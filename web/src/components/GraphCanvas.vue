<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape from "cytoscape";
import cytoscapeSvg from "cytoscape-svg";

cytoscape.use(cytoscapeSvg as any);

const props = defineProps<{ graph: { nodes: any[]; edges: any[] }; mode?: "pan" | "move" }>();
const emit = defineEmits<{ (e: "select", sel: { kind: "node" | "edge"; data: any }): void }>();

const container = ref<HTMLDivElement | null>(null);
let cy: cytoscape.Core | null = null;

const TYPE_COLORS: Record<string, string> = {
  "概念/方法/理论": "#4d7cba",
  人物: "#e0890c",
  "组织/机构": "#d64545",
  "论文/文献": "#2f9e63",
  "数据集/工具": "#7a5bd6",
  事件: "#c9a227",
  指标: "#b35a8e",
};
const colorOf = (type: string) => TYPE_COLORS[type] ?? "#8a94a6";

onMounted(() => {
  if (!container.value) return;
  cy = cytoscape({
    container: container.value,
    elements: [],
    style: [
      {
        selector: "node",
        style: {
          "grabbable": true,
          label: "data(label)",
          width: 40,
          height: 40,
          "background-color": (ele: any) => colorOf(ele.data("type")),
          "border-width": 2,
          "border-color": "#ffffff",
          "font-size": 12,
          "font-weight": 600,
          color: "#33404f",
          "text-valign": "bottom",
          "text-margin-y": 6,
          "text-wrap": "wrap",
          "text-max-width": 140,
          "overlay-opacity": 0,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#b9c2cf",
          "line-curvature": 0.08,
          "target-arrow-color": "#9aa6b5",
          "target-arrow-shape": "triangle",
          "target-arrow-width": 6,
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 10,
          color: "#7a8695",
          "text-rotation": "autorotate",
          "overlay-opacity": 0,
        },
      },
      {
        selector: ":selected",
        style: { "border-width": 3, "border-color": "#1f2933", "border-opacity": 1 },
      },
      {
        selector: ".faded",
        style: { opacity: 0.12 },
      },
    ],
    layout: { name: "cose", animate: false },
    // 交互：拖拽空白平移、滚轮缩放（显式开启，确保可用）
    userPanningEnabled: true,
    userZoomingEnabled: true,
    boxSelectionEnabled: false,
  });
  cy.on("tap", "node", (evt) => _select(evt.target));
  cy.on("tap", "edge", (evt) => {
    cy.elements().removeClass("faded");
    emit("select", { kind: "edge", data: evt.target.data() });
  });
  cy.on("tap", (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass("faded");
      emit("select", null as any);
    }
  });
  // 供自动化读取视口（平移/缩放），正常使用无副作用
  (window as any).__docgraph_view = () => ({ pan: cy?.pan(), zoom: cy?.zoom() });
  cy.autoungrabify(props.mode === "pan"); // 默认平移模式
  render();
});

watch(
  () => props.mode,
  (m) => { cy?.autoungrabify(m === "pan" || !m); }
);

watch(() => props.graph, () => render(), { deep: true });

function render() {
  if (!cy) return;
  cy.elements().remove();
  cy.add(props.graph.nodes as any);
  cy.add(props.graph.edges as any);
  cy.layout({ name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 130, padding: 40 }).run();
}

function _select(node: any) {
  const neighbor = node.closedNeighborhood();
  cy?.elements().removeClass("faded");
  cy?.elements().not(neighbor).addClass("faded");
  emit("select", { kind: "node", data: node.data() });
}

// 测试钩子：供自动化触发首个节点选择（原节点 tap 逻辑复用）
function selectFirstNode() {
  const first = cy?.nodes().first();
  if (first && first.length) _select(first);
}

function zoomIn() {
  if (cy) cy.zoom({ level: cy.zoom() * 1.2 });
}
function zoomOut() {
  if (cy) cy.zoom({ level: cy.zoom() / 1.2 });
}
function fit() {
  if (cy) cy.fit(undefined, 40);
}

function exportPng(): string | null {
  return cy ? cy.png({ full: true, scale: 2 }) : null;
}
function exportSvg(): string | null {
  return cy ? (cy as any).svg({ full: true, scale: 1 }) : null;
}
defineExpose({ exportPng, exportSvg, selectFirstNode });

onBeforeUnmount(() => { cy?.destroy(); cy = null; });
</script>

<template>
  <div class="graph-wrap">
    <div ref="container" class="graph-canvas" />
    <div class="graph-hint">{{ props.mode === "move" ? "✋ 拖拽节点可移动 · 空白处平移 · 滚轮缩放" : "🖐 拖拽任意处平移 · 滚轮缩放" }}</div>
    <div class="graph-controls">
      <button class="gc" title="放大" @click="zoomIn">＋</button>
      <button class="gc" title="缩小" @click="zoomOut">−</button>
      <button class="gc" title="适应视图" @click="fit">⤢</button>
    </div>
  </div>
</template>

<style scoped>
.graph-wrap {
  position: relative;
  height: 100%;
  width: 100%;
}
.graph-canvas {
  height: 100%;
  width: 100%;
  /* 浅色点阵网格背景 */
  background-color: #ffffff;
  background-image: radial-gradient(#e2e6ed 1px, transparent 1px);
  background-size: 22px 22px;
}
.graph-hint {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  color: #9aa6b5;
  background: rgba(255, 255, 255, .85);
  padding: 4px 12px;
  border-radius: 14px;
  border: 1px solid #e2e6ed;
  pointer-events: none;
  user-select: none;
}
.graph-controls {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gc {
  width: 32px;
  height: 32px;
  border: 1px solid #d4d9e2;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  font-size: 15px;
  color: #52606d;
  box-shadow: 0 1px 2px rgba(16,24,40,.06);
}
.gc:hover {
  border-color: #b7c0cd;
}
</style>
