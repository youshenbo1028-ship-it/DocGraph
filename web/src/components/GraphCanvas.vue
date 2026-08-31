<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import cytoscape from "cytoscape";
import cytoscapeSvg from "cytoscape-svg";

cytoscape.use(cytoscapeSvg as any);

const props = defineProps<{ graph: { nodes: any[]; edges: any[] } }>();
const emit = defineEmits<{ (e: "select", data: any): void }>();

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
  });
  cy.on("tap", "node", (evt) => {
    // 高亮邻居，淡化其余（FR-504）
    const node = evt.target;
    const neighbor = node.closedNeighborhood();
    cy.elements().removeClass("faded");
    cy.elements().not(neighbor).addClass("faded");
    emit("select", node.data());
  });
  cy.on("tap", (evt) => {
    if (evt.target === cy) {
      cy.elements().removeClass("faded");
      emit("select", null);
    }
  });
  render();
});

watch(() => props.graph, () => render(), { deep: true });

function render() {
  if (!cy) return;
  cy.elements().remove();
  cy.add(props.graph.nodes as any);
  cy.add(props.graph.edges as any);
  cy.layout({ name: "cose", animate: false, nodeRepulsion: 9000, idealEdgeLength: 130, padding: 40 }).run();
}

function exportPng(): string | null {
  return cy ? cy.png({ full: true, scale: 2 }) : null;
}
function exportSvg(): string | null {
  return cy ? (cy as any).svg({ full: true, scale: 1 }) : null;
}
defineExpose({ exportPng, exportSvg });

onBeforeUnmount(() => { cy?.destroy(); cy = null; });
</script>

<template>
  <div ref="container" class="graph-canvas" />
</template>

<style scoped>
.graph-canvas {
  height: 100%;
  width: 100%;
  /* 浅色点阵网格背景 */
  background-color: #ffffff;
  background-image: radial-gradient(#e2e6ed 1px, transparent 1px);
  background-size: 22px 22px;
}
</style>
