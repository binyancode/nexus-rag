<template>
  <div class="answer-panel">
    <div class="answer-title">回答</div>
    <div v-if="!answer" class="answer-empty">等待生成答案…</div>
    <div v-else class="answer-text">{{ answer }}</div>
    <div v-if="citations.length" class="citations">
      <div class="citations-title">出处（{{ citations.length }}）</div>
      <div v-for="c in citations" :key="c.fullname" class="citation">
        <code>{{ c.fullname }}</code>
        <span v-if="c.quote">{{ c.quote }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  answer?: string | null
  citations?: Array<{ fullname: string; quote?: string | null }>
}>(), { citations: () => [] })
</script>

<style scoped>
.answer-panel { padding: 18px; border: 1px solid var(--beone-border); border-radius: 10px; background: #fff; }
.answer-title { margin-bottom: 12px; font-size: 15px; font-weight: 700; color: var(--beone-midnight-blue); }
.answer-empty { color: var(--beone-text-secondary); font-size: 13px; }
.answer-text { white-space: pre-wrap; line-height: 1.75; font-size: 14px; }
.citations { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--beone-border); }
.citations-title { margin-bottom: 8px; font-size: 13px; font-weight: 600; }
.citation { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border-radius: 7px; background: var(--beone-bg-panel); margin-top: 6px; }
.citation code { color: #2563eb; word-break: break-all; }
.citation span { color: var(--beone-text-secondary); font-size: 12px; }
</style>
