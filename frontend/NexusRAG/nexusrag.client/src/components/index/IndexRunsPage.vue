<template>
  <div class="runs-page">
    <div class="rp-head">
      <div>
        <h1>运行历史</h1>
        <p>最近的建立索引运行。关掉窗口再回来，点任意一条即可继续查看进度或结果。</p>
      </div>
      <el-button :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="items" class="rp-table" empty-text="暂无运行记录"
              @row-click="open">
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <span class="st"><span class="st-dot" :style="{ background: stateColor(row.state) }"></span>{{ stateLabel(row.state) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="类别" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.category || '—' }}</template>
      </el-table-column>
      <el-table-column label="文档 / 块" width="120">
        <template #default="{ row }">{{ row.doc_count }} / {{ row.block_count }}</template>
      </el-table-column>
      <el-table-column label="节点" width="80">
        <template #default="{ row }">{{ row.node_count }}</template>
      </el-table-column>
      <el-table-column label="Token" min-width="180">
        <template #default="{ row }">{{ tokenText(row.tokens) }}</template>
      </el-table-column>
      <el-table-column label="耗时" width="100">
        <template #default="{ row }">{{ costText(row.cost_ms) }}</template>
      </el-table-column>
      <el-table-column label="开始时间" width="170">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="" width="90" align="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="open(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dlg" :title="'运行 · ' + (current?.category || current?.run_id || '')"
               width="86%" top="5vh" @closed="current = null">
      <IndexDagView v-if="current" :run-id="current.run_id" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import IndexDagView from './IndexDagView.vue'
import { listIndexRuns, type IndexRunListItem } from '../../backend/Index.js'

const items = ref<IndexRunListItem[]>([])
const loading = ref(false)
const dlg = ref(false)
const current = ref<IndexRunListItem | null>(null)

onMounted(load)

async function load() {
  loading.value = true
  try {
    items.value = await listIndexRuns()
  } catch {
    ElMessage.error('加载运行历史失败')
  } finally {
    loading.value = false
  }
}

function open(row: IndexRunListItem) {
  current.value = row
  dlg.value = true
}

function stateColor(s?: string | null) {
  return ({ running: '#2f7cb4', succeeded: '#2e9b5b', failed: '#d52b1e',
    cancelled: '#97a3ae', skipped: '#97a3ae' } as Record<string, string>)[s || ''] || '#c4cbd1'
}
function stateLabel(s?: string | null) {
  return ({ running: '运行中', succeeded: '完成', failed: '失败', cancelled: '已取消',
    skipped: '已跳过' } as Record<string, string>)[s || ''] || (s || '—')
}

function tokenText(raw: string | null) {
  const t = parseJson(raw)
  if (!t) return '—'
  const parts: string[] = []
  if (t.input) parts.push('入 ' + fmtNum(t.input))
  if (t.output) parts.push('出 ' + fmtNum(t.output))
  if (t.embedding) parts.push('向量 ' + fmtNum(t.embedding))
  return parts.length ? parts.join(' · ') : '—'
}
function costText(ms?: number) {
  if (!ms) return '—'
  return ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(1) + 's'
}
function fmtNum(n?: number) {
  if (!n) return '0'
  return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n)
}
function fmt(s: string | null) {
  if (!s) return '—'
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleString('zh-CN', { hour12: false })
}
function parseJson(s?: string | null): any {
  if (!s) return null
  try { return JSON.parse(s) } catch { return null }
}
</script>

<style scoped>
.runs-page {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 28px;
  width: 100%;
}
.rp-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}
.rp-head h1 {
  margin: 0 0 4px;
  font-size: 20px;
  color: var(--beone-text-primary);
}
.rp-head p {
  margin: 0;
  font-size: 13px;
  color: var(--beone-text-secondary);
}
.rp-table {
  cursor: pointer;
}
.st {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.st-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
</style>
