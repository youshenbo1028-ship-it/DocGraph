<script setup lang="ts">
// TODO(M1): Cytoscape.js 图谱渲染（FR-501~504）
//  - 力导向布局 / 缩放平移 / 类型着色 / 邻居高亮 / 详情联动
import { onMounted, onBeforeUnmount, ref } from "vue";

const container = ref<HTMLDivElement | null>(null);

onMounted(() => {
  // TODO(M1): 初始化 cytoscape 实例并绑定后端 /api/graph 数据
});

onBeforeUnmount(() => {
  // TODO(M1): 销毁 cytoscape 实例
});
</script>

<template>
  <div ref="container" class="graph-canvas">图谱画布占位（M1）</div>
</template>

<style scoped>
.graph-canvas {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  background: #fafafa;
}
</style>
