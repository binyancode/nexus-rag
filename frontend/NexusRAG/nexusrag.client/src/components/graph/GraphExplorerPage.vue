<template>
  <div class="gx-page">
    <!-- 工具栏 -->
    <div class="gx-toolbar">
      <div class="gx-title">知识图谱</div>
      <el-select v-model="typeFilter" size="small" placeholder="全部类型" clearable style="width:150px" @change="reload">
        <el-option v-for="t in typeOptions" :key="t" :value="t" :label="t" />
      </el-select>
      <el-button size="small" :loading="loading" @click="reload">刷新</el-button>
      <el-button size="small" @click="relayout">重新布局</el-button>
      <div class="gx-spacer"></div>
      <span class="gx-stat">节点 {{ nodes.length }} · 边 {{ edges.length }}</span>
      <el-button size="small" type="primary" @click="addDlg = true">＋ 新增实体</el-button>
    </div>

    <div class="gx-main">
      <!-- 画布 -->
      <div class="gx-canvas" ref="canvasEl">
        <svg
          :viewBox="`${vb.x} ${vb.y} ${vb.w} ${vb.h}`"
          class="gx-svg"
          @wheel.prevent="onWheel"
          @pointerdown="onBgDown"
          @pointermove="onMove"
          @pointerup="onUp"
          @pointerleave="onUp"
        >
          <g>
            <line
              v-for="e in edgeLines"
              :key="e.id"
              :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
              class="gx-edge"
              :class="{ 'gx-edge--manual': e.origin === 'manual' }"
            />
          </g>
          <g>
            <g
              v-for="n in nodeViews"
              :key="n.id"
              :transform="`translate(${n.x},${n.y})`"
              class="gx-node"
              :class="{ 'is-selected': n.id === selectedId }"
              @pointerdown.stop="onNodeDown(n, $event)"
              @click.stop="select(n.id)"
            >
              <circle :r="n.r" :fill="colorOf(n.type)" :stroke="n.locked ? '#d97706' : '#fff'" :stroke-width="n.locked ? 2.5 : 1.5" />
              <text class="gx-node-label" :y="n.r + 12">{{ n.name }}</text>
            </g>
          </g>
        </svg>

        <!-- 图例 -->
        <div class="gx-legend">
          <span v-for="t in typeOptions" :key="t" class="gx-legend-item">
            <i :style="{ background: colorOf(t) }"></i>{{ t }}
          </span>
        </div>
      </div>

      <!-- 详情面板 -->
      <div class="gx-detail" v-if="detail">
        <div class="gx-detail-head">
          <div>
            <div class="gx-detail-name">{{ detail.entity.name }}</div>
            <div class="gx-detail-sub">
              <el-tag size="small" :color="colorOf(detail.entity.type)" effect="dark" style="border:none">{{ detail.entity.type }}</el-tag>
              <el-tag size="small" :type="originTag(detail.entity.origin)">{{ detail.entity.origin }}</el-tag>
              <el-tag v-if="detail.entity.locked" size="small" type="warning">locked</el-tag>
            </div>
          </div>
          <el-button link @click="detail = null">✕</el-button>
        </div>

        <div v-if="detail.entity.aliases.length" class="gx-block">
          <div class="gx-block-t">别名</div>
          <div class="gx-aliases">
            <el-tag v-for="a in detail.entity.aliases" :key="a" size="small" effect="plain">{{ a }}</el-tag>
          </div>
        </div>

        <div class="gx-block">
          <div class="gx-block-t">出处块（{{ detail.evidence.length }}）</div>
          <div v-if="!detail.evidence.length" class="gx-empty">暂无出处</div>
          <ul class="gx-ev-list">
            <li v-for="ev in detail.evidence" :key="ev.fullname" @click="openBlock(ev.fullname, ev.store_id)">
              <span class="gx-ev-name">{{ ev.fullname }}</span>
              <el-tag size="small" :type="originTag(ev.origin)">{{ ev.origin }}</el-tag>
            </li>
          </ul>
        </div>

        <div class="gx-block">
          <div class="gx-block-t">关系（{{ detail.edges.length }}）</div>
          <ul class="gx-edge-list">
            <li v-for="r in detail.edges" :key="r.id ?? r.source + r.type + r.target">
              <span :class="{ 'gx-dir-out': r.source === detail.entity.id }">
                {{ r.source === detail.entity.id ? '→' : '←' }}
              </span>
              <b>{{ r.type }}</b>
              <span class="gx-edge-other">{{ nameOf(r.source === detail.entity.id ? r.target : r.source) }}</span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- 块原文查看 -->
    <el-dialog v-model="blockDlg" :title="block?.fullname || '块原文'" width="640px">
      <div v-loading="blockLoading" class="gx-block-view">
        <div class="gx-block-meta" v-if="block">
          《{{ block.title }}》 · {{ block.section }} · #{{ block.ordinal }}
        </div>
        <pre class="gx-block-text">{{ block?.text }}</pre>
      </div>
    </el-dialog>

    <!-- 新增实体 -->
    <el-dialog v-model="addDlg" title="新增实体" width="460px" @closed="resetAdd">
      <div class="fld">
        <label>名称 <span class="req">*</span></label>
        <el-input v-model="addForm.name" placeholder="规范全称" />
      </div>
      <div class="fld">
        <label>类型 <span class="req">*</span></label>
        <el-select v-model="addForm.type" style="width:100%" placeholder="选择类型">
          <el-option v-for="t in typeOptions" :key="t" :value="t" :label="t" />
        </el-select>
      </div>
      <div class="fld">
        <label>别名（回车分隔）</label>
        <el-input v-model="addForm.aliasText" placeholder="多个别名用回车或逗号分隔" />
      </div>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="primary" :loading="adding" :disabled="!addForm.name || !addForm.type" @click="doAdd">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getGraph, getEntityDetail, getBlock, addEntity,
  type GraphNode, type GraphEdge, type EntityDetail, type BlockView,
} from '../../backend/Graph.js'

const TYPE_COLORS: Record<string, string> = {
  AppType: '#2563eb', Reg: '#0891b2', Org: '#7c3aed',
  Requirement: '#d97706', Category: '#059669', Concept: '#db2777',
}
const typeOptions = ['AppType', 'Reg', 'Org', 'Requirement', 'Category', 'Concept']
function colorOf(t: string) { return TYPE_COLORS[t] || '#64748b' }

const loading = ref(false)
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const typeFilter = ref<string>('')
const pos = reactive<Record<string, { x: number; y: number }>>({})

const selectedId = ref('')
const detail = ref<EntityDetail | null>(null)

const blockDlg = ref(false)
const blockLoading = ref(false)
const block = ref<BlockView | null>(null)

const addDlg = ref(false)
const adding = ref(false)
const addForm = reactive({ name: '', type: '', aliasText: '' })

// 视口
const vb = reactive({ x: 0, y: 0, w: 1000, h: 700 })
const canvasEl = ref<HTMLElement | null>(null)

onMounted(reload)

async function reload() {
  loading.value = true
  try {
    const g = await getGraph(undefined, typeFilter.value || undefined)
    nodes.value = g.nodes
    edges.value = g.edges
    relayout()
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function nameOf(id: string) {
  return nodes.value.find(n => n.id === id)?.name || id
}

// ---- 力导向布局（一次性迭代） ----
function relayout() {
  const ns = nodes.value
  const n = ns.length
  if (!n) return
  const W = 1000, H = 700
  const P: Record<string, { x: number; y: number }> = {}
  ns.forEach((node, i) => {
    const a = (2 * Math.PI * i) / n
    P[node.id] = { x: W / 2 + Math.cos(a) * 250, y: H / 2 + Math.sin(a) * 250 }
  })
  const k = 180                       // 理想边长
  for (let iter = 0; iter < 260; iter++) {
    const disp: Record<string, { x: number; y: number }> = {}
    ns.forEach(node => (disp[node.id] = { x: 0, y: 0 }))
    // 斥力
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const pa = P[ns[i]!.id]!, pb = P[ns[j]!.id]!
        const da = disp[ns[i]!.id]!, db = disp[ns[j]!.id]!
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        const d = Math.hypot(dx, dy) || 0.01
        const rep = (k * k) / d
        dx /= d; dy /= d
        da.x += dx * rep; da.y += dy * rep
        db.x -= dx * rep; db.y -= dy * rep
      }
    }
    // 引力（边）
    for (const e of edges.value) {
      const ps = P[e.source], pt = P[e.target]
      const ds = disp[e.source], dt = disp[e.target]
      if (!ps || !pt || !ds || !dt) continue
      let dx = ps.x - pt.x
      let dy = ps.y - pt.y
      const d = Math.hypot(dx, dy) || 0.01
      const att = (d * d) / k
      dx /= d; dy /= d
      ds.x -= dx * att; ds.y -= dy * att
      dt.x += dx * att; dt.y += dy * att
    }
    const temp = 30 * (1 - iter / 260)
    for (const node of ns) {
      const dp = disp[node.id]!, pp = P[node.id]!
      const d = Math.hypot(dp.x, dp.y) || 0.01
      pp.x += (dp.x / d) * Math.min(d, temp)
      pp.y += (dp.y / d) * Math.min(d, temp)
    }
  }
  // 写回响应式位置
  for (const id of Object.keys(pos)) delete pos[id]
  for (const node of ns) pos[node.id] = P[node.id]!
  fitView()
}

function fitView() {
  const xs = nodes.value.map(n => pos[n.id]?.x ?? 0)
  const ys = nodes.value.map(n => pos[n.id]?.y ?? 0)
  if (!xs.length) return
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const pad = 80
  vb.x = minX - pad; vb.y = minY - pad
  vb.w = Math.max(400, maxX - minX + pad * 2)
  vb.h = Math.max(300, maxY - minY + pad * 2)
}

const nodeViews = computed(() =>
  nodes.value.map(n => ({
    ...n, x: pos[n.id]?.x ?? 0, y: pos[n.id]?.y ?? 0,
    r: n.id === selectedId.value ? 14 : 10,
  })),
)
const edgeLines = computed(() =>
  edges.value
    .filter(e => pos[e.source] && pos[e.target])
    .map(e => {
      const ps = pos[e.source]!, pt = pos[e.target]!
      return {
        id: e.id ?? e.source + e.type + e.target,
        x1: ps.x, y1: ps.y, x2: pt.x, y2: pt.y,
        origin: e.origin,
      }
    }),
)

async function select(id: string) {
  selectedId.value = id
  try {
    detail.value = await getEntityDetail(id)
  } catch {
    detail.value = null
  }
}

async function openBlock(fullname: string, storeId: string) {
  blockDlg.value = true
  blockLoading.value = true
  block.value = null
  try {
    block.value = await getBlock(fullname, storeId)
  } catch {
    /* 拦截器已提示 */
  } finally {
    blockLoading.value = false
  }
}

async function doAdd() {
  adding.value = true
  try {
    const aliases = addForm.aliasText.split(/[\n,，]/).map(s => s.trim()).filter(Boolean)
    await addEntity({ name: addForm.name.trim(), type: addForm.type, aliases, auto: false })
    ElMessage.success('已新增实体')
    addDlg.value = false
    await reload()
  } catch {
    /* 拦截器已提示 */
  } finally {
    adding.value = false
  }
}
function resetAdd() { addForm.name = ''; addForm.type = ''; addForm.aliasText = '' }

function originTag(o: string): 'success' | 'info' | 'warning' {
  if (o === 'manual') return 'warning'
  if (o === 'seed') return 'success'
  return 'info'
}

// ---- 平移 / 缩放 / 拖拽 ----
let panning = false
let dragNode: string | null = null
let last = { x: 0, y: 0 }

function onBgDown(ev: PointerEvent) {
  panning = true; last = { x: ev.clientX, y: ev.clientY }
  ;(ev.currentTarget as Element).setPointerCapture?.(ev.pointerId)
}
function onNodeDown(n: any, ev: PointerEvent) {
  dragNode = n.id; last = { x: ev.clientX, y: ev.clientY }
  ;(ev.currentTarget as Element).setPointerCapture?.(ev.pointerId)
}
function onMove(ev: PointerEvent) {
  if (dragNode) {
    const p = pos[dragNode]
    if (p) {
      const rect = canvasEl.value!.getBoundingClientRect()
      const sx = vb.w / rect.width, sy = vb.h / rect.height
      p.x += (ev.clientX - last.x) * sx
      p.y += (ev.clientY - last.y) * sy
      last = { x: ev.clientX, y: ev.clientY }
    }
  } else if (panning) {
    const rect = canvasEl.value!.getBoundingClientRect()
    vb.x -= (ev.clientX - last.x) * (vb.w / rect.width)
    vb.y -= (ev.clientY - last.y) * (vb.h / rect.height)
    last = { x: ev.clientX, y: ev.clientY }
  }
}
function onUp() { panning = false; dragNode = null }
function onWheel(ev: WheelEvent) {
  const factor = ev.deltaY > 0 ? 1.12 : 0.89
  const rect = canvasEl.value!.getBoundingClientRect()
  const mx = vb.x + (ev.clientX - rect.left) * (vb.w / rect.width)
  const my = vb.y + (ev.clientY - rect.top) * (vb.h / rect.height)
  vb.x = mx - (mx - vb.x) * factor
  vb.y = my - (my - vb.y) * factor
  vb.w *= factor; vb.h *= factor
}
</script>

<style scoped>
.gx-page { flex: 1; min-height: 0; display: flex; flex-direction: column; color: var(--beone-text-primary); }
.gx-toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--beone-border); background: var(--beone-bg-panel); }
.gx-title { font-weight: 600; font-size: 15px; }
.gx-spacer { flex: 1; }
.gx-stat { font-size: 12px; color: var(--beone-text-secondary); }
.gx-main { flex: 1; min-height: 0; display: flex; }
.gx-canvas { flex: 1; min-width: 0; position: relative; background:
  radial-gradient(circle, rgba(0,0,0,0.05) 1px, transparent 1px) 0 0 / 22px 22px; }
.gx-svg { width: 100%; height: 100%; cursor: grab; touch-action: none; }
.gx-svg:active { cursor: grabbing; }
.gx-edge { stroke: #b8c2cc; stroke-width: 1.2; }
.gx-edge--manual { stroke: #d97706; stroke-dasharray: 4 3; }
.gx-node { cursor: pointer; }
.gx-node.is-selected circle { filter: drop-shadow(0 0 6px rgba(37,99,235,0.6)); }
.gx-node-label { font-size: 11px; text-anchor: middle; fill: var(--beone-text-primary); pointer-events: none; }
.gx-legend { position: absolute; left: 12px; bottom: 12px; display: flex; flex-wrap: wrap; gap: 10px; background: rgba(255,255,255,0.85); padding: 6px 10px; border-radius: 8px; border: 1px solid var(--beone-border); }
.gx-legend-item { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: var(--beone-text-secondary); }
.gx-legend-item i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.gx-detail { width: 340px; flex: 0 0 340px; border-left: 1px solid var(--beone-border); background: var(--beone-white); padding: 16px; overflow: auto; }
.gx-detail-head { display: flex; justify-content: space-between; align-items: flex-start; }
.gx-detail-name { font-size: 16px; font-weight: 600; }
.gx-detail-sub { display: flex; gap: 6px; margin-top: 6px; }
.gx-block { margin-top: 16px; }
.gx-block-t { font-size: 13px; font-weight: 600; color: var(--beone-midnight-blue); margin-bottom: 8px; }
.gx-aliases { display: flex; flex-wrap: wrap; gap: 6px; }
.gx-empty { font-size: 12px; color: var(--beone-text-secondary); }
.gx-ev-list { list-style: none; margin: 0; padding: 0; }
.gx-ev-list li { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.gx-ev-list li:hover { background: var(--beone-bg-panel); }
.gx-ev-name { font-family: monospace; word-break: break-all; }
.gx-edge-list { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.gx-edge-list li { display: flex; align-items: center; gap: 6px; padding: 4px 0; }
.gx-dir-out { color: #2563eb; }
.gx-edge-other { color: var(--beone-text-secondary); }
.gx-block-view { max-height: 60vh; overflow: auto; }
.gx-block-meta { font-size: 12px; color: var(--beone-text-secondary); margin-bottom: 8px; }
.gx-block-text { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 14px; line-height: 1.7; margin: 0; }
.fld { margin-bottom: 12px; }
.fld > label { display: block; font-size: 13px; margin-bottom: 6px; color: var(--beone-text-secondary); }
.req { color: #d97706; }
</style>
