<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'

defineProps<{
  data: {
    name: string
    badge?: string          // 阶段（切块/向量化/抽取/入网/完成）
    value?: string          // 输出摘要
    color: string
    selected?: boolean
    cost?: string           // 已格式化耗时
    total?: number          // 折叠组：成员总数（有则显示进度条）
    ratio?: number          // 折叠组：完成比例 0..1
  }
}>()
</script>

<template>
  <div class="dnode" :class="{ sel: data.selected }" :style="{ '--c': data.color }">
    <Handle type="target" :position="Position.Left" class="dh" />
    <span class="accent"></span>
    <div class="inner">
      <div class="name" :title="data.name">{{ data.name }}</div>
      <div class="row">
        <span v-if="data.badge" class="badge">{{ data.badge }}</span>
        <span v-if="data.value" class="val" :title="data.value">{{ data.value }}</span>
        <span v-if="data.cost" class="cost" title="耗时">{{ data.cost }}</span>
      </div>
      <div v-if="data.total" class="track"><div class="fill" :style="{ width: (data.ratio || 0) * 100 + '%' }"></div></div>
    </div>
    <Handle type="source" :position="Position.Right" class="dh" />
  </div>
</template>

<style scoped>
.dnode {
  width: 182px;
  display: flex;
  align-items: stretch;
  background: #f9fbfe;
  border: 1px solid #dbe5f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 6px rgba(16, 24, 40, 0.05), 0 10px 20px rgba(16, 24, 40, 0.08);
  transition: box-shadow 0.15s, border-color 0.15s;
}
.dnode.sel {
  border-color: var(--c);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 18%, transparent), 0 10px 22px rgba(16, 24, 40, 0.12);
}
.accent { width: 4px; flex: 0 0 auto; background: color-mix(in srgb, var(--c) 78%, #ffffff); }
.inner {
  padding: 8px 11px;
  min-width: 0;
  flex: 1;
  background: linear-gradient(180deg, #e9f0f8 0%, #f9fbfe 38%);
}
.name {
  font-size: 12.5px; font-weight: 700; color: #1f2f43;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.row { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.badge {
  font-size: 9px; color: var(--c); flex: 0 0 auto;
  border: 1px solid color-mix(in srgb, var(--c) 38%, #ffffff);
  background: color-mix(in srgb, var(--c) 12%, #ffffff);
  border-radius: 4px; padding: 0 5px; line-height: 15px; letter-spacing: 0.02em; font-weight: 600;
}
.val {
  font-size: 11px; color: #546b82; font-variant-numeric: tabular-nums;
  flex: 1 1 auto; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cost {
  flex: 0 0 auto; margin-left: auto;
  font-size: 10px; color: #7a8ba0; font-variant-numeric: tabular-nums;
  background: #eef3f9; border-radius: 4px; padding: 0 5px; line-height: 15px;
}
.track { height: 4px; border-radius: 2px; background: #e2e8f0; margin-top: 6px; overflow: hidden; }
.fill { height: 100%; background: var(--c); transition: width 0.4s ease; }
.dh { width: 10px; height: 10px; min-width: 10px; min-height: 10px; background: #ffffff; border: 2px solid var(--c); }
</style>
