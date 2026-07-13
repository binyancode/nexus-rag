<template>
  <div class="summary-view">
    <div class="summary-head">
      <div class="summary-icon" :style="{ background: color + '18', color }">
        <el-icon><component :is="icon" /></el-icon>
      </div>
      <div><span>阶段 {{ stage.ordinal }}</span><h3>{{ stage.name }}</h3><p>{{ description }}</p></div>
      <el-tag :type="tagType" effect="light">{{ stateLabel(stage.state) }}</el-tag>
    </div>

    <el-alert v-if="stage.error" :title="stage.error" type="error" :closable="false" show-icon />

    <div class="metrics">
      <div class="metric"><span>耗时</span><b>{{ formatCost(stage.cost_ms) }}</b></div>
      <div class="metric"><span>输入 Token</span><b>{{ fmt(tokens.input) }}</b></div>
      <div class="metric"><span>输出 Token</span><b>{{ fmt(tokens.output) }}</b></div>
      <div class="metric"><span>向量 Token</span><b>{{ fmt(tokens.embedding) }}</b></div>
    </div>

    <div class="summary-section">
      <h4>本阶段完成情况</h4>
      <div class="facts">
        <div v-for="item in facts" :key="item.label" class="fact">
          <span>{{ item.label }}</span><b>{{ item.value }}</b>
        </div>
      </div>
    </div>

    <div class="time-row">
      <span>开始：{{ formatTime(stage.started_at) }}</span>
      <span>结束：{{ formatTime(stage.ended_at) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ChatDotRound, Connection, EditPen, MagicStick, Setting } from '@element-plus/icons-vue'
import type { QueryNodeState, QueryStageState } from '../../backend/Query.js'

const props = withDefaults(defineProps<{
  stage: QueryStageState
  nodes?: QueryNodeState[]
  runAnswer?: string | null
  citations?: Array<{ fullname:string; quote?:string|null }>
}>(), { nodes:()=>[], citations:()=>[] })

const output = computed(() => parse(props.stage.output) || {})
const input = computed(() => parse(props.stage.input) || {})
const tokens = computed(() => parse(props.stage.tokens) || {})
const description = computed(() => ({
  initializer:'确定用户可见的 Collection、Store 范围、预算和运行资源。',
  compiler:'把用户问题编译为只表达业务意图的 SQG。',
  optimizer:'绑定实体与关系，将 SQG 转换为可执行 PEP。',
  coordinator:'使用 Workflow 并行执行 PEP 中的固定物理算子。',
  generator:'只依据协调器输出的事实与原文依据生成答案。',
} as Record<string,string>)[props.stage.stage_id])
const icon = computed(() => ({initializer:Setting,compiler:EditPen,optimizer:MagicStick,coordinator:Connection,generator:ChatDotRound} as Record<string,any>)[props.stage.stage_id])
const color = computed(() => ({running:'#2f7cb4',succeeded:'#2e9b5b',failed:'#d52b1e',cancelled:'#97a3ae',skipped:'#97a3ae',pending:'#8291a0'} as Record<string,string>)[props.stage.state] || '#8291a0')
const tagType = computed(() => ({succeeded:'success',failed:'danger',cancelled:'info',skipped:'info',running:'primary',pending:'info'} as Record<string,any>)[props.stage.state] || 'info')
const facts = computed(() => {
  const o=output.value, i=input.value
  switch(props.stage.stage_id) {
    case 'initializer': return [
      {label:'用户问题',value:o.question || i.question || '—'},
      {label:'Collection',value:o.collection?.name || '—'},
      {label:'选择方式',value:selectionLabel(o.collection?.selected_by)},
      {label:'可用 Store',value:String(o.collection?.allowed_stores?.length || 0)},
      {label:'可见实体',value:String(o.entity_catalog?.length || 0)},
    ]
    case 'compiler': return [
      {label:'SQG 节点',value:String(o.nodes?.length || 0)},
      {label:'逻辑算子',value:opCounts(o.nodes)},
      {label:'终点',value:o.nodes?.find((x:any)=>x.op==='Answer')?.desc || '—'},
    ]
    case 'optimizer': return [
      {label:'PEP 节点',value:String(o.nodes?.length || 0)},
      {label:'物理算子',value:opCounts(o.nodes)},
      {label:'事实输出',value:o.outputs?.facts || '—'},
      {label:'依据输出',value:o.outputs?.evidence || '—'},
    ]
    case 'coordinator': {
      const succeeded=props.nodes.filter(n=>n.state==='succeeded').length
      const failed=props.nodes.filter(n=>n.state==='failed').length
      return [
        {label:'物理节点',value:String(props.nodes.length)},
        {label:'成功 / 失败',value:`${succeeded} / ${failed}`},
        {label:'事实项',value:String(o.facts?.items?.length || 0)},
        {label:'依据块',value:String(o.evidence?.items?.length || 0)},
      ]
    }
    default: return [
      {label:'答案长度',value:`${(props.runAnswer || '').length} 字`},
      {label:'引用出处',value:String(props.citations.length)},
      {label:'事实项',value:String(o.meta?.fact_count || 0)},
      {label:'依据块',value:String(o.meta?.evidence_count || 0)},
    ]
  }
})
function parse(raw?:string|null):any { if(!raw)return null; try{return JSON.parse(raw)}catch{return null} }
function fmt(n?:number) { return (n||0).toLocaleString('zh-CN') }
function formatCost(ms?:number|null) { return ms==null?'—':ms<1000?`${ms}ms`:`${(ms/1000).toFixed(1)}s` }
function formatTime(raw?:string|null) { if(!raw)return '—'; const d=new Date(raw); return isNaN(d.getTime())?raw:d.toLocaleString('zh-CN',{hour12:false}) }
function stateLabel(s:string) { return ({running:'运行中',succeeded:'完成',failed:'失败',cancelled:'已取消',skipped:'已跳过',pending:'等待'} as Record<string,string>)[s]||s }
function selectionLabel(s?:string) { return ({user:'用户指定',user_default:'用户默认',only_visible:'唯一可见',semantic_router:'语义选择'} as Record<string,string>)[s||'']||'—' }
function opCounts(nodes?:any[]) { const c:Record<string,number>={}; for(const n of nodes||[])c[n.op]=(c[n.op]||0)+1; return Object.entries(c).map(([k,v])=>`${k} × ${v}`).join(' · ')||'—' }
</script>

<style scoped>
.summary-view { padding:18px; border:1px solid var(--beone-border); border-radius:11px; background:#fff; }
.summary-head { display:grid; grid-template-columns:46px 1fr auto; gap:12px; align-items:start; }
.summary-icon { width:42px; height:42px; display:grid; place-items:center; border-radius:12px; font-size:19px; }
.summary-head span { color:var(--beone-text-secondary); font-size:10px; }
.summary-head h3 { margin:1px 0 3px; font-size:16px; }
.summary-head p { margin:0; color:var(--beone-text-secondary); font-size:11px; }
.metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:9px; margin-top:16px; }
.metric { padding:10px 12px; border-radius:8px; background:#f4f7fa; }
.metric span { display:block; color:var(--beone-text-secondary); font-size:9px; }
.metric b { display:block; margin-top:3px; color:#263b51; font-size:15px; }
.summary-section { margin-top:16px; }
.summary-section h4 { margin:0 0 8px; font-size:12px; color:var(--beone-midnight-blue); }
.facts { display:grid; grid-template-columns:1fr 1fr; gap:7px; }
.fact { display:flex; justify-content:space-between; gap:12px; padding:8px 10px; border-bottom:1px solid #edf0f3; }
.fact span { color:var(--beone-text-secondary); font-size:10px; }
.fact b { max-width:70%; text-align:right; font-size:10px; font-weight:600; word-break:break-word; }
.time-row { display:flex; gap:18px; margin-top:14px; color:var(--beone-text-secondary); font-size:9px; }
</style>
