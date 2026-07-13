<template>
  <div class="plan-wrap">
    <div v-if="!nodes.length" class="empty">等待计划生成…</div>
    <VueFlow v-else :nodes="nodes" :edges="edges" :node-types="nodeTypes"
              :fit-view-on-init="true" :nodes-draggable="true" :nodes-connectable="false"
              :elements-selectable="false" :min-zoom="0.25" :max-zoom="2" class="plan-canvas">
      <Background pattern-color="#d9e2ee" :gap="24" :size="1.2" />
      <Controls :show-interactive="false" />
    </VueFlow>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw } from 'vue'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MarkerType, VueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import IndexDagNode from '../index/IndexDagNode.vue'
import type { QueryNodeState } from '../../backend/Query.js'

interface PlanNode { id: string; op: string; desc?: string; name?: string; inputs?: string[] | Record<string,string>; layer?: number }
const props = defineProps<{ plan: { nodes?: PlanNode[] } | null; states?: QueryNodeState[] }>()
const nodeTypes: any = { dagNode: markRaw(IndexDagNode) }
const stateMap = computed(() => Object.fromEntries((props.states || []).map(s => [s.node_id, s])))

const layers = computed(() => {
  const planNodes = props.plan?.nodes || []
  const byId = new Map(planNodes.map(n => [n.id, n]))
  const memo: Record<string, number> = {}
  const depth = (id: string): number => {
    if (memo[id] !== undefined) return memo[id]!
    const n = byId.get(id)
    const deps = inputIds(n)
    return (memo[id] = deps.length ? 1 + Math.max(...deps.map(depth)) : 0)
  }
  for (const n of planNodes) depth(n.id)
  return memo
})

const nodes = computed<any[]>(() => {
  const grouped: Record<number, PlanNode[]> = {}
  for (const n of props.plan?.nodes || []) (grouped[layers.value[n.id] || 0] ||= []).push(n)
  return Object.entries(grouped).flatMap(([layer, group]) => group.map((n, i) => {
    const st = stateMap.value[n.id]
    return {
      id: n.id, type: 'dagNode', position: { x: Number(layer) * 245, y: i * 92 },
      class: st?.state === 'running' ? 'rn-pulse' : '',
      data: {
        name: n.name || n.desc || n.id, badge: n.op,
        value: st ? (st.value || stateLabel(st.state)) : undefined,
        color: stateColor(st?.state),
        cost: st?.cost_ms != null ? `${st.cost_ms}ms` : undefined,
      },
    }
  }))
})
const edges = computed<any[]>(() => (props.plan?.nodes || []).flatMap(n => inputIds(n).map(dep => ({
  id: `${dep}->${n.id}`, source: dep, target: n.id, markerEnd: MarkerType.ArrowClosed,
  style: { stroke: '#91a7bd', strokeWidth: 1.5 },
}))))

function inputIds(n?: PlanNode) {
  if (!n?.inputs) return []
  return Array.isArray(n.inputs) ? n.inputs : [...new Set(Object.values(n.inputs))]
}
function stateColor(s?: string | null) {
  return ({ running:'#2f7cb4',succeeded:'#2e9b5b',failed:'#d52b1e',skipped:'#97a3ae',cancelled:'#97a3ae' } as Record<string,string>)[s || ''] || '#7c5cff'
}
function stateLabel(s?: string | null) {
  return ({ running:'运行中',succeeded:'完成',failed:'失败',skipped:'已跳过',cancelled:'已取消' } as Record<string,string>)[s || ''] || ''
}
</script>

<style scoped>
.plan-wrap { height: 430px; position: relative; border: 1px solid var(--beone-border); border-radius: 10px; overflow: hidden; background: #f7fafe; }
.plan-canvas { width: 100%; height: 100%; }
.empty { height: 100%; display: flex; align-items: center; justify-content: center; color: var(--beone-text-secondary); font-size: 13px; }
:deep(.vue-flow__node-dagNode) { background: none; border: none; padding: 0; box-shadow: none; width: auto; border-radius: 0; }
:deep(.vue-flow__node.rn-pulse) { animation: pep-node-pulse 1.05s ease-in-out infinite; }
@keyframes pep-node-pulse {
  0%, 100% { filter: drop-shadow(0 0 3px rgba(47, 124, 180, 0.30)); }
  50% { filter: drop-shadow(0 0 12px rgba(47, 124, 180, 0.82)); }
}
</style>
