<template>
  <div class="answer-panel">
    <div class="answer-title">回答</div>
    <div v-if="!answer" class="answer-empty">等待生成答案…</div>
    <div v-else class="answer-text">{{ answer }}</div>
    <div v-if="citations.length" class="citations">
      <div class="citations-title">出处（{{ citations.length }}）</div>
      <div v-for="(c, index) in citations" :key="`${c.group || ''}:${c.assertion_id || ''}:${c.block_key}`" class="citation">
        <div class="citation-head">
          <span class="citation-index">{{ index + 1 }}</span>
          <div class="citation-source">
            <b>{{ sourceTitle(c) }}</b>
            <small>{{ sourceLocation(c) }}</small>
          </div>
          <span v-if="sourceGroup(c)" class="citation-group">{{ sourceGroup(c) }}</span>
          <span v-if="c.category" class="citation-category">{{ c.category }}</span>
        </div>
        <blockquote>{{ c.quote }}</blockquote>
        <details class="citation-ids">
          <summary>技术标识</summary>
          <code v-if="c.assertion_id">Assertion：{{ c.assertion_id }}</code>
          <code>Block：{{ c.block_key }}</code>
          <code v-if="c.document_id">Document：{{ c.document_id }}</code>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { QueryCitation } from '../../backend/Query.js'

withDefaults(defineProps<{
  answer?: string | null
  citations?: QueryCitation[]
}>(), { citations: () => [] })

function sourceTitle(citation: QueryCitation) {
  if (citation.title) return `《${citation.title}》`
  if (citation.group_label) return `《${citation.group_label}》`
  return '索引原文'
}

function sourceGroup(citation: QueryCitation) {
  if (!citation.group_label || citation.group_label === citation.title) return ''
  return citation.group_label
}

function sourceLocation(citation: QueryCitation) {
  const parts: string[] = []
  if (citation.heading_path) parts.push(citation.heading_path)
  if (citation.article_no) parts.push(`第${citation.article_no}条`)
  if (citation.paragraph_no) parts.push(`第${citation.paragraph_no}款`)
  if (citation.item_no) parts.push(`第${citation.item_no}项`)
  if (!parts.length && citation.ordinal != null) parts.push(`第 ${citation.ordinal} 个原文块`)
  if (!parts.length) {
    const match = citation.block_key.match(/:article-([^:]+)(?::|$)/)
    if (match?.[1]) parts.push(`第${match[1]}条`)
  }
  return parts.join(' · ') || '原文依据'
}
</script>

<style scoped>
.answer-panel { padding: 18px; border: 1px solid var(--beone-border); border-radius: 10px; background: #fff; }
.answer-title { margin-bottom: 12px; font-size: 15px; font-weight: 700; color: var(--beone-midnight-blue); }
.answer-empty { color: var(--beone-text-secondary); font-size: 13px; }
.answer-text { white-space: pre-wrap; line-height: 1.75; font-size: 14px; }
.citations { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--beone-border); }
.citations-title { margin-bottom: 8px; font-size: 13px; font-weight: 600; }
.citation { display:flex; flex-direction:column; gap:9px; padding:12px 14px; border:1px solid #e2eaf1; border-radius:9px; background:var(--beone-bg-panel); margin-top:8px; }
.citation-head { display:flex; align-items:center; gap:9px; min-width:0; }
.citation-index { width:23px; height:23px; flex:0 0 23px; display:grid; place-items:center; border-radius:50%; background:#e0eff9; color:#2f7cb4; font-size:11px; font-weight:700; }
.citation-source { min-width:0; flex:1; display:flex; flex-direction:column; gap:2px; }
.citation-source b { overflow:hidden; color:#203246; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
.citation-source small { overflow:hidden; color:var(--beone-text-secondary); font-size:11px; text-overflow:ellipsis; white-space:nowrap; }
.citation-group,.citation-category { flex:0 0 auto; padding:2px 7px; border-radius:10px; background:#e9f4ed; color:#2e7d4e; font-size:10px; }
.citation-category { background:#edf3f8; color:#61778b; }
.citation blockquote { margin:0; padding:8px 10px; border-left:3px solid #9ec9e3; background:#fff; color:var(--beone-text-secondary); font-size:12px; line-height:1.65; white-space:pre-wrap; }
.citation-ids { color:#7c8c9b; font-size:10px; }
.citation-ids summary { width:max-content; cursor:pointer; user-select:none; }
.citation-ids code { display:block; margin-top:4px; color:#6d7f91; font-size:10px; line-height:1.45; word-break:break-all; }
</style>
