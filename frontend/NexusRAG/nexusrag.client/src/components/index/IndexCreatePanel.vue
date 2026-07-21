<template>
  <div class="idx-page">
    <div class="idx-head">
      <div>
        <h1>建立索引</h1>
        <p>有一份上传一份：新增文档会加入 Store，同类别同标题文档会被替换；系统仍以完整代次构建并原子发布。</p>
      </div>
    </div>

    <div class="idx-body">
      <!-- 左：配置 -->
      <el-card class="idx-card" shadow="never">
        <div class="sec-t">原文文件</div>
        <el-upload
          drag
          multiple
          :auto-upload="false"
          accept=".txt"
          :file-list="fileList"
          :on-change="onFileChange"
          :on-remove="onFileRemove"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽 .txt 到此，或<em>点击选择</em></div>
        </el-upload>
        <div v-if="files.length" class="file-categories">
          <div v-for="file in files" :key="file.filename" class="file-category-row">
            <span :title="file.filename">{{ file.filename }}</span>
            <el-select
              v-model="file.category"
              filterable
              allow-create
              default-first-option
              placeholder="文档类别"
              style="width:150px"
            >
              <el-option v-for="c in categoryOptions" :key="c" :value="c" :label="c" />
            </el-select>
          </div>
        </div>

        <div class="sec-t">凭据</div>
        <div class="fld">
          <label>大模型（抽取/归一）<span class="req">*</span></label>
          <el-select v-model="form.llm_credential" filterable placeholder="选择 Azure OpenAI 凭据" style="width:100%">
            <el-option v-for="c in llmCreds" :key="c.credential_name" :value="c.credential_name" :label="c.credential_name" />
          </el-select>
        </div>
        <div class="fld">
          <label>向量模型（Embedding）<span class="req">*</span></label>
          <el-select v-model="form.embedding_credential" filterable placeholder="选择 Embedding 凭据" style="width:100%">
            <el-option v-for="c in embedCreds" :key="c.credential_name" :value="c.credential_name" :label="c.credential_name" />
          </el-select>
        </div>
        <div class="fld">
          <label>AI Search（块存储）<span class="req">*</span></label>
          <el-select v-model="form.store_credential" filterable placeholder="选择 Azure AI Search 凭据" style="width:100%" @change="onStoreChange">
            <el-option v-for="c in searchCreds" :key="c.credential_name" :value="c.credential_name" :label="c.credential_name" />
          </el-select>
        </div>
        <div class="fld">
          <label>索引名<span class="req">*</span></label>
          <el-select
            v-model="form.index_name"
            filterable
            allow-create
            default-first-option
            :loading="indexLoading"
            :disabled="!form.store_credential"
            :placeholder="form.store_credential ? '选择已有索引，或输入新索引名' : '请先选择 AI Search 凭据'"
            style="width:100%"
          >
            <el-option v-for="ix in indexOptions" :key="ix" :value="ix" :label="ix" />
          </el-select>
          <div class="hint">选已有索引=写入该索引；输入新名=自动创建。</div>
        </div>

        <div class="sec-t">索引选项</div>
        <div class="fld">
          <label>Temperature（可选）</label>
          <el-input v-model="form.temperature" placeholder="留空则不传；例如 0.2" style="width:100%" />
          <div class="hint">不设置时后端不会传 temperature，直接使用模型默认值。</div>
        </div>
        <div class="fld">
          <label>默认类别<span class="req">*</span></label>
          <el-select
            v-model="form.category"
            filterable
            allow-create
            default-first-option
            placeholder="选择或输入，如 IND / NDA / IIT"
            style="width:100%"
          >
            <el-option v-for="c in categoryOptions" :key="c" :value="c" :label="c" />
          </el-select>
          <div class="hint">新增文件默认使用此类别；可在文件列表中逐份调整。</div>
        </div>
        <div class="fld generation-note">
          <b>文档级新增 / 替换</b>
          <span>未上传文档会从当前活动代次继承；本次文档按“类别 + 文件标题”新增或替换。质量门禁通过后才原子发布。</span>
        </div>
        <div class="fld">
          <label>并行度（DAG 同时执行的节点数）</label>
          <el-input-number v-model="form.max_parallel" :min="1" :max="64" :step="1" controls-position="right" style="width:140px" />
        </div>

        <div class="idx-actions">
          <el-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
            开始索引
          </el-button>
        </div>
      </el-card>

      <!-- 右：实时 DAG 运行图 -->
      <el-card class="idx-card idx-card--dag" shadow="never">
        <div class="sec-t">运行图（DAG）</div>
        <div v-if="!runId" class="idx-empty">
          <el-icon class="idx-empty-ic"><DataAnalysis /></el-icon>
          <span>提交后在此实时显示 DAG 节点执行与并行情况。</span>
        </div>
        <IndexDagView v-else :run-id="runId" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, DataAnalysis } from '@element-plus/icons-vue'
import { listCredentials, type CredentialListItem } from '../../bff/Credentials.js'
import { createIndex, listSearchIndexes, type IndexFile } from '../../backend/Index.js'
import IndexDagView from './IndexDagView.vue'

const categoryOptions = ['IND', 'NDA', 'IIT']

const creds = ref<CredentialListItem[]>([])
const llmCreds = computed(() => creds.value.filter(c => c.credential_type === 'azure_openai'))
const embedCreds = computed(() => creds.value.filter(c => c.credential_type === 'azure_openai_embedding'))
const searchCreds = computed(() => creds.value.filter(c => c.credential_type === 'azure_ai_search'))

const form = reactive({
  llm_credential: '', embedding_credential: '', store_credential: '',
  index_name: '', category: '', max_parallel: 8, temperature: '',
})

const fileList = ref<any[]>([])
const files = ref<IndexFile[]>([])

const indexOptions = ref<string[]>([])
const indexLoading = ref(false)

const submitting = ref(false)
const runId = ref('')

const canSubmit = computed(() =>
  files.value.length > 0 && form.llm_credential && form.embedding_credential &&
  form.store_credential && form.index_name.trim().length > 0 && form.category.trim().length > 0 &&
  files.value.every(file => String(file.category || form.category).trim().length > 0),
)

onMounted(async () => {
  try {
    creds.value = await listCredentials()
  } catch {
    ElMessage.error('加载凭据列表失败')
  }
})

async function onStoreChange(cred: string) {
  form.index_name = ''
  indexOptions.value = []
  if (!cred) return
  indexLoading.value = true
  try {
    const res = await listSearchIndexes(cred)
    indexOptions.value = res.indexes
    if (res.default) form.index_name = res.default
  } catch {
    /* 拦截器已提示 */
  } finally {
    indexLoading.value = false
  }
}

function onFileChange(file: any) {
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result ?? '')
    const existing = files.value.findIndex(f => f.filename === file.name)
    if (existing >= 0) files.value[existing] = { ...files.value[existing], filename: file.name, text }
    else files.value.push({ filename: file.name, text, category: form.category })
  }
  reader.readAsText(file.raw, 'UTF-8')
  fileList.value = fileList.value.filter(f => f.uid !== file.uid).concat(file)
}
function onFileRemove(file: any) {
  files.value = files.value.filter(f => f.filename !== file.name)
  fileList.value = fileList.value.filter(f => f.uid !== file.uid)
}

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
    const res = await createIndex({
      files: files.value,
      llm_credential: form.llm_credential,
      embedding_credential: form.embedding_credential,
      temperature,
      store_credential: form.store_credential,
      index_name: form.index_name || undefined,
      category: form.category.trim(),
      max_parallel: form.max_parallel,
    })
    runId.value = res.run_id
    ElMessage.success('索引任务已提交')
  } catch {
    /* 错误已由拦截器提示 */
  } finally {
    submitting.value = false
  }
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
</script>

<style scoped>
.idx-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  overflow: auto;
  color: var(--beone-text-primary);
}
.idx-head h1 { margin: 0 0 4px; font-size: 20px; }
.idx-head p { margin: 0 0 16px; color: var(--beone-text-secondary); font-size: 13px; }
.idx-body { display: grid; grid-template-columns: minmax(360px, 1fr) minmax(360px, 1fr); gap: 16px; align-items: start; }
.idx-card { border: 1px solid var(--beone-border); border-radius: 10px; }
.sec-t { font-weight: 600; font-size: 13px; margin: 14px 0 10px; color: var(--beone-midnight-blue); }
.sec-t:first-child { margin-top: 0; }
.fld { margin-bottom: 12px; }
.fld > label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--beone-text-secondary); }
.fld-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.fld-row > label { margin-bottom: 0; }
.req { color: var(--beone-autumn-leaf, #d97706); margin-left: 2px; }
.hint { font-size: 12px; color: var(--beone-text-secondary); }
.file-categories { margin: 10px 0 14px; display: flex; flex-direction: column; gap: 8px; }
.file-category-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.file-category-row > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.generation-note { padding: 10px 12px; border-radius: 8px; background: #f5f8fc; display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--beone-text-secondary); }
.generation-note b { color: var(--beone-midnight-blue); }
.idx-actions { margin-top: 16px; }

/* ---- 运行进度 ---- */
.idx-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; color: var(--beone-text-secondary); font-size: 13px; padding: 40px 0;
}
.idx-empty-ic { font-size: 34px; opacity: 0.4; }

/* DAG 卡片：让运行图填满卡片高度 */
.idx-card--dag :deep(.el-card__body) { display: flex; flex-direction: column; }
.idx-card--dag :deep(.dag) { flex: 1; }
</style>
