<template>
  <div class="query-page">
    <div class="query-head">
      <div><h1>检索台</h1><p>大模型编译业务意图，优化器生成物理计划，固定算子执行并逐条溯源。</p></div>
    </div>
    <div class="query-grid">
      <QueryHistoryPanel ref="historyPanel" :selected-run-id="runId" @select="openHistory" />

      <el-card class="query-form" shadow="never">
        <div class="field">
          <label>问题</label>
          <el-input v-model="form.question" type="textarea" :rows="5" resize="vertical"
                    placeholder="例如：IND 需要、但 NDA 不需要的法规有哪些？请给出原文依据。" />
        </div>
        <div class="field">
          <label>Collection</label>
          <el-select v-model="form.collection" clearable style="width:100%" placeholder="自动选择可见 Collection">
            <el-option v-for="c in collections" :key="c.collection_id" :value="c.collection_id"
                       :label="`${c.name}（${c.stores.length} stores）`" />
          </el-select>
          <span class="hint">未选择时由初始化器从可见 Collection 中自动选择；查询全程不能越过该范围。</span>
        </div>
        <div class="field">
          <label>LLM 凭据</label>
          <el-select v-model="form.llm_credential" filterable style="width:100%">
            <el-option v-for="c in llmCreds" :key="c.credential_name" :value="c.credential_name" :label="c.credential_name" />
          </el-select>
        </div>
        <div class="field">
          <label>Embedding 凭据</label>
          <el-select v-model="form.embedding_credential" filterable style="width:100%">
            <el-option v-for="c in embedCreds" :key="c.credential_name" :value="c.credential_name" :label="c.credential_name" />
          </el-select>
        </div>
        <div class="form-row">
          <div class="field"><label>并行度</label><el-input-number v-model="form.max_parallel" :min="1" :max="64" /></div>
          <div class="field"><label>最多依据块</label><el-input-number v-model="form.max_blocks" :min="1" :max="100" /></div>
        </div>
        <div class="field">
          <label>Temperature（可选）</label>
          <el-input v-model="form.temperature" placeholder="留空则不传；例如 0.2" />
          <span class="hint">不设置时后端不会传 temperature，直接使用模型默认值。</span>
        </div>
        <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">开始查询</el-button>
      </el-card>

      <el-card class="query-result" shadow="never">
        <div v-if="!runId" class="result-empty">提交问题后，在这里查看 SQG、PEP、执行进度和带出处答案。</div>
        <QueryRunView v-else :run-id="runId" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listCredentials, type CredentialListItem } from '../../bff/Credentials.js'
import { createQuery, listQueryCollections, type QueryCollection, type QueryRunListItem } from '../../backend/Query.js'
import QueryHistoryPanel from './QueryHistoryPanel.vue'
import QueryRunView from './QueryRunView.vue'

const credentials = ref<CredentialListItem[]>([])
const collections = ref<QueryCollection[]>([])
const submitting = ref(false)
const runId = ref('')
const historyPanel = ref<InstanceType<typeof QueryHistoryPanel> | null>(null)
const form = reactive({
  question: '', collection: '', llm_credential: '', embedding_credential: '',
  max_parallel: 8, max_blocks: 30, temperature: '',
})
const llmCreds = computed(() => credentials.value.filter(x => x.credential_type === 'azure_openai'))
const embedCreds = computed(() => credentials.value.filter(x => x.credential_type === 'azure_openai_embedding'))
const canSubmit = computed(() => !!form.question.trim() && !!form.llm_credential && !!form.embedding_credential)

onMounted(async () => {
  const [credentialResult, collectionResult] = await Promise.allSettled([
    listCredentials(), listQueryCollections(),
  ])
  if (credentialResult.status === 'fulfilled') {
    credentials.value = credentialResult.value
  } else {
    ElMessage.error('加载凭据列表失败')
  }
  if (collectionResult.status === 'fulfilled') {
    collections.value = collectionResult.value
    form.collection = collections.value.find(c => c.is_default)?.collection_id || ''
  } else {
    ElMessage.error('加载 Collection 列表失败')
  }
})

async function submit() {
  let temperature: number | undefined
  try {
    temperature = parseOptionalTemperature(form.temperature)
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'temperature 参数不合法')
    return
  }
  submitting.value = true
  try {
    const result = await createQuery({
      question: form.question.trim(), collection: form.collection || undefined,
      llm_credential: form.llm_credential, embedding_credential: form.embedding_credential,
      temperature,
      max_parallel: form.max_parallel,
      budgets: { max_blocks: form.max_blocks },
    })
    runId.value = result.run_id
    ElMessage.success('查询已提交')
    window.setTimeout(() => historyPanel.value?.reload(), 600)
  } catch { /* 拦截器已提示 */ }
  finally { submitting.value = false }
}

function parseOptionalTemperature(raw: string): number | undefined {
  const value = raw.trim()
  if (!value) {
    return undefined
  }
  const number = Number(value)
  if (!Number.isFinite(number) || number < 0 || number > 2) {
    throw new Error('Temperature 需在 0 到 2 之间')
  }
  return number
}
function openHistory(run: QueryRunListItem) {
  runId.value=run.run_id
  if (run.question) form.question=run.question
  if (run.collection_id) form.collection=run.collection_id
}
</script>

<style scoped>
.query-page { flex: 1; min-height: 0; overflow: auto; padding: 24px 28px; }
.query-head { display:flex; align-items:flex-start; justify-content:space-between; }
.query-head h1 { margin: 0 0 4px; font-size: 20px; }
.query-head p { margin: 0 0 18px; color: var(--beone-text-secondary); font-size: 13px; }
.query-grid { display:grid; grid-template-columns:minmax(220px,270px) minmax(290px,340px) minmax(0,1fr); gap:14px; align-items:start; }
.query-form, .query-result { border-color: var(--beone-border); }
.field { margin-bottom: 14px; }
.field label { display: block; margin-bottom: 6px; color: var(--beone-text-secondary); font-size: 12px; font-weight: 600; }
.hint { display: block; margin-top: 5px; color: var(--beone-text-secondary); font-size: 11px; line-height: 1.5; }
.form-row { display: flex; gap: 16px; }
.form-row .field { flex: 1; }
.result-empty { min-height: 420px; display: flex; align-items: center; justify-content: center; color: var(--beone-text-secondary); font-size: 13px; text-align: center; }
@media (max-width: 1250px) { .query-grid { grid-template-columns:240px minmax(280px,320px) minmax(520px,1fr); } }
</style>
