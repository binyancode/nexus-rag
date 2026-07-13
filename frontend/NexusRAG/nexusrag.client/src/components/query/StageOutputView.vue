<template>
  <div class="output-view">
    <div class="output-head">
      <div><span>{{ stage?.name || '阶段输出' }}</span><h3>{{ outputTitle }}</h3></div>
      <span v-if="stage?.cost_ms != null" class="cost">{{ formatCost(stage.cost_ms) }}</span>
    </div>

    <PlanDagView v-if="stage?.stage_id === 'compiler'" :plan="output" />
    <PlanDagView v-else-if="stage?.stage_id === 'optimizer'" :plan="output" :states="nodes" />
    <AnswerPanel v-else-if="stage?.stage_id === 'generator'" :answer="runAnswer" :citations="citations" />

    <div v-else-if="stage?.stage_id === 'initializer'" class="context-view">
      <div class="context-question"><span>用户问题</span><b>{{ output.question || '—' }}</b></div>
      <div class="context-grid">
        <div><span>Collection</span><b>{{ output.collection?.name || '—' }}</b></div>
        <div><span>选择方式</span><b>{{ selectionLabel(output.collection?.selected_by) }}</b></div>
        <div><span>并行度</span><b>{{ output.max_parallel || '—' }}</b></div>
        <div><span>可见实体 / 行动</span><b>{{ output.entities?.length || 0 }} / {{ output.actions?.length || 0 }}</b></div>
      </div>
      <section><h4>允许访问的 Store</h4><div class="tags"><el-tag v-for="s in output.collection?.allowed_stores || []" :key="s" effect="plain">{{ s }}</el-tag></div></section>
      <section><h4>冻结的活动代次</h4><div class="tags"><el-tag v-for="(generation,store) in output.collection?.generation_scope || {}" :key="store" type="success" effect="plain">{{ store }} → {{ generation }}</el-tag></div></section>
      <section><h4>查询预算</h4><div class="budget-list">
        <span>最多实体 <b>{{ output.budgets?.max_entities || 0 }}</b></span>
        <span>最多依据块 <b>{{ output.budgets?.max_blocks || 0 }}</b></span>
        <span>最多 Token <b>{{ (output.budgets?.max_tokens || 0).toLocaleString('zh-CN') }}</b></span>
      </div></section>
      <section><h4>可用文档类别</h4><div class="tags"><el-tag v-for="c in output.categories || []" :key="c" type="warning" effect="light">{{ c }}</el-tag></div></section>
      <section><h4>可见文档（{{ output.documents?.length || 0 }}）</h4><div class="document-list">
        <div v-for="d in output.documents || []" :key="`${d.store_id}:${d.document_version_id}`"><b>{{ d.title || d.document_id }}</b><small>{{ d.category }} · {{ d.document_id }} · {{ d.block_count }} 块</small></div>
      </div></section>
      <section><h4>可见实体类型</h4><div class="tags"><el-tag v-for="x in entityTypeCounts" :key="x.type" type="info" effect="light">{{ x.type }} · {{ x.count }}</el-tag></div></section>
    </div>

    <div v-else-if="stage?.stage_id === 'coordinator'" class="coordinator-view">
      <div class="metrics"><div><b>{{ facts.length }}</b><span>事实项</span></div><div><b>{{ evidence.length }}</b><span>依据块</span></div><div v-if="evidenceGroups.length"><b>{{ evidenceGroups.length }}</b><span>文档分组</span></div></div>
      <div v-if="evidenceGroups.length" class="evidence-groups">
        <section v-for="group in evidenceGroups" :key="group.key" class="evidence-group">
          <h4>{{ group.label }} <el-tag size="small" effect="plain">{{ group.items?.length || 0 }} 条</el-tag></h4>
          <div class="result-list"><div v-for="(b,i) in group.items || []" :key="b.block_key || i" class="evidence-item">
            <b>{{ b.title || b.block_key }}</b><small>{{ b.heading_path }} · {{ b.block_key }}</small><p>{{ snippet(b.quote || b.text) }}</p>
          </div></div>
        </section>
      </div>
      <div v-else class="result-columns">
        <section><h4>结构化事实</h4><div v-if="!facts.length" class="empty">没有事实结果</div>
          <div class="result-list"><div v-for="(f,i) in facts" :key="f.fact_key || f.assertion_id || f.action_id || f.entity_id || i" class="fact-item">
            <el-tag v-if="f.fact_kind || f.type" size="small" effect="plain">{{ f.fact_kind || f.type }}</el-tag><b>{{ f.name || f.action_text || f.canonical_text || f.predicate || '未命名结果' }}</b>
            <small>{{ f.assertion_id || f.action_id || f.entity_id || '' }}<template v-if="f.modality"> · {{ f.modality }}</template></small>
          </div></div>
        </section>
        <section><h4>原文依据</h4><div v-if="!evidence.length" class="empty">没有原文依据</div>
          <div class="result-list"><div v-for="(b,i) in evidence" :key="`${b.assertion_id || ''}:${b.block_key || i}`" class="evidence-item">
            <b>{{ b.title || b.block_key }}</b><small>{{ b.assertion_id || '原文块' }} · {{ b.block_key }}</small><p>{{ snippet(b.quote || b.text) }}</p>
          </div></div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { QueryCitation, QueryNodeState, QueryStageState } from '../../backend/Query.js'
import AnswerPanel from './AnswerPanel.vue'
import PlanDagView from './PlanDagView.vue'

const props=withDefaults(defineProps<{stage:QueryStageState|null;nodes?:QueryNodeState[];runAnswer?:string|null;citations?:QueryCitation[]}>(),{nodes:()=>[],citations:()=>[]})
const output=computed<any>(()=>parse(props.stage?.output)||{})
const outputTitle=computed(()=>({initializer:'QueryContext',compiler:'SQG · 业务意图图',optimizer:'PEP · 物理执行图',coordinator:'事实与原文依据',generator:'最终答案'} as Record<string,string>)[props.stage?.stage_id||'']||'阶段输出')
const facts=computed<any[]>(()=>output.value.facts?.items||[])
const evidence=computed<any[]>(()=>output.value.evidence?.items||[])
const evidenceGroups=computed<any[]>(()=>output.value.evidence?.groups||output.value.facts?.groups||[])
const entityTypeCounts=computed(()=>{const c:Record<string,number>={};for(const x of output.value.entities||[])c[x.entity_type]=(c[x.entity_type]||0)+1;return Object.entries(c).map(([type,count])=>({type,count})).sort((a,b)=>b.count-a.count)})
function parse(raw?:string|null):any{if(!raw)return null;try{return JSON.parse(raw)}catch{return null}}
function formatCost(ms:number){return ms<1000?`${ms}ms`:`${(ms/1000).toFixed(1)}s`}
function selectionLabel(s?:string){return({user:'用户指定',user_default:'用户默认',only_visible:'唯一可见',semantic_router:'语义选择'}as Record<string,string>)[s||'']||'—'}
function snippet(s?:string){if(!s)return '—';return s.length>150?s.slice(0,150)+'…':s}
</script>

<style scoped>
.output-view{padding:16px;border:1px solid var(--beone-border);border-radius:11px;background:#fff}.output-head{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px}.output-head span{color:var(--beone-text-secondary);font-size:10px}.output-head h3{margin:2px 0 0;font-size:15px;color:var(--beone-midnight-blue)}.cost{padding:3px 7px;border-radius:5px;background:var(--beone-bg-panel)}
.context-question{display:flex;flex-direction:column;gap:4px;padding:12px;border-radius:9px;background:#edf6fd}.context-question span,.context-grid span{color:var(--beone-text-secondary);font-size:9px}.context-question b{font-size:13px}.context-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:9px}.context-grid>div{display:flex;flex-direction:column;gap:3px;padding:10px;border-radius:8px;background:#f5f7fa}.context-grid b{font-size:13px}.output-view section{margin-top:14px}.output-view h4{margin:0 0 7px;font-size:11px;color:var(--beone-midnight-blue)}.tags{display:flex;flex-wrap:wrap;gap:6px}.budget-list{display:flex;gap:9px}.budget-list span{padding:7px 10px;border-radius:7px;background:#f5f7fa;color:var(--beone-text-secondary);font-size:10px}.budget-list b{color:#263b51}.document-list{display:grid;grid-template-columns:1fr 1fr;gap:6px}.document-list>div{display:flex;flex-direction:column;gap:2px;padding:8px;border-radius:7px;background:#f5f7fa}.document-list b{font-size:10px}.document-list small{color:var(--beone-text-secondary);font-size:8px;word-break:break-all}
.metrics{display:flex;gap:9px}.metrics>div{min-width:115px;padding:12px;border-radius:9px;background:#edf6fd}.metrics b{display:block;color:#2f7cb4;font-size:22px}.metrics span{font-size:10px;color:var(--beone-text-secondary)}.result-columns{display:grid;grid-template-columns:1fr 1.2fr;gap:12px}.evidence-groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.evidence-group{padding:11px;border:1px solid #dce6ef;border-radius:9px;background:#fafcfe}.evidence-group h4{display:flex;align-items:center;justify-content:space-between}.result-list{max-height:360px;overflow:auto}.fact-item,.evidence-item{display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:8px;border-bottom:1px solid #edf0f3}.fact-item b,.evidence-item b{font-size:11px}.fact-item small,.evidence-item small{width:100%;color:var(--beone-text-secondary);font-size:9px;word-break:break-all}.evidence-item p{margin:0;color:#52677d;font-size:10px;line-height:1.5}.empty{padding:16px;color:var(--beone-text-secondary);font-size:10px;text-align:center}
</style>
