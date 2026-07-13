"""index workflow：把建立索引流程组织成 DAG（用 services/workflow 通用引擎执行）。

- runner：组 seed DAG、注入运行期资源、跑 workflow、可取消
- ops：DAG 节点处理器（parse/embed/extract/attach/finalize）
- expanders：虚拟节点展开器（extract 按块扇出）
- recorder：index_run_recorder（写 nexus.index_run / nexus.index_node）
"""
from .runner import run_index, cancel_run, build_index_workflow, build_seed
from .recorder import index_run_recorder

__all__ = ["run_index", "cancel_run", "build_index_workflow", "build_seed", "index_run_recorder"]
