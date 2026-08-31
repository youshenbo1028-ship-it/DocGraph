<script setup lang="ts">
// TODO(M1): 左侧分组+文档树、中部图谱画布、右侧详情面板（PRD 6.1 线框）
import GraphCanvas from "./components/GraphCanvas.vue";
</script>

<template>
  <div class="app-shell">
    <header class="toolbar">
      DocGraph <span class="badge">dev</span>
      <span class="spacer" />
      <button disabled>导入文档</button>
      <button disabled>开始抽取</button>
    </header>
    <main class="layout">
      <aside class="panel left">分组 + 文档树（TODO M2）</aside>
      <section class="canvas"><GraphCanvas /></section>
      <aside class="panel right">详情面板（TODO）</aside>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #ccc;
}
.badge {
  font-size: 12px;
  color: #666;
}
.spacer {
  flex: 1;
}
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
}
.panel {
  width: 240px;
  padding: 12px;
  border: 1px dashed #ccc;
  font-size: 13px;
  color: #888;
}
.left {
  border-right: 1px solid #eee;
}
.right {
  border-left: 1px solid #eee;
}
.canvas {
  flex: 1;
  min-width: 0;
}
</style>
