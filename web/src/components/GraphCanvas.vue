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
  "概念/方法/理论": "#4e79a7",
  人物: "#f28e2b",
  "组织/机构": "#e15759",
  "论文/文献": "#76b7b2",
  "数据集/工具": "#59a14f",
  事件: "#edc948",
  指标: "#b07aa1",
};

const colorOf = (type: string) => TYPE_COLORS[type] ?? "#999999";

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
          width: 34,
          height: 34,
          "background-color": (ele: any) => colorOf(ele.data("type")),
          "font-size": 12,
          "text-valign": "bottom",
          "text-margin-y": 4,
          "text-wrap": "wrap",
          "text-max-width": 120,
        },
      },
      {
        selector: "edge",
        style: {
          width: 2,
          "line-color": "#c0c0c0",
          "target-arrow-color": "#c0c0c0",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          label: "data(label)",
          "font-size": 10,
          "text-rotation": "autorotate",
        },
      },
      {
        selector: ":selected",
        style: { "border-width": 3, "border-color": "#333333" },
      },
    ],
    layout: { name: "cose", animate: false },
  });
  cy.on("tap", "node", (evt) => emit("select", evt.target.data()));
  cy.on("tap", (evt) => {
    if (evt.target === cy) emit("select", null);
  });
  render();
});

watch(
  () => props.graph,
  () => render(),
  { deep: true },
);

function render() {
  if (!cy) return;
  cy.elements().remove();
  cy.add(props.graph.nodes as any);
  cy.add(props.graph.edges as any);
  cy.layout({ name: "cose", animate: false, nodeRepulsion: 8000, idealEdgeLength: 120 }).run();
}

// 导出（FR-601）
function exportPng(): string | null {
  return cy ? cy.png({ full: true, scale: 2 }) : null; // data URL
}
function exportSvg(): string | null {
  return cy ? (cy as any).svg({ full: true, scale: 1 }) : null;
}

defineExpose({ exportPng, exportSvg });

onBeforeUnmount(() => {
  cy?.destroy();
  cy = null;
});
</script>

<template>
  <div ref="container" class="graph-canvas" />
</template>

<style scoped>
.graph-canvas {
  height: 100%;
  width: 100%;
}
</style>
