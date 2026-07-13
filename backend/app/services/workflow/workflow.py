"""Workflow 引擎:通用 DAG 执行器。

模型:
- 一张**可变活图**:预生成的 DAG 里可以有虚拟节点(VIRTUAL);当它的父全部终态时,
  调其 expander(拿父输出)→ 产出物理节点 → 缝合(根接虚拟节点的父、虚拟节点的子改接生成叶)
  → 虚拟节点从图中消失 → 触发 on_dag_update(整图落库)。
- **单一调度线程**做:就绪判定 / 展开 / 缝合 / 整图落库 / 起节点 / 收结果 / token 聚合;
  worker 线程池只跑处理器(纯计算,返回 NodeResult)。→ 所有落库单写者,无需锁。
- 就绪判定:上游全终态后——**依赖全部成功**才执行;任一依赖失败/跳过 → 本节点 skipped(失败一路传到底)。
  下游只拿成功父的产物。
- 全局并发 ≤ max_parallel。任一节点 failed → run failed。
"""
from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Callable

from utils.logger import get_logger

from .node import TASK, VIRTUAL, Node, NodeContext
from .recorder import NullWorkflowRecorder, WorkflowRecorder
from .result import NodeResult

_logger = get_logger("nexus.workflow")

_TERMINAL = {"succeeded", "failed", "skipped"}

# 处理器:ctx -> NodeResult;展开器:ctx -> list[Node]
TaskFn = Callable[[NodeContext], NodeResult]
ExpanderFn = Callable[[NodeContext], list]


class Workflow:
    def __init__(self):
        self._ops: dict[str, TaskFn] = {}
        self._expanders: dict[str, ExpanderFn] = {}

    # ---------------- 注册 ----------------
    def register(self, op: str, fn: TaskFn) -> "Workflow":
        self._ops[op] = fn
        return self

    def register_expander(self, name: str, fn: ExpanderFn) -> "Workflow":
        self._expanders[name] = fn
        return self

    # ---------------- 执行 ----------------
    def run(self, run_id: str, seed: list[Node], max_parallel: int,
            recorder: WorkflowRecorder | None = None, shared: dict | None = None,
            cancel_token=None) -> dict:
        recorder = recorder or NullWorkflowRecorder()
        shared = shared or {}
        max_parallel = max(1, int(max_parallel or 1))

        graph: dict[str, Node] = {n.id: n for n in seed}
        state: dict[str, str] = {nid: "pending" for nid in graph}
        output: dict[str, object] = {}
        started_at: dict[str, float] = {}
        dag_version = [0]

        run_start = time.time()
        self._emit_dag(recorder, run_id, graph, dag_version)

        def _cancelled() -> bool:
            return cancel_token is not None and cancel_token.is_cancelled

        running: dict[Future, str] = {}
        with ThreadPoolExecutor(max_workers=max_parallel) as pool:
            while True:
                if not _cancelled():
                    # 0) 硬依赖失败的 pending 节点→标 skipped(可级联，失败传到底)
                    progressed = True
                    while progressed:
                        progressed = False
                        for n in list(graph.values()):
                            if state.get(n.id) == "pending" and self._classify(n, state) == "skip":
                                state[n.id] = "skipped"
                                recorder.finish_node(run_id, n.id, "skipped", None,
                                                     "已跳过（上游失败）", None, None, 0)
                                progressed = True

                    # 1) 展开所有就绪虚拟节点(可能级联)
                    while True:
                        v = self._next_ready_virtual(graph, state)
                        if v is None:
                            break
                        self._expand(v, graph, state, output, max_parallel, shared, recorder,
                                     run_id, dag_version, cancel_token)

                    # 2) 调度就绪 task(受并发上限)
                    for node in self._ready_tasks(graph, state):
                        if len(running) >= max_parallel:
                            break
                        state[node.id] = "running"
                        started_at[node.id] = time.time()
                        recorder.start_node(run_id, node.id)
                        ctx = NodeContext(
                            run_id=run_id, node=node,
                            deps=self._dep_outputs(node, state, output),
                            max_parallel=max_parallel, shared=shared, cancel_token=cancel_token,
                        )
                        fut = pool.submit(self._safe_run, self._ops.get(node.op), ctx)
                        running[fut] = node.id

                # 3) 没有在跑的了 → 结束(完成 / 停滞 / 取消后已排空)
                if not running:
                    break

                # 4) 等至少一个完成,回收结果
                done, _ = wait(list(running.keys()), return_when=FIRST_COMPLETED)
                for fut in done:
                    nid = running.pop(fut)
                    cost = int((time.time() - started_at.get(nid, run_start)) * 1000)
                    res: NodeResult = fut.result()   # _safe_run 不抛
                    if res.error and _cancelled():
                        st = "cancelled"
                    elif res.error:
                        st = "failed"
                    else:
                        st = "succeeded"
                    output[nid] = res.output
                    state[nid] = st
                    recorder.finish_node(run_id, nid, st, res.output, res.value, res.tokens, res.error, cost)
                    if res.tokens:
                        recorder.bump_tokens(run_id, res.tokens)
                    if res.error and st != "cancelled":
                        _logger.warning(f"node {nid} failed: {res.error}")

        if _cancelled():
            final = "cancelled"
        elif any(s == "failed" for s in state.values()):
            final = "failed"
        else:
            final = "succeeded"
        recorder.finish_run(run_id, final, None, int((time.time() - run_start) * 1000))
        return {"state": final, "outputs": output, "node_states": state}

    # ---------------- 内部 ----------------
    @staticmethod
    def _safe_run(fn, ctx: NodeContext) -> NodeResult:
        if fn is None:
            return NodeResult(error=f"未注册的 op: {ctx.node.op!r}")
        try:
            r = fn(ctx)
            return r if isinstance(r, NodeResult) else NodeResult(output=r)
        except Exception as exc:  # noqa: BLE001
            return NodeResult(error=str(exc))

    def _deps_terminal(self, node: Node, state: dict) -> bool:
        return all(state.get(d) in _TERMINAL for d in node.depends_on)

    def _classify(self, node: Node, state: dict) -> str:
        """就绪判定：wait=还有父未终态；skip=任一依赖没成功→跳过（失败传到底）；run=全部成功。"""
        if not self._deps_terminal(node, state):
            return "wait"
        if all(state.get(d) == "succeeded" for d in node.depends_on):
            return "run"
        return "skip"

    def _ready_tasks(self, graph: dict, state: dict) -> list[Node]:
        return [n for n in graph.values()
                if n.kind == TASK and state.get(n.id) == "pending" and self._classify(n, state) == "run"]

    def _next_ready_virtual(self, graph: dict, state: dict) -> Node | None:
        for n in graph.values():
            if n.kind == VIRTUAL and state.get(n.id) == "pending" and self._classify(n, state) == "run":
                return n
        return None

    @staticmethod
    def _dep_outputs(node: Node, state: dict, output: dict) -> dict:
        # 只把成功父的产物给下游
        return {d: output.get(d) for d in node.depends_on if state.get(d) == "succeeded"}

    def _expand(self, v: Node, graph: dict, state: dict, output: dict,
                max_parallel: int, shared: dict, recorder: WorkflowRecorder,
                run_id: str, dag_version: list, cancel_token=None) -> None:
        expander = self._expanders.get(v.expander)
        ctx = NodeContext(run_id=run_id, node=v, deps=self._dep_outputs(v, state, output),
                          max_parallel=max_parallel, shared=shared, cancel_token=cancel_token)
        try:
            physical = expander(ctx) if expander else None
            if not physical:
                physical = []
        except Exception as exc:  # noqa: BLE001
            _logger.warning(f"expander {v.expander!r} failed: {exc}")
            state[v.id] = "failed"      # 展开失败 → 虚拟节点标 failed(终态,下游照跑)
            return
        self._splice(v, physical, graph, state)
        self._emit_dag(recorder, run_id, graph, dag_version)

    @staticmethod
    def _splice(v: Node, physical: list, graph: dict, state: dict) -> None:
        """把 physical 替换虚拟节点 v:根接 v 的父,v 的子改接 physical 的叶。"""
        phys_ids = {p.id for p in physical}
        # 根(内部无依赖的)→ 接 v 的父;其余保留内部依赖
        for p in physical:
            if not p.depends_on:
                p.depends_on = list(v.depends_on)
            graph[p.id] = p
            state[p.id] = "pending"
        # 叶(没有其它 physical 依赖它的);空展开 → 直通:下游改接 v 的父
        depended = {d for p in physical for d in p.depends_on if d in phys_ids}
        leaves = [p.id for p in physical if p.id not in depended]
        if not leaves:
            leaves = list(v.depends_on)
        # v 的所有下游:把 depends_on 里的 v 替换成 leaves
        for node in graph.values():
            if v.id in node.depends_on:
                node.depends_on = [d for d in node.depends_on if d != v.id] + leaves
        # 移除虚拟节点
        graph.pop(v.id, None)
        state.pop(v.id, None)

    @staticmethod
    def _emit_dag(recorder: WorkflowRecorder, run_id: str, graph: dict, dag_version: list) -> None:
        dag_version[0] += 1
        recorder.on_dag_update(run_id, {
            "version": dag_version[0],
            "nodes": [n.to_json() for n in graph.values()],
        })
