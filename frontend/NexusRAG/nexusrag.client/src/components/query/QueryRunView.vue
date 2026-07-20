<template>
  <div class="run-view">
    <div class="run-head">
      <div class="run-identity">
        <span class="state-dot" :style="{ background: stateColor(run?.state) }"></span>
        <b>{{ stateLabel(run?.state) }}</b>
        <button v-if="run?.run_id" type="button" class="run-id" :title="run.run_id" @click="copyRunId">
          Run ID · {{ shortRunId }}
          <el-icon><CopyDocument /></el-icon>
        </button>
        <span v-if="run?.collection_name" class="meta">Collection：{{ run.collection_name }}</span>
        <span class="meta">节点 {{ run?.node_count || 0 }}</span>
      </div>
      <el-button v-if="run?.state === 'running'" size="small" type="danger" plain @click="cancel">取消</el-button>
    </div>

    <div class="token-bar" :class="{ 'is-live': run?.state === 'running' }">
      <div class="token-title"><el-icon><Coin /></el-icon><span>Token 实时消耗</span></div>
      <span>输入 <b>{{ fmt(tokens.input) }}</b></span>
      <span v-if="tokens.cached">缓存 <b>{{ fmt(tokens.cached) }}</b></span>
      <span>输出 <b>{{ fmt(tokens.output) }}</b></span>
      <span>向量 <b>{{ fmt(tokens.embedding) }}</b></span>
      <span class="token-total">合计 <b>{{ fmt(tokenTotal) }}</b></span>
    </div>

    <el-alert v-if="run?.error" :title="run.error" type="error" :closable="false" show-icon />

    <div class="stage-flow-wrap">
      <div class="stage-flow">
        <template v-for="(s, index) in stages" :key="s.stage_id">
          <div
            class="stage-card"
            :class="[
              `stage--${s.state}`,
              {
                'selected-stage': selectedStageId === s.stage_id && detailMode === 'summary',
                'selected-output-source': selectedStageId === s.stage_id && detailMode === 'output',
              },
            ]"
            role="button"
            tabindex="0"
            :aria-pressed="selectedStageId === s.stage_id && detailMode === 'summary'"
            @click="selectSummary(s)"
            @keydown.enter.prevent="selectSummary(s)"
            @keydown.space.prevent="selectSummary(s)"
          >
            <span class="stage-icon"><el-icon><component :is="stageIcon(s.stage_id)" /></el-icon></span>
            <span class="stage-body"><b :title="s.name">{{ s.name }}</b><small>{{ stateLabel(s.state) }}</small></span>
            <span v-if="stageTokenTotal(s)" class="stage-token">{{ fmt(stageTokenTotal(s)) }}</span>
            <button
              v-if="s.stage_id === 'generator' && s.output"
              type="button"
              class="inside-output"
              :class="{ selected: selectedStageId === s.stage_id && detailMode === 'output' }"
              @click.stop="selectOutput(s)"
            >查看答案</button>
          </div>

          <div
            v-if="index < stages.length - 1"
            class="stage-connector"
            :class="{ 'selected-output': selectedStageId === s.stage_id && detailMode === 'output' }"
          >
            <span class="connector-line"></span>
            <button
              type="button"
              class="output-chip"
              :class="{
                ready: !!s.output,
                selected: selectedStageId === s.stage_id && detailMode === 'output',
              }"
              :disabled="!s.output"
              :aria-pressed="selectedStageId === s.stage_id && detailMode === 'output'"
              @click.stop="selectOutput(s)"
            >{{ outputLabel(s.stage_id) }}</button>
          </div>
        </template>
      </div>
    </div>

    <transition name="stage-detail" mode="out-in">
      <StageSummaryView v-if="selectedStage && detailMode === 'summary'" :key="`${selectedStage.stage_id}-summary`"
                        :stage="selectedStage" :nodes="nodes" :run-answer="run?.answer" :citations="citations" />
      <StageOutputView v-else-if="selectedStage" :key="`${selectedStage.stage_id}-output`"
                       :stage="selectedStage" :nodes="nodes" :run-answer="run?.answer" :citations="citations" />
      <div v-else key="empty" class="output-placeholder">点击阶段查看摘要；点击阶段之间的输出标签查看产物。</div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ChatDotRound, Coin, Connection, CopyDocument, EditPen, MagicStick, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { cancelQuery, getQueryRun, type QueryNodeState, type QueryRunInfo, type QueryStageState } from '../../backend/Query.js'
import StageSummaryView from './StageSummaryView.vue'
import StageOutputView from './StageOutputView.vue'

const props = defineProps<{ runId: string }>()
const run = ref<QueryRunInfo | null>(null)
const nodes = ref<QueryNodeState[]>([])
const stages = ref<QueryStageState[]>([])
const selectedStageId = ref<string | null>(null)
const detailMode = ref<'summary'|'output'>('summary')
const lastAutoStageId = ref<string | null>(null)
let timer: number | undefined

const tokens = computed<Record<string,number>>(() => parseJson(run.value?.tokens) || {})
const tokenTotal = computed(() => (tokens.value.input || 0) + (tokens.value.output || 0) + (tokens.value.embedding || 0))
const citations = computed(() => parseJson(run.value?.citations) || [])
const selectedStage = computed(() => stages.value.find(s => s.stage_id === selectedStageId.value) || null)
const shortRunId = computed(() => run.value?.run_id ? `${run.value.run_id.slice(0,8)}…` : '')

watch(() => props.runId, start, { immediate: true })
onBeforeUnmount(stop)

function start() {
  stop(); run.value=null; nodes.value=[]; stages.value=[]; selectedStageId.value=null
  detailMode.value='summary'; lastAutoStageId.value=null
  if (!props.runId) return
  void poll(); timer=window.setInterval(poll,5000)
}
function stop() { if (timer) { window.clearInterval(timer); timer=undefined } }
async function poll() {
  try {
    const data=await getQueryRun(props.runId)
    run.value=data.run; nodes.value=data.nodes || []; stages.value=data.stages || []
    const latestOutput=stages.value.filter(s=>!!s.output).sort((a,b)=>b.ordinal-a.ordinal)[0]
    if (latestOutput && latestOutput.stage_id !== lastAutoStageId.value) {
      selectedStageId.value=latestOutput.stage_id
      detailMode.value='output'
      lastAutoStageId.value=latestOutput.stage_id
    }
    if (['succeeded','failed','cancelled'].includes(data.run.state)) stop()
  } catch { /* run 行可能正在创建，继续轮询 */ }
}
function selectOutput(stage: QueryStageState) {
  if (!stage.output) return
  selectedStageId.value=stage.stage_id; detailMode.value='output'
}
function selectSummary(stage: QueryStageState) { selectedStageId.value=stage.stage_id; detailMode.value='summary' }
async function cancel() { await cancelQuery(props.runId) }
async function copyRunId() {
  if (!run.value?.run_id) return
  await navigator.clipboard.writeText(run.value.run_id)
  ElMessage.success('Run ID 已复制')
}
function parseJson(raw?: string | null): any { if (!raw) return null; try { return JSON.parse(raw) } catch { return null } }
function fmt(n?: number) { return (n || 0).toLocaleString('zh-CN') }
function stageTokenTotal(s: QueryStageState) { const t=parseJson(s.tokens)||{}; return (t.input||0)+(t.output||0)+(t.embedding||0) }
function stateColor(s?: string | null) { return ({running:'#2f7cb4',succeeded:'#2e9b5b',failed:'#d52b1e',cancelled:'#97a3ae',skipped:'#97a3ae',pending:'#c4cbd1'} as Record<string,string>)[s || ''] || '#c4cbd1' }
function stateLabel(s?: string | null) { return ({running:'运行中',succeeded:'完成',failed:'失败',cancelled:'已取消',skipped:'已跳过',pending:'等待'} as Record<string,string>)[s || ''] || '准备中' }
function outputLabel(id: string) { return ({initializer:'QueryContext',compiler:'SQG',optimizer:'PEP',coordinator:'事实 + 依据'} as Record<string,string>)[id] || '输出' }
function stageIcon(id: string) { return ({initializer:Setting,compiler:EditPen,optimizer:MagicStick,coordinator:Connection,generator:ChatDotRound} as Record<string,any>)[id] || Setting }
</script>

<style scoped>
.run-view { display:flex; flex-direction:column; gap:14px; }
.run-head { display:flex; align-items:center; justify-content:space-between; }
.run-identity { display:flex; align-items:center; gap:8px; }
.state-dot { width:9px; height:9px; border-radius:50%; }
.meta { color:var(--beone-text-secondary); font-size:12px; }
.run-id { display:inline-flex; align-items:center; gap:4px; padding:3px 7px; border:1px solid #d6e1eb; border-radius:6px; background:#f7f9fc; color:#60758a; font-size:9px; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; cursor:pointer; }
.run-id:hover { border-color:#82b8d9; background:#edf6fd; color:#2f7cb4; }
.token-bar { display:flex; align-items:center; gap:18px; padding:9px 12px; border:1px solid #cfe2f2; border-radius:8px; background:linear-gradient(90deg,#edf6fd,#f3fbfc); color:#536b82; font-size:11px; font-variant-numeric:tabular-nums; }
.token-title { display:flex; align-items:center; gap:6px; color:#2f7cb4; font-weight:700; }
.token-bar b { color:#1f3b55; }
.token-total { margin-left:auto; padding-left:14px; border-left:1px solid #cadde9; }
.token-bar.is-live .token-title:after { content:''; width:6px; height:6px; border-radius:50%; background:#2e9b5b; animation:pulse 1.2s infinite; }
@keyframes pulse { 50% { opacity:.35; transform:scale(.75); } }
.stage-flow-wrap { overflow-x:auto; padding:8px 5px 18px; }
.stage-flow { width:100%; min-width:1240px; display:flex; align-items:center; }
.stage-card { box-sizing:border-box; position:relative; width:174px; min-height:88px; flex:0 0 174px; display:flex; align-items:center; gap:10px; padding:18px 12px 13px; overflow:visible; border:1px solid #d9e4ee; border-radius:13px; background:#fbfcfe; text-align:left; color:inherit; cursor:pointer; transition:border-color .15s,box-shadow .15s,background .15s,transform .15s; }
.stage-card:hover { border-color:#a9c8de; background:#f8fbfd; }
.stage-card:focus-visible { outline:2px solid rgba(47,124,180,.45); outline-offset:2px; }
.stage-card.selected-stage { border-color:#2f7cb4; background:#edf7fd; box-shadow:0 0 0 3px rgba(47,124,180,.16),0 7px 18px rgba(47,124,180,.10); transform:translateY(-1px); }
.stage-card.selected-output-source { border-color:#79afd2; background:#f4fafe; box-shadow:inset 0 0 0 1px rgba(47,124,180,.10); }
.stage-icon { width:36px; height:36px; flex:0 0 36px; display:grid; place-items:center; border-radius:10px; background:#eef2f6; color:#8291a0; font-size:16px; }
.stage-body { min-width:0; flex:1 1 auto; display:flex; flex-direction:column; gap:3px; overflow:hidden; }
.stage-body b { display:-webkit-box; overflow:hidden; color:#203246; font-size:12px; line-height:1.35; overflow-wrap:anywhere; -webkit-box-orient:vertical; -webkit-line-clamp:2; }
.stage-body small { font-size:10px; color:#8190a0; }
.stage-token { position:absolute; right:8px; top:6px; max-width:76px; overflow:hidden; color:#7b8b9b; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }
.inside-output { position:absolute; left:50%; bottom:-12px; padding:3px 10px; border:1px solid #b9ddc9; border-radius:9px; background:#e7f4ed; color:#2e9b5b; font-size:9px; white-space:nowrap; cursor:pointer; transform:translateX(-50%); transition:.15s; }
.inside-output.selected { border-color:#2f7cb4; background:#2f7cb4; color:#fff; box-shadow:0 0 0 3px rgba(47,124,180,.15); }
.stage--running { border-color:#9bc5e1; background:#f0f8fd; }
.stage--running .stage-icon { background:#dceefa; color:#2f7cb4; }
.stage--succeeded .stage-icon { background:#e5f5ec; color:#2e9b5b; }
.stage--failed .stage-icon { background:#fdeceb; color:#d52b1e; }
.stage-connector { position:relative; min-width:96px; height:88px; flex:1 1 120px; display:flex; align-items:center; justify-content:center; }
.connector-line { position:absolute; left:0; right:7px; top:50%; height:2px; background:#d2dce6; transform:translateY(-50%); transition:.15s; }
.stage-connector::after { content:''; position:absolute; right:0; top:50%; width:0; height:0; border-top:5px solid transparent; border-bottom:5px solid transparent; border-left:7px solid #9baaba; transform:translateY(-50%); }
.stage-connector.selected-output .connector-line { height:3px; background:#2f7cb4; box-shadow:0 0 8px rgba(47,124,180,.28); }
.stage-connector.selected-output::after { border-left-color:#2f7cb4; }
.output-chip { box-sizing:border-box; position:relative; z-index:1; max-width:112px; overflow:hidden; padding:4px 10px; border:1px solid #d5e0ea; border-radius:11px; background:#fff; color:#8a98a7; font-size:9px; line-height:15px; text-overflow:ellipsis; white-space:nowrap; transition:.15s; }
.output-chip.ready { border-color:#9cc7e2; color:#2f7cb4; cursor:pointer; box-shadow:0 2px 7px rgba(47,124,180,.1); }
.output-chip.selected { border-color:#2f7cb4; background:#2f7cb4; color:#fff; font-weight:700; box-shadow:0 0 0 3px rgba(47,124,180,.15),0 4px 10px rgba(47,124,180,.18); }
.output-placeholder { min-height:170px; display:flex; align-items:center; justify-content:center; border:1px dashed var(--beone-border); border-radius:10px; color:var(--beone-text-secondary); font-size:12px; }
.stage-detail-enter-active, .stage-detail-leave-active { transition:opacity .22s ease, transform .22s ease; }
.stage-detail-enter-from { opacity:0; transform:translateX(14px); }
.stage-detail-leave-to { opacity:0; transform:translateX(-10px); }
</style>
