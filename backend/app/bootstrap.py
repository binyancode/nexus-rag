"""bootstrap.py —— 共享的服务注册。

把系统 DB、凭据提供器注册进全局 IoC 容器；注册 API 日志汇与运行记录器。
main.py 启动时调用。

说明：检索引擎（Nexus Retrieval Engine）尚未构建，这里只装配通用基础设施。
引擎就绪后，在 register_services 内追加其门面（如 NexusClient）的注册即可。
"""
from services.sql_db import sql_db
from services.credential import azure_keyvault_credential_provider
from core.services import services
from core.api_handler import api_handler
from core.api_log import ApiLogRecord, ApiLogSink
from nexus.stores import store_registry, document_store, entity_store, edge_store, block_store
from nexus.index import attach_entity
from utils.logger import get_logger

_log = get_logger("api")


class ApiLogRecorder(ApiLogSink):
    """API 日志汇：同时记录到 nexus.api_log 和系统 logger（按 state 分级）。

    DB 依赖留在 app 层，core 不引用 services。
    """

    def emit(self, record: ApiLogRecord) -> None:
        # 1) 系统 logger（按状态分级；错误时把完整堆栈换行打出，便于定位报错行）
        line = (f"[{record.function}] {record.method} {record.path} "
                f"state={record.state} user={record.user} {record.cost_ms}ms")
        if record.state in ("failed", "error"):
            _log.error(line + (f"\n{record.message}" if record.message else ""))
        elif record.state in ("denied", "unauthorized"):
            _log.warning(line + (f" {record.message}" if record.message else ""))
        else:
            _log.info(line)

        # 2) 数据库
        services[sql_db].execute_non_query(
            """INSERT INTO nexus.api_log
                   (function_name, [method], [path], user_name, payload, response, state, cost_ms, message, source, request_time, response_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.function, record.method, record.path, record.user, record.payload,
                record.response, record.state, record.cost_ms, record.message, record.source,
                record.request_time, record.response_time,
            ),
        )


def register_services():
    """注册服务类型及默认配置映射。"""
    services.register(sql_db)
    services.register(azure_keyvault_credential_provider)

    # Nexus 存储层（实体/边/出处/Store/文档），均依赖 services[sql_db]
    services.register(store_registry)
    services.register(document_store)
    services.register(entity_store)
    services.register(edge_store)
    services.register(block_store)

    # Nexus 索引（建立索引阶段）
    services.register(attach_entity)

    # services[Type] 取实例时，自动把对应 config 段传给构造函数
    services.register_default_config(sql_db, "sql_db")
    services.register_default_config(azure_keyvault_credential_provider, "credential_provider")

    # 注册实现 ApiLogSink 接口的日志汇（依赖倒置：DB 依赖在 app 层，core 不引用 services）
    api_handler.register_log_sink(ApiLogRecorder())


def register_resolvers():
    """检索引擎的 Resolver / LLM 注册占位。引擎定型后在此装配。"""
    pass
