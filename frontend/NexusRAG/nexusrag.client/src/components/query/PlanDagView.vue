<template>
  <div class="plan-wrap">
    <div v-if="!nodes.length" class="empty">等待计划生成…</div>
    <VueFlow v-else :nodes="nodes" :edges="edges" :node-types="nodeTypes"
              :fit-view-on-init="true" :nodes-draggable="true" :nodes-connectable="false"
              :elements-selectable="false" :min-zoom="0.25" :max-zoom="2" class="plan-canvas"
              @node-click="onNodeClick" @pane-click="selectedId=null">
      <Background pattern-color="#d9e2ee" :gap="24" :size="1.2" />
      <Controls :show-interactive="false" />
    </VueFlow>

    <transition name="detail-fade">
      <aside v-if="selectedDetail" class="node-detail">
        <div class="detail-head">
          <div><span>{{ isPhysical ? 'PEP 物理节点' : 'SQG 逻辑节点' }}</span><h3>{{ selectedDetail.name }}</h3></div>
          <button type="button" @click="selectedId=null">×</button>
        </div>
        <div class="detail-tags">
          <el-tag size="small" effect="plain">{{ selectedDetail.op }}</el-tag>
          <el-tag v-if="selectedDetail.state" size="small" :type="stateTag(selectedDetail.state)">{{ stateLabel(selectedDetail.state) }}</el-tag>
          <span v-if="selectedDetail.cost">耗时 {{ selectedDetail.cost }}</span>
        </div>

        <section v-if="selectedDetail.desc"><label>业务目标</label><p>{{ selectedDetail.desc }}</p></section>
        <section v-if="detailRows.length"><label>{{ isPhysical ? '执行参数' : '结构化意图' }}</label>
          <div class="detail-rows"><div v-for="r in detailRows" :key="r.key"><span>{{ r.key }}</span><b>{{ r.value }}</b></div></div>
        </section>
        <section v-if="inputRows.length"><label>{{ isPhysical ? '输入端口' : '上游依赖' }}</label>
          <div class="detail-rows"><div v-for="r in inputRows" :key="r.key"><span>{{ r.key }}</span><b>{{ r.value }}</b></div></div>
        </section>
        <section v-if="selectedDetail.result"><label>运行结果</label>
          <div class="result-summary"><b>{{ selectedDetail.result.kind }}</b><span>{{ selectedDetail.result.summary }}</span></div>
        </section>
        <section v-if="selectedDetail.tokens"><label>Token</label><p>{{ selectedDetail.tokens }}</p></section>
        <el-alert v-if="selectedDetail.error" :title="selectedDetail.error" type="error" :closable="false" />
      </aside>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, ref, watch } from 'vue'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MarkerType, VueFlow } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import IndexDagNode from '../index/IndexDagNode.vue'
import type { QueryNodeState } from '../../backend/Query.js'

interface PlanNode {
  id: string; op: string; desc?: string; name?: string
  inputs?: string[] | Record<string,string>; params?: Record<string,unknown>
  goal?: Record<string,unknown>; layer?: number
}
const props = defineProps<{ plan: { nodes?: PlanNode[]; outputs?:Record<string,string> } | null; states?: QueryNodeState[] }>()
const nodeTypes: any = { dagNode: markRaw(IndexDagNode) }
const stateMap = computed(() => Object.fromEntries((props.states || []).map(s => [s.node_id, s])))
const selectedId = ref<string|null>(null)
const isPhysical = computed(() => props.states !== undefined)

watch(() => props.plan, () => { selectedId.value=null })

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
        selected: selectedId.value===n.id,
        cost: st?.cost_ms != null ? `${st.cost_ms}ms` : undefined,
      },
    }
  }))
})
const edges = computed<any[]>(() => (props.plan?.nodes || []).flatMap(n => inputIds(n).map(dep => ({
  id: `${dep}->${n.id}`, source: dep, target: n.id, markerEnd: MarkerType.ArrowClosed,
  style: { stroke: '#91a7bd', strokeWidth: 1.5 },
}))))

const selectedDetail = computed(() => {
  const n=(props.plan?.nodes||[]).find(x=>x.id===selectedId.value)
  if(!n)return null
  const st=stateMap.value[n.id]
  const output=parse(st?.output)
  return {
    ...n, name:n.name||n.desc||n.id, state:st?.state,
    cost:st?.cost_ms!=null?`${st.cost_ms}ms`:null,
    tokens:tokenText(st?.tokens), error:st?.error,
    result:resultSummary(output),
  }
})
const detailRows=computed(()=>{
  const n=selectedDetail.value
  const source=isPhysical.value?n?.params:n?.goal
  return objectRows(source)
})
const inputRows=computed(()=>{
  const input=selectedDetail.value?.inputs
  if(!input)return[]
  if(Array.isArray(input))return input.map((x,i)=>({key:`依赖 ${i+1}`,value:x}))
  return Object.entries(input).map(([key,value])=>({key,value}))
})

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
function onNodeClick(event:any){selectedId.value=event.node.id}
function parse(raw?:string|null):any{if(!raw)return null;try{return JSON.parse(raw)}catch{return null}}
function display(value:unknown):string{
  if(value==null)return '—'
  if(Array.isArray(value))return value.join('、')||'—'
  if(typeof value==='object')return Object.entries(value as Record<string,unknown>).map(([k,v])=>`${k}: ${display(v)}`).join('；')
  return String(value)
}
function objectRows(value?:Record<string,unknown>){return Object.entries(value||{}).map(([key,v])=>({key,value:display(v)}))}
function tokenText(raw?:string|null){const t=parse(raw);if(!t)return null;return [`输入 ${t.input||0}`,`输出 ${t.output||0}`,`向量 ${t.embedding||0}`].join(' · ')}
function resultSummary(output:any){
  if(!output?.kind)return null
  if(output.kind==='evidence_bundle')return{kind:'分组证据',summary:`${output.groups?.length||0} 个文档组 · ${output.items?.length||0} 个原文块`}
  const labels:Record<string,string>={entity_set:'实体集合',block_set:'原文块集合',answer:'答案',empty:'空结果'}
  return{kind:labels[output.kind]||output.kind,summary:`${output.items?.length||0} 项`}
}
function stateTag(s:string):any{return({succeeded:'success',failed:'danger',running:'primary',skipped:'info',cancelled:'info'}as Record<string,string>)[s]||'info'}
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
.node-detail{position:absolute;top:12px;right:12px;z-index:6;width:300px;max-height:calc(100% - 24px);overflow:auto;padding:14px;border:1px solid #d7e3ee;border-radius:11px;background:rgba(255,255,255,.97);box-shadow:0 12px 30px rgba(27,52,78,.16)}
.detail-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}.detail-head span{color:var(--beone-text-secondary);font-size:9px}.detail-head h3{margin:2px 0 0;font-size:14px;color:#203246}.detail-head button{border:0;background:transparent;color:#7f8e9d;font-size:19px;cursor:pointer}.detail-tags{display:flex;align-items:center;gap:6px;margin-top:9px}.detail-tags>span{margin-left:auto;color:var(--beone-text-secondary);font-size:9px}.node-detail section{margin-top:13px}.node-detail label{display:block;margin-bottom:6px;color:#2f7cb4;font-size:10px;font-weight:700}.node-detail p{margin:0;color:#53697f;font-size:10px;line-height:1.55}.detail-rows{display:flex;flex-direction:column;gap:5px}.detail-rows>div{display:flex;justify-content:space-between;gap:10px;padding:6px 8px;border-radius:6px;background:#f5f8fb}.detail-rows span{color:var(--beone-text-secondary);font-size:9px}.detail-rows b{max-width:68%;text-align:right;font-size:9px;word-break:break-word}.result-summary{display:flex;align-items:center;justify-content:space-between;padding:8px;border-radius:7px;background:#edf6fd}.result-summary b{color:#2f7cb4;font-size:11px}.result-summary span{color:#53697f;font-size:9px}.detail-fade-enter-active,.detail-fade-leave-active{transition:opacity .16s ease,transform .16s ease}.detail-fade-enter-from,.detail-fade-leave-to{opacity:0;transform:translateX(8px)}
</style>
