<template>
  <div class="gx-page">
    <!-- 工具栏 -->
    <div class="gx-toolbar">
      <div class="gx-title">知识图谱</div>
      <el-select v-model="activeCollection" size="small" placeholder="选择 Collection" style="width:190px" @change="loadCatalog(true)">
        <el-option v-for="c in collections" :key="c.collection_id" :value="c.collection_id" :label="c.name" />
      </el-select>
      <el-select v-model="typeFilter" size="small" placeholder="全部类型" clearable style="width:150px" @change="loadCatalog(true)">
        <el-option v-for="t in typeOptions" :key="t" :value="t" :label="t" />
      </el-select>
      <span class="gx-depth-label">默认深度</span>
      <el-input-number v-model="defaultDepth" size="small" :min="1" :max="10" :step="1" controls-position="right" style="width:92px" />
      <el-button size="small" :loading="graphBusy" @click="refresh">刷新</el-button>
      <el-button size="small" :disabled="!nodes.length || graphBusy" @click="relayout('progressive')">重新布局</el-button>
      <el-button size="small" :disabled="!nodes.length || graphBusy" @click="clearCanvas">清除</el-button>
      <el-button size="small" :loading="graphBusy" @click="expandAll">全部展开</el-button>
      <el-button size="small" :disabled="!selectedId" :loading="graphBusy" @click="expandSelectedAll">当前节点展开到底</el-button>
      <div class="gx-spacer"></div>
      <span class="gx-stat">节点 {{ nodes.length }} · 边 {{ edges.length }}</span>
    </div>

    <div class="gx-main">
      <!-- 节点浏览：实体和行动都来自当前冻结代次 -->
      <aside class="gx-browser">
        <div class="gx-browser-head">
          <span>实体 / 行动浏览</span>
          <span class="gx-browser-count">{{ filteredEntities.length }}</span>
        </div>
        <el-input
          v-model="entityKeyword"
          size="small"
          clearable
          placeholder="搜索名称、别名或 ID"
          class="gx-browser-search"
        />
        <div class="gx-browser-list">
          <button
            v-for="n in filteredEntities"
            :key="n.id"
            type="button"
            class="gx-browser-item"
            :class="{ 'is-selected': n.id === selectedId }"
            @click="locateOrLoad(n.id)"
          >
            <i :style="{ background: colorOf(n.type) }"></i>
            <span class="gx-browser-info">
              <b :title="n.name">{{ n.name }}</b>
              <small>{{ n.type }}<template v-if="n.aliases.length"> · {{ n.aliases.join(' / ') }}</template></small>
            </span>
            <span class="gx-browser-degree" title="关联边数">{{ catalogDegree[n.id] || 0 }}</span>
          </button>
          <div v-if="!filteredEntities.length" class="gx-browser-empty">没有匹配的节点</div>
        </div>
      </aside>

      <!-- 画布 -->
      <div class="gx-canvas" ref="canvasEl">
        <div v-if="!nodes.length && !graphBusy" class="gx-canvas-empty">
          <b>从左侧选择一个实体或行动</b>
          <span>将加载该节点向外 {{ defaultDepth }} 跳的关系图</span>
        </div>
        <div v-if="graphBusy" class="gx-progress" :class="{ 'gx-progress--compact': graphVisible && nodes.length }">
          <div class="gx-progress-card">
            <b>{{ progressText }}</b>
            <el-progress :percentage="progress" :stroke-width="8" :show-text="true" />
            <span v-if="nodes.length">{{ nodes.length }} 个节点 · {{ edges.length }} 条边</span>
          </div>
        </div>
        <svg
          v-show="graphVisible"
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
              :style="{ animationDelay: n.revealDelay + 'ms' }"
              class="gx-node"
              :class="{ 'is-selected': n.id === selectedId }"
              @pointerdown.stop="onNodeDown(n, $event)"
              @click.stop="select(n.id)"
            >
              <circle :r="n.r" :fill="colorOf(n.type)" :stroke="n.locked ? '#d97706' : '#fff'" :stroke-width="n.locked ? 2.5 : 1.5" />
              <text v-if="n.deg" class="gx-node-deg" :style="{ fontSize: n.degFont + 'px' }">{{ n.deg }}</text>
              <text class="gx-node-label" :y="n.r + 12">{{ n.name }}</text>
              <g
                v-if="expandableSet.has(n.id)"
                :transform="`translate(${n.r * 0.72},${-n.r * 0.72})`"
                class="gx-expand"
                @pointerdown.stop
                @click.stop="expandNode(n.id)"
              >
                <circle r="8" />
                <text>＋</text>
              </g>
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
              <el-tag size="small" effect="plain">{{ detail.entity.kind }}</el-tag>
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
          <div class="gx-block-t">支持断言（{{ detail.support.length }}）</div>
          <div v-if="!detail.support.length" class="gx-empty">暂无支持断言</div>
          <ul class="gx-ev-list">
            <li v-for="ev in detail.support" :key="`${ev.assertion_id}:${ev.block_key}`" @click="openBlock(ev.block_key)">
              <span class="gx-ev-info">
                <b class="gx-ev-name">{{ ev.assertion_id }} · {{ ev.block_key }}</b>
                <small>{{ ev.quote }}</small>
                <small v-if="ev.condition">条件：{{ ev.condition }}</small>
                <small v-if="ev.exception">例外：{{ ev.exception }}</small>
              </span>
              <el-tag size="small" effect="plain">{{ ev.modality }}</el-tag>
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
    <el-dialog v-model="blockDlg" :title="block?.block_key || '块原文'" width="640px">
      <div v-loading="blockLoading" class="gx-block-view">
        <div class="gx-block-meta" v-if="block">
          《{{ block.title }}》 · {{ block.heading_path }} · #{{ block.ordinal }}
        </div>
        <pre class="gx-block-text">{{ block?.text }}</pre>
      </div>
    </el-dialog>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  getGraph, getEntityCatalog, getGraphNeighborhood, getNodeDetail, getBlock,
  type GraphNode, type GraphEdge, type NodeDetail, type BlockView,
} from '../../backend/Graph.js'
import { listQueryCollections, type QueryCollection } from '../../backend/Query.js'

const TYPE_COLORS: Record<string, string> = {
  Reg: '#0891b2', Org: '#7c3aed', Activity: '#2563eb', Product: '#d97706',
  Category: '#059669', Concept: '#db2777', Action: '#dc2626',
}
const typeOptions = ['Reg', 'Org', 'Activity', 'Product', 'Category', 'Concept', 'Action']
function colorOf(t: string) { return TYPE_COLORS[t] || '#64748b' }

const loading = ref(false)
const layoutBusy = ref(false)
const progress = ref(0)
const progressText = ref('')
const graphVisible = ref(true)
const revealedCount = ref(0)
const defaultDepth = ref(2)
const activeCollection = ref<string>()
const collections = ref<QueryCollection[]>([])
const entityCatalog = ref<GraphNode[]>([])
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const expandableIds = ref<string[]>([])
const typeFilter = ref<string>('')
const entityKeyword = ref('')
const pos = reactive<Record<string, { x: number; y: number }>>({})

const selectedId = ref('')
const detail = ref<NodeDetail | null>(null)

const blockDlg = ref(false)
const blockLoading = ref(false)
const block = ref<BlockView | null>(null)

// 视口
const vb = reactive({ x: 0, y: 0, w: 1000, h: 700 })
const canvasEl = ref<HTMLElement | null>(null)
const graphBusy = computed(() => loading.value || layoutBusy.value)

onMounted(async () => {
  collections.value = await listQueryCollections()
  activeCollection.value = collections.value.find(c => c.is_default)?.collection_id
    || (collections.value.length === 1 ? collections.value[0]?.collection_id : undefined)
  if (activeCollection.value) await loadCatalog(false)
})

async function loadCatalog(clearGraph: boolean) {
  loading.value = true
  progress.value = 8
  progressText.value = '正在加载实体目录…'
  try {
    if (!activeCollection.value) return
    const data = await getEntityCatalog(activeCollection.value, typeFilter.value || undefined)
    entityCatalog.value = data.nodes
    activeCollection.value = data.collection || undefined
    if (clearGraph) clearCanvas()
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function refresh() {
  const selected = selectedId.value
  await loadCatalog(false)
  if (selected) await loadCenter(selected)
}

function clearCanvas() {
  layoutRun++
  layoutBusy.value = false
  graphVisible.value = true
  revealedCount.value = 0
  nodes.value = []
  edges.value = []
  expandableIds.value = []
  selectedId.value = ''
  detail.value = null
  for (const id of Object.keys(pos)) delete pos[id]
}

function nameOf(id: string) {
  return nodes.value.find(n => n.id === id)?.name || id
}

// 每个节点的度数（连了多少条边，含出/入）
const localDegree = computed(() => {
  const d: Record<string, number> = {}
  for (const e of edges.value) {
    d[e.source] = (d[e.source] || 0) + 1
    d[e.target] = (d[e.target] || 0) + 1
  }
  return d
})

const catalogDegree = computed(() => Object.fromEntries(
  entityCatalog.value.map(n => [n.id, n.degree || 0]),
))
const expandableSet = computed(() => new Set(expandableIds.value))

const filteredEntities = computed(() => {
  const q = entityKeyword.value.trim().toLocaleLowerCase()
  return entityCatalog.value
    .filter(n => !q || n.name.toLocaleLowerCase().includes(q)
      || n.id.toLocaleLowerCase().includes(q)
      || n.aliases.some(a => a.toLocaleLowerCase().includes(q)))
    .slice()
    .sort((a, b) => (catalogDegree.value[b.id] || 0) - (catalogDegree.value[a.id] || 0)
      || a.name.localeCompare(b.name, 'zh-CN'))
})

// ---- 力导向布局（逐帧离屏计算；收敛后一次显示，避免节点来回晃动） ----
let layoutRun = 0
function nextFrame() {
  return new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
}

async function relayout(_mode: 'progressive' | 'hidden' = 'progressive') {
  const run = ++layoutRun
  const ns = nodes.value
  const n = ns.length
  if (!n) {
    layoutBusy.value = false
    return
  }
  layoutBusy.value = true
  progressText.value = '正在布局…'
  progress.value = Math.max(progress.value, 20)
  graphVisible.value = false
  revealedCount.value = 0

  const W = 1000, H = 700
  const P: Record<string, { x: number; y: number }> = {}
  ns.forEach((node, i) => {
    const a = (2 * Math.PI * i) / n
    P[node.id] = { x: W / 2 + Math.cos(a) * 250, y: H / 2 + Math.sin(a) * 250 }
  })
  const k = 180                       // 理想边长
  const totalIterations = n > 600 ? 180 : 260
  const iterationsPerFrame = n > 350 ? 1 : n > 180 ? 2 : 5
  for (let iter = 0; iter < totalIterations;) {
    const frameEnd = Math.min(totalIterations, iter + iterationsPerFrame)
    for (; iter < frameEnd; iter++) {
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
    const temp = 30 * (1 - iter / totalIterations)
    for (const node of ns) {
      const dp = disp[node.id]!, pp = P[node.id]!
      const d = Math.hypot(dp.x, dp.y) || 0.01
      pp.x += (dp.x / d) * Math.min(d, temp)
      pp.y += (dp.y / d) * Math.min(d, temp)
    }
    }

    if (run !== layoutRun) return
    progress.value = 20 + Math.round((iter / totalIterations) * 78)
    await nextFrame()
  }

  if (run !== layoutRun) return
  for (const id of Object.keys(pos)) delete pos[id]
  for (const node of ns) pos[node.id] = P[node.id]!
  revealedCount.value = n
  fitView()
  graphVisible.value = true
  progress.value = 100
  progressText.value = '布局完成'
  await nextFrame()
  if (run === layoutRun) layoutBusy.value = false
}

async function layoutExpandedNodes(newIds: string[], anchorId: string) {
  if (!newIds.length) {
    revealedCount.value = nodes.value.length
    return
  }
  const run = ++layoutRun
  const newSet = new Set(newIds)
  const anchor = pos[anchorId] || { x: 500, y: 350 }
  const P: Record<string, { x: number; y: number }> = {}
  newIds.forEach((id, i) => {
    const a = (2 * Math.PI * i) / newIds.length
    const ring = 135 + Math.floor(i / 18) * 70
    P[id] = { x: anchor.x + Math.cos(a) * ring, y: anchor.y + Math.sin(a) * ring }
  })

  layoutBusy.value = true
  graphVisible.value = true
  progress.value = 20
  progressText.value = `正在布局新增的 ${newIds.length} 个节点…`
  // 只显示旧节点；新增节点在局部布局稳定后一次渐显。
  revealedCount.value = nodes.value.length - newIds.length

  const totalIterations = 150
  const perFrame = newIds.length > 120 ? 1 : 4
  for (let iter = 0; iter < totalIterations;) {
    const frameEnd = Math.min(totalIterations, iter + perFrame)
    for (; iter < frameEnd; iter++) {
      const disp: Record<string, { x: number; y: number }> = {}
      for (const id of newIds) disp[id] = { x: 0, y: 0 }

      // 新节点之间互斥；已有节点只作为固定障碍，不参与移动。
      for (let i = 0; i < newIds.length; i++) {
        for (let j = i + 1; j < newIds.length; j++) {
          const a = newIds[i]!, b = newIds[j]!
          const pa = P[a]!, pb = P[b]!
          let dx = pa.x - pb.x, dy = pa.y - pb.y
          const d = Math.hypot(dx, dy) || 0.01
          const force = (120 * 120) / d
          dx /= d; dy /= d
          disp[a]!.x += dx * force; disp[a]!.y += dy * force
          disp[b]!.x -= dx * force; disp[b]!.y -= dy * force
        }
      }
      for (const old of nodes.value) {
        if (newSet.has(old.id)) continue
        const fixed = pos[old.id]
        if (!fixed) continue
        for (const id of newIds) {
          const p = P[id]!
          let dx = p.x - fixed.x, dy = p.y - fixed.y
          const d = Math.hypot(dx, dy) || 0.01
          if (d > 190) continue
          const force = (105 * 105) / d
          dx /= d; dy /= d
          disp[id]!.x += dx * force; disp[id]!.y += dy * force
        }
      }

      // 关系边产生引力；已有端点固定，只移动新增端点。
      for (const edge of edges.value) {
        const sourceNew = newSet.has(edge.source)
        const targetNew = newSet.has(edge.target)
        if (!sourceNew && !targetNew) continue
        const ps = sourceNew ? P[edge.source] : pos[edge.source]
        const pt = targetNew ? P[edge.target] : pos[edge.target]
        if (!ps || !pt) continue
        let dx = ps.x - pt.x, dy = ps.y - pt.y
        const d = Math.hypot(dx, dy) || 0.01
        const force = (d * d) / 155
        dx /= d; dy /= d
        if (sourceNew) {
          disp[edge.source]!.x -= dx * force
          disp[edge.source]!.y -= dy * force
        }
        if (targetNew) {
          disp[edge.target]!.x += dx * force
          disp[edge.target]!.y += dy * force
        }
      }

      const temp = 24 * (1 - iter / totalIterations)
      for (const id of newIds) {
        const dxy = disp[id]!, p = P[id]!
        const d = Math.hypot(dxy.x, dxy.y) || 0.01
        p.x += (dxy.x / d) * Math.min(d, temp)
        p.y += (dxy.y / d) * Math.min(d, temp)
      }
    }
    if (run !== layoutRun) return
    progress.value = 20 + Math.round((iter / totalIterations) * 78)
    await nextFrame()
  }

  if (run !== layoutRun) return
  for (const id of newIds) pos[id] = P[id]!
  revealedCount.value = nodes.value.length
  progress.value = 100
  progressText.value = '新增节点布局完成'
  await nextFrame()
  if (run === layoutRun) layoutBusy.value = false
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

const visibleNodeIds = computed(() => new Set(nodes.value.slice(0, revealedCount.value).map(n => n.id)))

const nodeViews = computed(() =>
  nodes.value.slice(0, revealedCount.value).map((n, index) => {
    const deg = n.degree ?? localDegree.value[n.id] ?? 0
    // 边越多节点越大（sqrt 压缩防止崨雄节点过大），选中再略放大
    const base = Math.min(34, 9 + Math.sqrt(deg) * 3.4)
    const r = n.id === selectedId.value ? base + 3 : base
    return {
      ...n, deg, r, revealDelay: Math.min(index * 12, 360),
      degFont: Math.max(9, Math.min(15, r * 0.95)),
      x: pos[n.id]?.x ?? 0, y: pos[n.id]?.y ?? 0,
    }
  }),
)
const edgeLines = computed(() =>
  edges.value
    .filter(e => pos[e.source] && pos[e.target]
      && visibleNodeIds.value.has(e.source) && visibleNodeIds.value.has(e.target))
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
    detail.value = await getNodeDetail(id, activeCollection.value)
  } catch {
    detail.value = null
  }
}

function focusEntity(id: string) {
  const p = pos[id]
  if (!p) return
  const rect = canvasEl.value?.getBoundingClientRect()
  const aspect = rect && rect.width > 0 && rect.height > 0 ? rect.height / rect.width : 0.7
  const width = 780
  const height = width * aspect
  vb.x = p.x - width / 2
  vb.y = p.y - height / 2
  vb.w = width
  vb.h = height
}

function neighborhoodIds(rootId: string, hops = 2) {
  const seen = new Set([rootId])
  let frontier = new Set([rootId])
  for (let hop = 0; hop < hops && frontier.size; hop++) {
    const next = new Set<string>()
    for (const edge of edges.value) {
      if (frontier.has(edge.source) && !seen.has(edge.target)) next.add(edge.target)
      if (frontier.has(edge.target) && !seen.has(edge.source)) next.add(edge.source)
    }
    for (const id of next) seen.add(id)
    frontier = next
  }
  return [...seen].filter(id => pos[id])
}

function focusNeighborhood(id: string, hops = 2) {
  const ids = neighborhoodIds(id, hops)
  if (!ids.length) return
  const xs = ids.map(x => pos[x]!.x)
  const ys = ids.map(x => pos[x]!.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const centerX = (minX + maxX) / 2
  const centerY = (minY + maxY) / 2
  const rect = canvasEl.value?.getBoundingClientRect()
  const aspect = rect && rect.width > 0 && rect.height > 0 ? rect.height / rect.width : 0.7
  // 两跳范围加留白；保证不会因为邻域很小而过度放大。
  let width = Math.max(620, maxX - minX + 220)
  let height = Math.max(420, maxY - minY + 220)
  if (height / width > aspect) width = height / aspect
  else height = width * aspect
  vb.x = centerX - width / 2
  vb.y = centerY - height / 2
  vb.w = width
  vb.h = height
}

async function locateOrLoad(id: string) {
  if (!nodes.value.some(n => n.id === id) || !pos[id]) {
    if (nodes.value.length) {
      const entity = entityCatalog.value.find(n => n.id === id)
      try {
        await ElMessageBox.confirm(
          `实体“${entity?.name || id}”不在当前图中，是否以此实体重新绘制？`,
          '实体不在当前图中',
          {
            confirmButtonText: '重新绘制',
            cancelButtonText: '取消',
            type: 'warning',
          },
        )
      } catch {
        return
      }
    }
    await loadCenter(id)
    return
  }
  await select(id)
  await nextFrame() // 详情面板出现后，按变化后的画布宽高计算缩放比例
  focusNeighborhood(id, 2)
}

async function loadCenter(id: string) {
  loading.value = true
  progress.value = 8
  progressText.value = `正在加载 ${defaultDepth.value} 跳关系…`
  try {
    const g = await getGraphNeighborhood(id, defaultDepth.value, activeCollection.value)
    nodes.value = g.nodes
    edges.value = g.edges
    expandableIds.value = g.expandable || []
    selectedId.value = id
    void select(id)
    loading.value = false
    progress.value = 20
    await relayout('progressive')
    focusNeighborhood(id, 2)
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function mergeGraph(newNodes: GraphNode[], newEdges: GraphEdge[]) {
  const nodeMap = new Map(nodes.value.map(n => [n.id, n]))
  for (const n of newNodes) nodeMap.set(n.id, n)
  const edgeMap = new Map(edges.value.map(e => [String(e.id ?? `${e.source}|${e.type}|${e.target}`), e]))
  for (const e of newEdges) edgeMap.set(String(e.id ?? `${e.source}|${e.type}|${e.target}`), e)
  nodes.value = [...nodeMap.values()]
  edges.value = [...edgeMap.values()]
}

async function expandNode(id: string) {
  loading.value = true
  progress.value = 8
  progressText.value = '正在加载下一层关系…'
  try {
    const existingIds = new Set(nodes.value.map(n => n.id))
    const g = await getGraphNeighborhood(id, 1, activeCollection.value)
    mergeGraph(g.nodes, g.edges)
    const newIds = g.nodes.filter(n => !existingIds.has(n.id)).map(n => n.id)
    expandableIds.value = [...new Set([
      ...expandableIds.value.filter(x => x !== id),
      ...(g.expandable || []),
    ])]
    void select(id)
    loading.value = false
    progress.value = 20
    await layoutExpandedNodes(newIds, id)
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function expandSelectedAll() {
  if (!selectedId.value) return
  const id = selectedId.value
  loading.value = true
  progress.value = 5
  progressText.value = '正在加载当前连通图…'
  try {
    const g = await getGraphNeighborhood(id, 0, activeCollection.value)
    nodes.value = g.nodes
    edges.value = g.edges
    expandableIds.value = []
    loading.value = false
    progress.value = 20
    await relayout('hidden')
    focusEntity(id)
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function expandAll() {
  loading.value = true
  progress.value = 5
  progressText.value = '正在加载全部节点和关系…'
  graphVisible.value = false
  try {
    const g = await getGraph(activeCollection.value, typeFilter.value || undefined)
    nodes.value = g.nodes
    edges.value = g.edges
    expandableIds.value = []
    loading.value = false
    progress.value = 20
    await relayout('hidden')
  } catch {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function openBlock(blockKey: string) {
  blockDlg.value = true
  blockLoading.value = true
  block.value = null
  try {
    block.value = await getBlock(blockKey, activeCollection.value)
  } catch {
    /* 拦截器已提示 */
  } finally {
    blockLoading.value = false
  }
}

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
.gx-depth-label { margin-left: 4px; font-size: 12px; color: var(--beone-text-secondary); white-space: nowrap; }
.gx-spacer { flex: 1; }
.gx-stat { font-size: 12px; color: var(--beone-text-secondary); }
.gx-main { flex: 1; min-height: 0; display: flex; }
.gx-browser { width: 260px; flex: 0 0 260px; min-height: 0; display: flex; flex-direction: column; padding: 12px; border-right: 1px solid var(--beone-border); background: var(--beone-white); }
.gx-browser-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 13px; font-weight: 600; color: var(--beone-midnight-blue); }
.gx-browser-count { min-width: 24px; padding: 1px 7px; border-radius: 10px; text-align: center; font-size: 11px; font-weight: 500; color: var(--beone-text-secondary); background: var(--beone-bg-panel); }
.gx-browser-search { margin-bottom: 10px; }
.gx-browser-list { flex: 1; min-height: 0; overflow: auto; }
.gx-browser-item { width: 100%; display: flex; align-items: center; gap: 9px; padding: 8px 7px; border: 0; border-radius: 7px; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.gx-browser-item:hover { background: var(--beone-bg-panel); }
.gx-browser-item.is-selected { background: #eaf4fb; box-shadow: inset 3px 0 #2f7cb4; }
.gx-browser-item > i { width: 10px; height: 10px; flex: 0 0 10px; border-radius: 50%; }
.gx-browser-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.gx-browser-info b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
.gx-browser-info small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--beone-text-secondary); }
.gx-browser-degree { min-width: 24px; padding: 2px 6px; border-radius: 10px; text-align: center; font-size: 10px; color: var(--beone-text-secondary); background: var(--beone-bg-panel); }
.gx-browser-empty { padding: 28px 8px; text-align: center; font-size: 12px; color: var(--beone-text-secondary); }
.gx-canvas { flex: 1; min-width: 0; position: relative; background:
  radial-gradient(circle, rgba(0,0,0,0.05) 1px, transparent 1px) 0 0 / 22px 22px; }
.gx-canvas-empty { position: absolute; inset: 0; z-index: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; pointer-events: none; color: var(--beone-text-secondary); }
.gx-canvas-empty b { font-size: 15px; color: var(--beone-text-primary); }
.gx-canvas-empty span { font-size: 12px; }
.gx-progress { position: absolute; inset: 0; z-index: 4; display: flex; align-items: center; justify-content: center; pointer-events: none; background: rgba(247,250,253,0.62); backdrop-filter: blur(1px); }
.gx-progress-card { width: min(360px, 70%); padding: 18px 22px; border: 1px solid var(--beone-border); border-radius: 12px; background: rgba(255,255,255,0.94); box-shadow: 0 10px 30px rgba(26,49,76,0.12); }
.gx-progress-card b { display: block; margin-bottom: 12px; font-size: 13px; color: var(--beone-midnight-blue); }
.gx-progress-card > span { display: block; margin-top: 8px; text-align: center; font-size: 11px; color: var(--beone-text-secondary); }
.gx-progress--compact { inset: 12px 12px auto auto; display: block; width: 280px; background: transparent; backdrop-filter: none; }
.gx-progress--compact .gx-progress-card { width: auto; padding: 12px 14px; box-shadow: 0 6px 20px rgba(26,49,76,0.12); }
.gx-svg { width: 100%; height: 100%; cursor: grab; touch-action: none; }
.gx-svg:active { cursor: grabbing; }
.gx-edge { stroke: #b8c2cc; stroke-width: 1.2; }
.gx-edge--manual { stroke: #d97706; stroke-dasharray: 4 3; }
.gx-node { cursor: pointer; transform-box: fill-box; transform-origin: center; animation: gx-node-in 260ms ease-out both; }
.gx-node.is-selected circle { filter: drop-shadow(0 0 6px rgba(37,99,235,0.6)); }
.gx-node-label { font-size: 11px; text-anchor: middle; fill: var(--beone-text-primary); pointer-events: none; }
.gx-node-deg { text-anchor: middle; dominant-baseline: central; fill: #fff; font-weight: 700; pointer-events: none; }
.gx-expand circle { fill: #fff; stroke: #2f7cb4; stroke-width: 1.8; filter: none !important; }
.gx-expand text { text-anchor: middle; dominant-baseline: central; fill: #2f7cb4; font-size: 12px; font-weight: 700; pointer-events: none; }
.gx-expand:hover circle { fill: #eaf4fb; }
@keyframes gx-node-in {
  from { opacity: 0; scale: 0.45; }
  to { opacity: 1; scale: 1; }
}
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
.gx-ev-info { min-width:0; display:flex; flex:1; flex-direction:column; gap:3px; }
.gx-ev-info small { color:var(--beone-text-secondary); line-height:1.45; }
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
