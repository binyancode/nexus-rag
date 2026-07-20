<template>
  <div class="dag">
    <div class="dag-head">
      <div class="dag-head-left">
        <span class="dag-dot" :class="'dag-dot--' + runState"></span>
        <span class="dag-state">{{ stateLabel(runState) }}</span>
        <span class="dag-meta">{{ run?.doc_count || 0 }} 文档 · {{ run?.block_count || 0 }} 块 · {{ run?.node_count || 0 }} 节点</span>
      </div>
      <div class="dag-head-right">
        <span class="dag-par">并行 {{ run?.max_parallel || '-' }}</span>
        <el-button v-if="runState === 'running'" size="small" type="danger" plain :loading="cancelling" @click="cancel">
          取消
        </el-button>
      </div>
    </div>

    <div v-if="tokens" class="dag-tokens">
      <el-icon class="tok-ic"><Coin /></el-icon>
      <span>输入 {{ fmt(tokens.input) }}<span class="tok-dim" v-if="tokens.cached">（缓存 {{ fmt(tokens.cached) }}）</span></span>
      <span>· 输出 {{ fmt(tokens.output) }}</span>
      <span>· 向量 {{ fmt(tokens.embedding) }}</span>
    </div>

    <div class="dag-wrap">
      <div v-if="!nodes.length" class="dag-empty">等待 DAG…</div>
      <button v-if="nodes.length" class="dag-reset" title="恢复自动布局并居中" @click="resetLayout">⟲ 自动布局</button>
      <VueFlow
        v-if="nodes.length"
        :nodes="nodes"
        :edges="edges"
        :node-types="nodeTypes"
        :fit-view-on-init="true"
        :nodes-draggable="true"
        :nodes-connectable="false"
        :elements-selectable="false"
        :min-zoom="0.2"
        :max-zoom="2"
        class="dag-canvas"
        @node-click="onNodeClick"
        @node-drag-stop="onNodeDragStop"
        @pane-click="selectedId = null"
      >
        <Background pattern-color="#d9e2ee" :gap="24" :size="1.3" />
        <Controls :show-interactive="false" />
      </VueFlow>

      <transition name="fade">
        <div v-if="selected" class="node-detail">
          <div class="nd-head">
            <span class="nd-dot" :style="{ background: stateColor(selected.state) }"></span>
            <span class="nd-name">{{ selected.name }}</span>
            <span class="nd-badge">{{ stateLabel(selected.state) }}</span>
            <span class="nd-close" @click="selectedId = null">✕</span>
          </div>
          <div class="nd-row"><b>阶段</b><span>{{ phaseLabel(selected.phase) }}</span></div>
          <div class="nd-row" v-if="selected.value"><b>输出</b><span class="nd-val">{{ selected.value }}</span></div>
          <div class="nd-row" v-if="selected.cost"><b>耗时</b><span>{{ selected.cost }}</span></div>
          <div class="nd-row" v-if="selected.tokenText"><b>Token</b><span>{{ selected.tokenText }}</span></div>
          <div class="nd-block err" v-if="selected.error"><b>错误</b><pre>{{ selected.error }}</pre></div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Coin } from '@element-plus/icons-vue'
import { VueFlow, MarkerType, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import IndexDagNode from './IndexDagNode.vue'
import {
  getIndexRun, cancelIndex,
  type Dag, type DagNode, type IndexNodeState, type IndexRunInfo, type TokenUsage,
} from '../../backend/Index.js'

const props = defineProps<{ runId: string }>()
const emit = defineEmits<{ (e: 'terminal', state: string): void }>()

const FOLD_THRESHOLD = 8
const X_GAP = 250
const Y_GAP = 84
const PHASE_LABEL: Record<string, string> = { parse: '切块', embed: '向量化', extract: '抽取', attach: '入网', done: '完成' }

const nodeTypes: any = { dagNode: markRaw(IndexDagNode) }
const { fitView } = useVueFlow()

const run = ref<IndexRunInfo | null>(null)
const nodeStates = ref<Record<string, IndexNodeState>>({})
const dag = ref<Dag | null>(null)
const cancelling = ref(false)
const selectedId = ref<string | null>(null)
const posOverride = ref<Record<string, { x: number; y: number }>>({})
let timer: number | undefined

const runState = computed(() => run.value?.state || 'running')
const tokens = computed<TokenUsage | null>(() => parseJson(run.value?.tokens))

watch(() => props.runId, start, { immediate: true })
onBeforeUnmount(stop)

function start() {
  stop()
  run.value = null; dag.value = null; nodeStates.value = {}; selectedId.value = null; posOverride.value = {}
  if (!props.runId) return
  timer = window.setInterval(poll, 5000)
  poll()
}
function stop() { if (timer) { window.clearInterval(timer); timer = undefined } }

async function poll() {
  if (!props.runId) return
  try {
    const data = await getIndexRun(props.runId)
    run.value = data.run
    dag.value = parseJson(data.run?.dag)
    const map: Record<string, IndexNodeState> = {}
    for (const n of data.nodes || []) map[n.node_id] = n
    nodeStates.value = map
    if (['succeeded', 'failed', 'cancelled'].includes(runState.value)) {
      stop()
      emit('terminal', runState.value)
    }
  } catch {
    /* 静默 */
  }
}

// ---- 折叠结构（仅随 dag 变）----
interface VNode { vid: string; type: 'task' | 'group'; phase: string; name: string; layer: number; members: string[]; deps: string[] }

const visualNodes = computed<VNode[]>(() => {
  const d = dag.value
  if (!d?.nodes?.length) return []
  const groups: Record<string, DagNode[]> = {}
  for (const n of d.nodes) if (n.sibling_group) (groups[n.sibling_group] ||= []).push(n)
  const folded = new Set(Object.keys(groups).filter(g => (groups[g]?.length ?? 0) > FOLD_THRESHOLD))
  const visualOf: Record<string, string> = {}
  for (const n of d.nodes) {
    visualOf[n.id] = (n.sibling_group && folded.has(n.sibling_group)) ? 'group:' + n.sibling_group : n.id
  }
  const map: Record<string, VNode> = {}
  for (const n of d.nodes) {
    const vid = visualOf[n.id]!
    if (!map[vid]) {
      map[vid] = {
        vid, type: vid.startsWith('group:') ? 'group' : 'task', phase: n.phase, layer: n.layer,
        name: vid.startsWith('group:') ? (n.name.replace(/·.*$/, '') || n.sibling_group!) : (n.name || n.id),
        members: [], deps: [],
      }
    }
    map[vid]!.members.push(n.id)
  }
  const depSet: Record<string, Set<string>> = {}
  for (const n of d.nodes) {
    const to = visualOf[n.id]!
    for (const dep of n.depends_on || []) {
      const from = visualOf[dep]
      if (from && from !== to) (depSet[to] ||= new Set()).add(from)
    }
  }
  for (const v of Object.values(map)) v.deps = [...(depSet[v.vid] || [])]
  return Object.values(map)
})

// 自动布局：按 layer 分波，每波竖直居中
const layoutPos = computed(() => {
  const byLayer: Record<number, VNode[]> = {}
  for (const v of visualNodes.value) (byLayer[v.layer] ||= []).push(v)
  const waves = Object.keys(byLayer).map(Number).sort((a, b) => a - b).map(l => byLayer[l]!)
  const pos = new Map<string, { x: number; y: number }>()
  const maxRows = Math.max(1, ...waves.map(w => w.length))
  waves.forEach((wave, wi) => {
    const offset = ((maxRows - wave.length) * Y_GAP) / 2
    wave.forEach((v, ni) => pos.set(v.vid, { x: 24 + wi * X_GAP, y: 24 + offset + ni * Y_GAP }))
  })
  return pos
})

// ---- Vue Flow 节点 / 边（随状态+选择重算）----
const nodes = computed(() => {
  const pos = layoutPos.value
  const over = posOverride.value
  return visualNodes.value.map(v => {
    const agg = stateOf(v)
    return {
      id: v.vid, type: 'dagNode',
      position: over[v.vid] ?? pos.get(v.vid) ?? { x: 0, y: 0 },
      class: agg.state === 'running' ? 'rn-pulse' : '',
      data: {
        name: v.name, badge: phaseLabel(v.phase), value: agg.value, color: stateColor(agg.state),
        selected: v.vid === selectedId.value, cost: agg.cost,
        total: v.type === 'group' ? v.members.length : undefined,
        ratio: v.type === 'group' ? agg.ratio : undefined,
      },
    }
  })
})

const edges = computed(() => {
  const sel = selectedId.value
  const out: any[] = []
  for (const v of visualNodes.value) {
    const st = stateOf(v).state
    const col = stateColor(st)
    for (const from of v.deps) {
      const hl = sel != null && (sel === v.vid || sel === from)
      out.push({
        id: `${from}->${v.vid}`, source: from, target: v.vid, type: 'smoothstep',
        animated: st === 'running' || hl,
        style: { stroke: hl ? '#7c5cff' : col, strokeWidth: hl ? 2.6 : 1.6 },
        class: hl ? 'edge-hl' : '',
        markerEnd: { type: MarkerType.ArrowClosed, color: hl ? '#7c5cff' : col, width: 14, height: 14 },
      })
    }
  }
  return out
})

// 选中详情
const selected = computed(() => {
  const v = visualNodes.value.find(x => x.vid === selectedId.value)
  if (!v) return null
  const agg = stateOf(v)
  let error: string | null = null
  let tokenText = ''
  if (v.type === 'task') {
    const row = nodeStates.value[v.members[0]!]
    error = row?.error ?? null
    const tk = parseJson<TokenUsage>(row?.tokens ?? null)
    if (tk) tokenText = tokenSummary(tk)
  }
  return { name: v.name, phase: v.phase, state: agg.state, value: agg.value, cost: agg.cost, error, tokenText }
})

// ---- 状态聚合 ----
function stateOf(v: VNode): { state: string; value: string; cost?: string; ratio: number } {
  if (v.type === 'group') {
    let done = 0, failed = 0, running = 0, cancelled = 0
    for (const id of v.members) {
      const s = nodeStates.value[id]?.state
      if (s === 'succeeded') done++
      else if (s === 'failed') failed++
      else if (s === 'running') running++
      else if (s === 'cancelled') cancelled++
    }
    const total = v.members.length
    let state = 'pending'
    if (failed) state = 'failed'
    else if (running || (done > 0 && done < total)) state = 'running'
    else if (done === total) state = 'succeeded'
    else if (cancelled) state = 'cancelled'
    return { state, value: `${done}/${total}` + (failed ? ` · 失败 ${failed}` : ''), ratio: total ? done / total : 0 }
  }
  const row = nodeStates.value[v.members[0]!]
  const state = row?.state || (v.phase === 'extract' && dag.value ? 'pending' : 'pending')
  const value = row?.output ? row.output.slice(0, 28) : (state === 'pending' ? '待执行' : '')
  const cost = row?.cost_ms != null ? fmtCost(row.cost_ms) : undefined
  return { state, value, cost, ratio: 0 }
}

// ---- 交互 ----
function onNodeClick(e: { node: { id: string } }) { selectedId.value = e.node.id }
function onNodeDragStop(e: { node: { id: string; position: { x: number; y: number } } }) {
  posOverride.value = { ...posOverride.value, [e.node.id]: { ...e.node.position } }
}
function resetLayout() {
  posOverride.value = {}
  nextTick(() => { try { fitView({ padding: 0.15 }) } catch { /* ignore */ } })
}

async function cancel() {
  cancelling.value = true
  try {
    await cancelIndex(props.runId)
    ElMessage.info('已请求取消，运行将尽快停止')
  } catch { /* 拦截器提示 */ } finally { cancelling.value = false }
}

// ---- helpers ----
function parseJson<T = any>(s: string | null | undefined): T | null {
  if (!s) return null
  try { return JSON.parse(s) } catch { return null }
}
function fmt(n: number | undefined) { return (n ?? 0).toLocaleString('en-US') }
function fmtCost(ms: number) { return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s` }
function phaseLabel(p: string) { return PHASE_LABEL[p] || p }
function tokenSummary(t: TokenUsage) {
  const parts: string[] = []
  if (t.input) parts.push(`入 ${t.input}`)
  if (t.output) parts.push(`出 ${t.output}`)
  if (t.embedding) parts.push(`向量 ${t.embedding}`)
  return parts.join(' · ')
}
function stateColor(s?: string | null) {
  return ({ running: '#2f7cb4', succeeded: '#2e9b5b', failed: '#d52b1e',
    cancelled: '#97a3ae', skipped: '#97a3ae', virtual: '#7c5cff', pending: '#c4cbd1' } as Record<string, string>)[s || 'pending'] || '#c4cbd1'
}
function stateLabel(s: string) {
  return ({ running: '运行中', succeeded: '完成', failed: '失败', cancelled: '已取消',
    skipped: '已跳过', pending: '等待', virtual: '待展开' } as Record<string, string>)[s] || s
}
</script>

<style scoped>
.dag { display: flex; flex-direction: column; }
.dag-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.dag-head-left { display: flex; align-items: center; gap: 8px; }
.dag-dot { width: 9px; height: 9px; border-radius: 50%; background: #94a3b8; }
.dag-dot--running { background: #f59e0b; animation: dag-pulse 1.3s infinite; }
.dag-dot--succeeded { background: #16a34a; }
.dag-dot--failed { background: #dc2626; }
.dag-dot--cancelled { background: #64748b; }
.dag-state { font-weight: 600; font-size: 14px; }
.dag-meta, .dag-par { font-size: 12px; color: var(--beone-text-secondary); }
.dag-head-right { display: flex; align-items: center; gap: 10px; }
.dag-tokens { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12px; color: var(--beone-text-secondary);
  padding: 6px 10px; margin-bottom: 8px; border-radius: 8px;
  background: linear-gradient(135deg, rgba(59,130,246,0.08), rgba(6,182,212,0.08)); border: 1px solid rgba(59,130,246,0.2); }
.tok-ic { color: #0891b2; }
.tok-dim { color: #94a3b8; }

.dag-wrap { position: relative; width: 100%; height: 520px; border: 1px solid #dbe5f2; border-radius: 12px; overflow: hidden; background: #f4f8fd; }
.dag-canvas { width: 100%; height: 100%; }
.dag-empty { height: 100%; display: flex; align-items: center; justify-content: center; color: var(--beone-text-secondary); font-size: 13px; }
.dag-reset {
  position: absolute; top: 10px; left: 10px; z-index: 5;
  font-size: 12px; color: #3f566f; cursor: pointer;
  background: #fff; border: 1px solid #dbe5f2; border-radius: 8px; padding: 4px 10px; line-height: 1.4;
  box-shadow: 0 4px 12px rgba(20, 40, 70, 0.12); transition: background 0.15s, border-color 0.15s;
}
.dag-reset:hover { background: #f1f6fb; border-color: #7c5cff; color: #5b3fd6; }

:deep(.vue-flow__node-dagNode) { background: none; border: none; padding: 0; box-shadow: none; width: auto; border-radius: 0; }
:deep(.vue-flow__node.rn-pulse) { animation: rnpulse 1.1s ease-in-out infinite; }
@keyframes rnpulse {
  0%, 100% { filter: drop-shadow(0 0 2px rgba(47, 124, 180, 0.3)); }
  50% { filter: drop-shadow(0 0 11px rgba(47, 124, 180, 0.75)); }
}
:deep(.vue-flow__edge.edge-hl .vue-flow__edge-path) { filter: drop-shadow(0 0 3px rgba(124, 92, 255, 0.55)); }
:deep(.vue-flow__controls) { box-shadow: 0 8px 20px rgba(20, 40, 70, 0.16); border: 1px solid #dbe5f2; border-radius: 10px; overflow: hidden; }
:deep(.vue-flow__controls-button) { background: #fff; color: #3f566f; }
:deep(.vue-flow__controls-button:hover) { background: #f1f6fb; }

.node-detail {
  position: absolute; top: 10px; right: 10px; width: 258px; background: #fff;
  border: 1px solid #dbe5f2; border-radius: 10px; box-shadow: 0 12px 30px rgba(16, 24, 40, 0.14);
  padding: 10px 12px; font-size: 12px; max-height: 92%; overflow: auto;
}
.nd-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.nd-dot { width: 10px; height: 10px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 0 0 2px rgba(157, 170, 186, 0.2); }
.nd-name { font-weight: 700; flex: 1; color: #1f2f43; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nd-badge { font-size: 10px; color: #6f859c; }
.nd-close { cursor: pointer; color: #7a8da3; }
.nd-row { display: flex; gap: 8px; margin: 3px 0; color: #2f455e; }
.nd-row b { color: #6f859c; font-weight: 600; min-width: 34px; }
.nd-val { font-weight: 700; color: #1f2f43; word-break: break-word; }
.nd-block b { color: #6f859c; font-weight: 600; }
.nd-block pre { margin: 4px 0 0; background: #fff2f2; border: 1px solid #f0caca; border-radius: 6px; padding: 6px 8px; font-size: 11px; color: #a33a3a; max-height: 140px; overflow: auto; white-space: pre-wrap; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
@keyframes dag-pulse { 0% { box-shadow: 0 0 0 0 rgba(245,158,11,0.5); } 70% { box-shadow: 0 0 0 6px rgba(245,158,11,0); } 100% { box-shadow: 0 0 0 0 rgba(245,158,11,0); } }
</style>
