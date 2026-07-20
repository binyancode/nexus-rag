<template>
  <div class="docs-page">
    <div class="docs-head">
      <div>
        <h1>索引文档管理</h1>
        <p>查看当前活动索引中的文档、事实和原文块；删除操作通过新代次发布，不直接破坏线上数据。</p>
      </div>
      <div class="docs-actions">
        <el-select v-model="activeStore" filterable placeholder="选择 Store" style="width:220px" @change="loadDocuments">
          <el-option v-for="store in stores" :key="store.store_id" :label="store.name" :value="store.store_id" />
        </el-select>
        <el-button :loading="loading" @click="loadDocuments">刷新</el-button>
        <el-button
          type="danger"
          plain
          :disabled="!selected.length || selected.length >= documents.length || (!!deleteRunId && !deleteTerminal)"
          @click="removeSelected"
        >删除所选（{{ selected.length }}）</el-button>
      </div>
    </div>

    <el-card v-if="generation" class="generation-card" shadow="never">
      <div class="generation-main">
        <span class="generation-label">当前活动代次</span>
        <b>{{ generation.generation_id }}</b>
        <el-tag size="small" type="success">{{ generation.quality_state }}</el-tag>
        <span>发布于 {{ formatDate(generation.activated_at) }}</span>
      </div>
      <div class="generation-stats">
        <span><b>{{ generation.document_count }}</b> 文档</span>
        <span><b>{{ generation.block_count }}</b> 原文块</span>
        <span><b>{{ generation.assertion_count }}</b> 事实</span>
        <span><b>{{ generation.graph_edge_count }}</b> Graph 关系</span>
      </div>
    </el-card>

    <el-alert
      v-if="documents.length && selected.length >= documents.length"
      title="不能删除 Store 中的全部文档；至少保留一份文档。"
      type="warning"
      :closable="false"
      show-icon
    />

    <el-card class="documents-card" shadow="never" v-loading="loading">
      <el-table
        :data="filteredDocuments"
        row-key="document_id"
        height="100%"
        @selection-change="onSelectionChange"
        @row-click="openDetail"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column label="文档" min-width="260">
          <template #header>
            <div class="title-filter">
              <span>文档</span>
              <el-input v-model="keyword" size="small" clearable placeholder="搜索标题或类别" style="width:190px" />
            </div>
          </template>
          <template #default="{ row }">
            <div class="document-name">
              <b>{{ row.title }}</b>
              <small>{{ row.document_id }}</small>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="90" />
        <el-table-column label="健康" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="healthType(row.health)">{{ healthLabel(row.health) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="manifest_blocks" label="原文块" width="88" align="right" />
        <el-table-column prop="assertions" label="事实" width="78" align="right" />
        <el-table-column prop="graph_edges" label="关系" width="78" align="right" />
        <el-table-column label="隔离/失败" width="100" align="right">
          <template #default="{ row }">{{ row.quarantined_blocks }} / {{ row.failed_blocks }}</template>
        </el-table-column>
        <el-table-column label="内容版本" width="120">
          <template #default="{ row }"><code>{{ shortHash(row.content_hash) }}</code></template>
        </el-table-column>
        <el-table-column label="操作" width="88" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <div class="empty-text">{{ activeStore ? '当前 Store 没有活动文档' : '请选择 Store' }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card v-if="deleteRunId" class="delete-run" shadow="never">
      <div class="delete-run-head">
        <div><b>文档删除运行</b><span>{{ deleteTerminal ? `运行已${deleteTerminal === 'failed' ? '失败' : '取消'}` : '正在构建不包含所选文档的新完整代次' }}</span></div>
        <div class="delete-run-tools">
          <code>{{ deleteRunId }}</code>
          <el-button v-if="deleteTerminal" size="small" @click="closeDeleteRun">关闭</el-button>
        </div>
      </div>
      <IndexDagView :run-id="deleteRunId" @terminal="onDeleteTerminal" />
    </el-card>

    <el-drawer v-model="detailOpen" size="68%" :title="detail?.title || '文档详情'">
      <div v-if="detail" class="detail-body">
        <div class="detail-meta">
          <div><span>类别</span><b>{{ detail.category }}</b></div>
          <div><span>原文块</span><b>{{ detail.manifest_blocks }}</b></div>
          <div><span>事实</span><b>{{ detail.assertions }}</b></div>
          <div><span>Graph 关系</span><b>{{ detail.graph_edges }}</b></div>
          <div><span>实体提及</span><b>{{ detail.entity_mentions }}</b></div>
          <div><span>行动提及</span><b>{{ detail.action_mentions }}</b></div>
        </div>
        <div class="detail-identities">
          <span>Document</span><code>{{ detail.document_id }}</code>
          <span>Version</span><code>{{ detail.document_version_id }}</code>
          <span>Hash</span><code>{{ detail.content_hash }}</code>
        </div>

        <section v-if="detail.quarantined_blocks" class="quarantine-section">
          <div class="blocks-title">
            <b>隔离项（{{ detail.quarantined_blocks }}）</b>
            <span>原文仍可检索，但未进入结构化事实和 Graph</span>
          </div>
          <el-alert
            title="隔离不是原文丢失：系统只是拒绝使用未通过校验的模型事实。"
            type="warning"
            :closable="false"
            show-icon
          />
          <div v-loading="quarantineLoading" class="quarantine-list">
            <article v-for="item in quarantined" :key="item.block_key" class="quarantine-item">
              <header>
                <div>
                  <b>{{ blockLocation(item) }}</b>
                  <span>模型尝试 {{ item.attempt_count || item.attempt_no }} 次</span>
                </div>
                <el-tag size="small" type="warning">已隔离</el-tag>
              </header>
              <div class="quarantine-reason"><b>隔离原因：</b>{{ item.reason }}</div>
              <div class="recognized-output">
                <div v-if="item.extracted_entities.length" class="recognized-group">
                  <b>识别的实体</b>
                  <div class="recognized-tags">
                    <el-tag v-for="entity in item.extracted_entities" :key="entity.local_id || entity.canonical_name || ''" size="small" effect="plain">
                      {{ entity.canonical_name || entity.mention_text }} · {{ entity.entity_type }}
                    </el-tag>
                  </div>
                </div>
                <div v-if="item.extracted_actions.length" class="recognized-group">
                  <b>识别的行动</b>
                  <ul>
                    <li v-for="action in item.extracted_actions" :key="action.local_id || action.canonical_text || ''">
                      <strong>{{ action.canonical_text }}</strong>
                      <span v-if="action.participants.length">（{{ actionParticipants(action.participants) }}）</span>
                    </li>
                  </ul>
                </div>
                <div v-if="item.candidate_assertions.length" class="recognized-group">
                  <b>被丢弃的候选事实</b>
                  <ul>
                    <li v-for="assertion in item.candidate_assertions" :key="assertion.local_id || assertion.predicate || ''">
                      <strong>{{ assertion.action || assertion.predicate }}</strong>
                      <span>：{{ assertion.rejection_reasons.join('、') || '未通过事实契约校验' }}</span>
                    </li>
                  </ul>
                </div>
              </div>
              <pre v-if="item.text">{{ item.text }}</pre>
              <details v-if="item.validation_messages.length || item.source_generation_id">
                <summary>查看技术详情</summary>
                <code v-if="item.source_generation_id">来源代次：{{ item.source_generation_id }}</code>
                <code v-if="item.attempt_state">最终尝试：#{{ item.attempt_no }} · {{ item.attempt_state }}</code>
                <code v-for="(message, index) in item.validation_messages" :key="index">{{ message }}</code>
              </details>
            </article>
          </div>
        </section>

        <div class="blocks-title">
          <b>索引原文（{{ blocksTotal }}）</b>
          <span>按文档结构顺序显示</span>
        </div>
        <div v-loading="blocksLoading" class="blocks-list">
          <article v-for="block in blocks" :key="block.block_key" class="block-item">
            <header>
              <b>{{ blockLocation(block) }}</b>
              <span>#{{ block.ordinal }}</span>
            </header>
            <pre>{{ block.text }}</pre>
            <details><summary>技术标识</summary><code>{{ block.block_key }}</code></details>
          </article>
          <div v-if="!blocksLoading && !blocks.length" class="empty-text">没有原文块</div>
        </div>
        <el-pagination
          v-if="blocksTotal > blockPageSize"
          v-model:current-page="blockPage"
          :page-size="blockPageSize"
          :total="blocksTotal"
          layout="prev, pager, next, total"
          @current-change="loadBlocks"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteIndexedDocuments,
  getIndexedDocument,
  listIndexedDocumentBlocks,
  listIndexedDocuments,
  listQuarantinedDocumentBlocks,
  listStores,
  type IndexedBlockInfo,
  type IndexedDocumentInfo,
  type IndexedGenerationInfo,
  type QuarantinedBlockInfo,
  type StoreInfo,
} from '../../backend/Index.js'
import IndexDagView from './IndexDagView.vue'

const stores = ref<StoreInfo[]>([])
const activeStore = ref('')
const generation = ref<IndexedGenerationInfo | null>(null)
const documents = ref<IndexedDocumentInfo[]>([])
const selected = ref<IndexedDocumentInfo[]>([])
const keyword = ref('')
const loading = ref(false)
const deleteRunId = ref('')
const deleteTerminal = ref('')

const detailOpen = ref(false)
const detail = ref<IndexedDocumentInfo | null>(null)
const blocks = ref<IndexedBlockInfo[]>([])
const blocksLoading = ref(false)
const blocksTotal = ref(0)
const blockPage = ref(1)
const blockPageSize = 10
const quarantined = ref<QuarantinedBlockInfo[]>([])
const quarantineLoading = ref(false)

const filteredDocuments = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase()
  if (!query) return documents.value
  return documents.value.filter(item =>
    item.title.toLocaleLowerCase().includes(query)
    || item.category.toLocaleLowerCase().includes(query)
    || item.document_id.toLocaleLowerCase().includes(query),
  )
})

onMounted(async () => {
  try {
    stores.value = await listStores()
    activeStore.value = stores.value.find(item => item.is_default)?.store_id
      || stores.value.find(item => item.active_generation_id)?.store_id
      || stores.value[0]?.store_id
      || ''
    if (activeStore.value) await loadDocuments()
  } catch {
    /* 全局请求拦截器提示 */
  }
})

async function loadDocuments() {
  if (!activeStore.value) return
  loading.value = true
  selected.value = []
  try {
    const data = await listIndexedDocuments(activeStore.value)
    generation.value = data.generation
    documents.value = data.documents || []
  } catch {
    generation.value = null
    documents.value = []
  } finally {
    loading.value = false
  }
}

function onSelectionChange(rows: IndexedDocumentInfo[]) { selected.value = rows }

async function openDetail(row: IndexedDocumentInfo) {
  if (!activeStore.value) return
  detailOpen.value = true
  detail.value = row
  blocks.value = []
  quarantined.value = []
  blockPage.value = 1
  try {
    const data = await getIndexedDocument(activeStore.value, row.document_id)
    detail.value = data.document
    await Promise.all([loadBlocks(), loadQuarantined()])
  } catch {
    detailOpen.value = false
  }
}

async function loadQuarantined() {
  if (!activeStore.value || !detail.value || !detail.value.quarantined_blocks) return
  quarantineLoading.value = true
  try {
    const data = await listQuarantinedDocumentBlocks(activeStore.value, detail.value.document_id)
    quarantined.value = data.items || []
  } finally {
    quarantineLoading.value = false
  }
}

async function loadBlocks() {
  if (!activeStore.value || !detail.value) return
  blocksLoading.value = true
  try {
    const data = await listIndexedDocumentBlocks(
      activeStore.value, detail.value.document_id, blockPage.value, blockPageSize,
    )
    blocks.value = data.items || []
    blocksTotal.value = data.total || 0
  } finally {
    blocksLoading.value = false
  }
}

async function removeSelected() {
  if (!generation.value || !selected.value.length || !activeStore.value) return
  const titles = selected.value.map(item => `《${item.title}》`).join('、')
  const assertionCount = selected.value.reduce((sum, item) => sum + item.assertions, 0)
  const edgeCount = selected.value.reduce((sum, item) => sum + item.graph_edges, 0)
  try {
    await ElMessageBox.confirm(
      `将删除 ${titles}。新索引将排除这些文档，并重新生成事实与 Graph；预计影响 ${assertionCount} 条事实、${edgeCount} 条关系。历史代次仍保留。`,
      '确认删除索引文档',
      { confirmButtonText: '创建删除运行', cancelButtonText: '取消', type: 'warning' },
    )
    const result = await deleteIndexedDocuments({
      store_id: activeStore.value,
      document_ids: selected.value.map(item => item.document_id),
      expected_generation_id: generation.value.generation_id,
      reason: '管理员从文档管理页面删除',
    })
    deleteRunId.value = result.run_id
    deleteTerminal.value = ''
    ElMessage.success('删除运行已提交；当前活动索引在新代次发布前保持不变')
  } catch (error: any) {
    if (error === 'cancel' || error === 'close') return
  }
}

async function onDeleteTerminal(state: string) {
  deleteTerminal.value = state
  if (state === 'succeeded') {
    ElMessage.success('文档删除完成，活动索引已更新')
    deleteRunId.value = ''
    deleteTerminal.value = ''
    await loadDocuments()
  } else if (state === 'failed') {
    ElMessage.error('文档删除运行失败，当前活动索引未改变')
  } else {
    ElMessage.warning('文档删除运行已取消，当前活动索引未改变')
  }
}

function closeDeleteRun() {
  deleteRunId.value = ''
  deleteTerminal.value = ''
}

function healthType(health: IndexedDocumentInfo['health']): 'success'|'warning'|'danger' {
  return health === 'healthy' ? 'success' : health === 'warning' ? 'warning' : 'danger'
}
function healthLabel(health: IndexedDocumentInfo['health']) {
  return ({ healthy: '正常', warning: '有隔离项', degraded: '异常' } as const)[health]
}
function shortHash(value: string) { return value ? `${value.slice(0, 10)}…` : '—' }
function formatDate(value?: string | null) { return value ? new Date(value).toLocaleString('zh-CN') : '—' }
function blockLocation(block: IndexedBlockInfo | QuarantinedBlockInfo) {
  const parts = [block.heading_path]
  if (block.article_no) parts.push(`第${block.article_no}条`)
  if (block.paragraph_no) parts.push(`第${block.paragraph_no}款`)
  if (block.item_no) parts.push(`第${block.item_no}项`)
  return parts.filter(Boolean).join(' · ') || `原文块 ${block.ordinal}`
}
function actionParticipants(participants: Array<{role:string|null;value:string|null}>) {
  return participants.map(item => `${item.role || '参与者'}：${item.value || '未识别'}`).join('；')
}
</script>

<style scoped>
.docs-page { flex:1; min-height:0; display:flex; flex-direction:column; gap:14px; padding:20px 24px; overflow:auto; color:var(--beone-text-primary); }
.docs-head { display:flex; align-items:flex-start; justify-content:space-between; gap:20px; }
.docs-head h1 { margin:0 0 4px; font-size:20px; }
.docs-head p { margin:0; color:var(--beone-text-secondary); font-size:13px; }
.docs-actions { display:flex; align-items:center; gap:8px; }
.generation-card { flex:0 0 auto; }
.generation-card :deep(.el-card__body) { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:12px 16px; }
.generation-main,.generation-stats { display:flex; align-items:center; gap:12px; min-width:0; font-size:12px; color:var(--beone-text-secondary); }
.generation-main b { overflow:hidden; color:var(--beone-midnight-blue); font-family:ui-monospace,Consolas,monospace; text-overflow:ellipsis; white-space:nowrap; }
.generation-label { font-weight:700; color:var(--beone-text-primary); }
.generation-stats b { margin-right:3px; color:var(--beone-midnight-blue); font-size:15px; }
.documents-card { min-height:420px; height:calc(100vh - 280px); flex:1 0 420px; }
.documents-card :deep(.el-card__body) { height:100%; box-sizing:border-box; padding:0; }
.title-filter { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.document-name { display:flex; flex-direction:column; gap:3px; min-width:0; cursor:pointer; }
.document-name b { overflow:hidden; color:#203246; text-overflow:ellipsis; white-space:nowrap; }
.document-name small { overflow:hidden; color:#8a98a7; font-size:10px; font-family:ui-monospace,Consolas,monospace; text-overflow:ellipsis; white-space:nowrap; }
.empty-text { padding:28px; color:var(--beone-text-secondary); text-align:center; }
.delete-run { flex:0 0 auto; }
.delete-run-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; }
.delete-run-head > div { display:flex; flex-direction:column; gap:3px; }
.delete-run-head span { color:var(--beone-text-secondary); font-size:12px; }
.delete-run-head code { color:#6d7f91; font-size:10px; }
.delete-run-tools { display:flex; align-items:center; gap:10px; }
.detail-body { display:flex; flex-direction:column; gap:16px; }
.detail-meta { display:grid; grid-template-columns:repeat(6,minmax(90px,1fr)); gap:10px; }
.detail-meta > div { display:flex; flex-direction:column; gap:5px; padding:10px 12px; border:1px solid #e1e8ef; border-radius:8px; background:#f8fafc; }
.detail-meta span { color:var(--beone-text-secondary); font-size:11px; }
.detail-meta b { color:var(--beone-midnight-blue); font-size:17px; }
.detail-identities { display:grid; grid-template-columns:72px 1fr; gap:5px 10px; padding:10px 12px; border-radius:8px; background:#f5f7fa; }
.detail-identities span { color:#7f8e9d; font-size:11px; }
.detail-identities code { color:#52677a; font-size:10px; word-break:break-all; }
.blocks-title { display:flex; align-items:baseline; gap:10px; }
.blocks-title span { color:var(--beone-text-secondary); font-size:11px; }
.quarantine-section { display:flex; flex-direction:column; gap:10px; }
.quarantine-list { min-height:80px; display:flex; flex-direction:column; gap:10px; }
.quarantine-item { padding:13px 14px; border:1px solid #f0d8ad; border-radius:9px; background:#fffbf2; }
.quarantine-item header { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.quarantine-item header > div { display:flex; flex-direction:column; gap:3px; }
.quarantine-item header b { color:#704e16; font-size:13px; }
.quarantine-item header span { color:#9b7a43; font-size:10px; }
.quarantine-reason { margin-top:10px; padding:8px 10px; border-radius:7px; background:#fff3d7; color:#76571f; font-size:12px; line-height:1.55; }
.recognized-output { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:10px; }
.recognized-group { min-width:0; padding:9px 10px; border:1px solid #eadfc9; border-radius:7px; background:#fff; }
.recognized-group > b { display:block; margin-bottom:7px; color:#684d20; font-size:11px; }
.recognized-tags { display:flex; flex-wrap:wrap; gap:5px; }
.recognized-group ul { margin:0; padding-left:17px; color:#5f6670; font-size:11px; line-height:1.6; }
.recognized-group li + li { margin-top:3px; }
.recognized-group li span { color:#88734e; }
.quarantine-item pre { margin:10px 0 0; font:12px/1.7 var(--beone-font-family); color:#4b5967; white-space:pre-wrap; word-break:break-word; }
.quarantine-item details { margin-top:8px; color:#8d7349; font-size:10px; }
.quarantine-item details code { display:block; margin-top:4px; color:#79694e; white-space:pre-wrap; word-break:break-word; }
.blocks-list { min-height:180px; display:flex; flex-direction:column; gap:10px; }
.block-item { padding:12px 14px; border:1px solid #e0e8ef; border-radius:9px; background:#fff; }
.block-item header { display:flex; justify-content:space-between; gap:12px; color:var(--beone-midnight-blue); font-size:12px; }
.block-item header span { color:#8a99a7; }
.block-item pre { margin:9px 0 0; font:12px/1.7 var(--beone-font-family); color:#435568; white-space:pre-wrap; word-break:break-word; }
.block-item details { margin-top:8px; color:#8694a2; font-size:10px; }
.block-item details code { display:block; margin-top:4px; word-break:break-all; }
@media (max-width:1000px) { .docs-head { flex-direction:column; } .detail-meta { grid-template-columns:repeat(3,1fr); } .recognized-output { grid-template-columns:1fr; } }
</style>
