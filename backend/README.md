# Nexus Retrieval Engine — Backend

基于 data_nexus 通用框架骨架搭建（IoC 容器 / 配置系统 / API 装饰器 / MSAL 认证 /
SQL Server 访问 / Key Vault 凭据 / API 日志），去除了 data_nexus 的取数引擎与 ontology 领域代码。
检索引擎（两层图 + 向量 + 溯源）在 `app/nexus/` 下自建。

## 结构

```
app/
  main.py              FastAPI 入口（配置驱动路由）
  bootstrap.py         服务注册（sql_db / 凭据 / API 日志汇 / 运行记录器）
  config.py/json       三级配置：文件 → DB → 环境变量
  core/                IoC 容器、API 装饰器、MSAL 认证、依赖注入、取消令牌、API 日志接口
  services/            sql_db（SQL Server 连接池）、credential（Key Vault 凭据）
  models/              Pydantic 基类与 API 模型
  utils/               logger、json_utils
  nexus/core/run_log   运行记录接口（引擎落库进度用；表结构随引擎阶段定型后创建）
api/v1/                路由装配 + 端点（me 认证、credentials 凭据）
```

## 运行

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd app
uvicorn main:app --reload --port 8000
```

- 健康检查：GET http://localhost:8000/health
- 交互文档：http://localhost:8000/docs

## 数据库

- 服务器 `binyansql-ea-01`，库 `binyan-nexus-rag`，schema `nexus`。
- 已建表：`api_log`、`app_credential`、`app_user`。
- `run` / `run_stage` / `run_node`（运行进度表）随引擎阶段定型后再建，届时对齐
  `bootstrap.py` 的 `DbRunRecorder` 列名。

## 待接入

- 凭据 Key Vault（`config.credential_provider.vault_url`）当前沿用参考项目地址，投产前更换为本项目 KV。
- 检索引擎门面就绪后，在 `bootstrap.register_services` 追加注册，并在 `config.route_prefixes` 挂载其端点。
