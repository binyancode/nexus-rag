<template>
  <aside class="history-panel">
    <div class="history-head">
      <div><b>查询历史</b><span>{{ filtered.length }}</span></div>
      <el-button link :loading="loading" @click="load">刷新</el-button>
    </div>
    <el-input v-model="keyword" size="small" clearable placeholder="模糊搜索问题，或输入完整 Run ID" class="history-search" />
    <div class="history-list">
      <button v-for="item in filtered" :key="item.run_id" type="button" class="history-item"
              :class="{ selected:item.run_id===selectedRunId }" @click="$emit('select',item)">
        <span class="item-top"><i :style="{background:stateColor(item.state)}"></i><small>{{ stateLabel(item.state) }}</small><time>{{ shortTime(item.created_at) }}</time></span>
        <b :title="item.question || ''">{{ item.question || '未命名查询' }}</b>
        <span class="item-meta"><span>{{ item.collection_name || '未选择 Collection' }}</span><span>{{ tokenTotal(item.tokens).toLocaleString('zh-CN') }} tokens</span></span>
        <p v-if="item.answer || item.error" :class="{error:!!item.error}">{{ item.answer || item.error }}</p>
      </button>
      <div v-if="!loading && !filtered.length" class="history-empty">暂无匹配的查询记录</div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listQueryRuns, type QueryRunListItem } from '../../backend/Query.js'

defineProps<{ selectedRunId?:string }>()
defineEmits<{(e:'select',run:QueryRunListItem):void}>()
const items=ref<QueryRunListItem[]>([]),loading=ref(false),keyword=ref('')
const filtered=computed(()=>{
  const raw=keyword.value.trim()
  if(!raw)return items.value
  const exact=items.value.filter(x=>x.run_id===raw)
  if(exact.length)return exact
  const q=raw.toLocaleLowerCase()
  return items.value.filter(x=>(x.question||'').toLocaleLowerCase().includes(q)||(x.answer||'').toLocaleLowerCase().includes(q))
})
onMounted(load)
defineExpose({ reload:load })
async function load(){loading.value=true;try{items.value=await listQueryRuns()}catch{ElMessage.error('加载查询历史失败')}finally{loading.value=false}}
function parse(raw?:string|null){if(!raw)return{};try{return JSON.parse(raw)}catch{return{}}}
function tokenTotal(raw?:string|null){const t=parse(raw);return(t.input||0)+(t.output||0)+(t.embedding||0)}
function stateColor(s:string){return({running:'#2f7cb4',succeeded:'#2e9b5b',failed:'#d52b1e',cancelled:'#97a3ae'}as Record<string,string>)[s]||'#c4cbd1'}
function stateLabel(s:string){return({running:'运行中',succeeded:'完成',failed:'失败',cancelled:'已取消'}as Record<string,string>)[s]||s}
function shortTime(raw?:string|null){if(!raw)return'';const d=new Date(raw);return isNaN(d.getTime())?raw:d.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})}
</script>

<style scoped>
.history-panel{min-width:0;height:calc(100vh - 140px);display:flex;flex-direction:column;padding:13px;border:1px solid var(--beone-border);border-radius:10px;background:#fff}.history-head{display:flex;align-items:center;justify-content:space-between}.history-head>div{display:flex;align-items:center;gap:7px}.history-head b{font-size:13px;color:var(--beone-midnight-blue)}.history-head span{min-width:22px;padding:1px 6px;border-radius:9px;background:var(--beone-bg-panel);color:var(--beone-text-secondary);font-size:9px;text-align:center}.history-search{margin:10px 0}.history-list{flex:1;min-height:0;overflow:auto}.history-item{width:100%;display:flex;flex-direction:column;gap:5px;padding:9px;border:0;border-bottom:1px solid #edf0f3;border-radius:7px;background:transparent;color:inherit;text-align:left;cursor:pointer}.history-item:hover{background:#f4f8fb}.history-item.selected{background:#eaf4fb;box-shadow:inset 3px 0 #2f7cb4}.item-top{display:flex;align-items:center;gap:5px}.item-top i{width:7px;height:7px;border-radius:50%}.item-top small{font-size:8px;color:var(--beone-text-secondary)}.item-top time{margin-left:auto;font-size:8px;color:#9aa7b4}.history-item>b{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.item-meta{display:flex;justify-content:space-between;gap:6px;color:var(--beone-text-secondary);font-size:8px}.item-meta span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history-item p{display:-webkit-box;overflow:hidden;margin:1px 0 0;color:#62778c;font-size:9px;line-height:1.4;-webkit-box-orient:vertical;-webkit-line-clamp:2}.history-item p.error{color:#c24136}.history-empty{padding:28px 8px;text-align:center;color:var(--beone-text-secondary);font-size:10px}
</style>
