<template>
  <div class="common-layout">
    <el-container class="frame-outer">
      <el-header class="frame-header-region">
        <FrameHeader :active-menu="activeMenu" @menu-select="onMenuSelect" />
      </el-header>
      <el-main class="frame-main">
        <keep-alive>
          <component :is="activeComponent" v-bind="activeComponentProps" />
        </keep-alive>
      </el-main>
      <el-footer class="frame-footer">
        <el-text class="footer-text" type="info">Nexus Retrieval Engine · 法规检索平台 v0.1</el-text>
      </el-footer>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { computed, type Component, defineAsyncComponent, ref, onMounted } from 'vue'
import FrameHeader from './FrameHeader.vue'
import { loadAuthState } from '../common/authState.js'

// 页面懒加载（各自独立 chunk，导航到才拉取）
const PlaceholderPage = defineAsyncComponent(() => import('./PlaceholderPage.vue'))
const CredentialsPage = defineAsyncComponent(() => import('./CredentialsPage.vue'))
const IndexCreatePanel = defineAsyncComponent(() => import('./index/IndexCreatePanel.vue'))
const IndexRunsPage = defineAsyncComponent(() => import('./index/IndexRunsPage.vue'))
const GraphExplorerPage = defineAsyncComponent(() => import('./graph/GraphExplorerPage.vue'))

const activeMenu = ref('ask')

onMounted(() => {
  loadAuthState()   // 经 BFF 读 nexus.app_user，拿 displayName / is_admin
})

const componentMap: Record<string, Component> = {
  credentials: CredentialsPage,
  index: IndexCreatePanel,
  runs: IndexRunsPage,
  graph: GraphExplorerPage,
}

const activeComponent = computed(() => componentMap[activeMenu.value] ?? PlaceholderPage)

const activeComponentProps = computed(() => {
  if (componentMap[activeMenu.value]) return {}
  return { menu: activeMenu.value }
})

function onMenuSelect(menuId: string) {
  activeMenu.value = menuId
}
</script>

<style scoped>
.common-layout {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background: var(--beone-bg-page);
  color: var(--beone-text-primary);
  font-family: var(--beone-font-family);
}

.frame-outer {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.frame-header-region {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: var(--beone-midnight-blue);
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
}

.frame-main {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: var(--beone-bg-page);
  display: flex;
  position: relative;
}

.frame-footer {
  height: 30px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  background: var(--beone-bg-panel);
  border-top: 1px solid var(--beone-border);
}

.footer-text {
  font-size: 12px;
  color: var(--beone-text-secondary);
}
</style>
