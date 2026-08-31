<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import GraphCanvas from "./components/GraphCanvas.vue";
import { api, type ApiConfig } from "./api";

const STORAGE_KEY = "docgraph_project_id";

const pid = ref<string | null>(localStorage.getItem(STORAGE_KEY));
const project = ref<any>(null);
const groups = ref<any[]>([]);
const documents = ref<any[]>([]);
const selectedGroupId = ref<string | null>(null);
const fullGraph = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
const selected = ref<any>(null);
const loading = ref(false);
const error = ref("");
const notice = ref("");
const hasKey = ref(false);
const search = ref("");
const typeFilter = ref<string>("");
const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null);

const apiCfg = ref<ApiConfig>({
  base_url: "https://api.deepseek.com/v1",
  api_key: "",
  model: "deepseek-chat",
});

// 客户端搜索 + 类型筛选（FR-506/507）
const graph = computed(() => {
  const kw = search.value.trim().toLowerCase();
  const nodes = fullGraph.value.nodes.filter((n) => {
    const data = n.data;
    if (typeFilter.value && data.type !== typeFilter.value) return false;
    if (kw && !String(data.label).toLowerCase().includes(kw)) return false;
    return true;
  });
  const ids = new Set(nodes.map((n) => n.data.id));
  const edges = fullGraph.value.edges.filter((e) => ids.has(e.data.source) && ids.has(e.data.target));
  return { nodes, edges };
});

const nodeTypes = computed(() => {
  const set = new Set<string>();
  for (const n of fullGraph.value.nodes) set.add(n.data.type || "未知");
  return Array.from(set);
});

async function call(fn: () => Promise<void>, okMsg: string) {
  loading.value = true;
  error.value = "";
  notice.value = "";
  try {
    await fn();
    if (okMsg) notice.value = okMsg;
  } catch (e: any) {
    error.value = String(e?.message ?? e);
  } finally {
    loading.value = false;
  }
}

async function loadSettings() {
  try {
    const s = await api.getSettings();
    if (s.base_url) apiCfg.value.base_url = s.base_url;
    if (s.model) apiCfg.value.model = s.model;
    hasKey.value = !!s.has_key;
  } catch {
    /* 后端未启动时忽略 */
  }
}

async function ensureProject() {
  if (pid.value) {
    await loadProject();
    return;
  }
  const p = await api.createProject("我的知识库");
  pid.value = p.project.id;
  localStorage.setItem(STORAGE_KEY, pid.value);
  await loadProject();
}

async function loadProject() {
  if (!pid.value) return;
  const p = await api.getProject(pid.value);
  project.value = p.project;
  groups.value = p.groups;
  documents.value = p.documents;
  if (!selectedGroupId.value && groups.value.length) {
    selectedGroupId.value = groups.value[0].id;
  }
  await refreshGraph();
}

async function refreshGraph() {
  if (!pid.value) return;
  fullGraph.value = await api.getGraph(pid.value, selectedGroupId.value ?? undefined);
}

async function onFileChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !pid.value) return;
  await call(async () => {
    await api.importDocument(pid.value!, file, selectedGroupId.value ?? undefined);
    await loadProject();
  }, "文档已导入，点击「解析并抽取」生成图谱");
  input.value = "";
}

async function onExtract() {
  if (!pid.value) return;
  await call(async () => {
    const summary = await api.extract(pid.value!, selectedGroupId.value, apiCfg.value);
    await loadProject();
    notice.value =
      "抽取完成：" + summary.documents + " 篇 / " + summary.entities + " 实体 / " +
      summary.relations + " 关系" +
      (summary.errors.length ? "（失败 " + summary.errors.length + " 篇：" + summary.errors.map((e: any) => e.document).join("、") + "）" : "");
  }, "");
}

async function onSaveSettings() {
  await call(async () => {
    const s = await api.saveSettings(apiCfg.value);
    hasKey.value = !!s.has_key;
    apiCfg.value.api_key = ""; // 保存后清空输入框（Key 已入凭据库）
  }, "配置已保存" + (hasKey.value ? "，API Key 已安全存储" : ""));
}

function selectGroup(id: string) {
  selectedGroupId.value = id || null;
  refreshGraph();
}

function onSelect(data: any) {
  selected.value = data;
}

function downloadDataUrl(url: string | null, filename: string) {
  if (!url) return;
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
}

function onExportPng() {
  downloadDataUrl(canvasRef.value?.exportPng() ?? null, "graph.png");
}
function onExportSvg() {
  const svg = canvasRef.value?.exportSvg();
  if (!svg) return;
  const blob = new Blob([svg], { type: "image/svg+xml" });
  const url = URL.createObjectURL(blob);
  downloadDataUrl(url, "graph.svg");
  URL.revokeObjectURL(url);
}
function onExportJson() {
  if (pid.value) api.downloadExport(pid.value, "graph.json", selectedGroupId.value ?? undefined);
}
function onExportCsv() {
  if (!pid.value) return;
  api.downloadExport(pid.value, "nodes.csv", selectedGroupId.value ?? undefined);
  api.downloadExport(pid.value, "edges.csv", selectedGroupId.value ?? undefined);
}

onMounted(() => call(async () => {
  await loadSettings();
  await ensureProject();
}, "项目已就绪"));
</script>

<template>
  <div class="app-shell">
    <header class="toolbar">
      <strong>DocGraph</strong>
      <span class="badge">M1 dev</span>
      <span class="spacer" />
      <input v-model="apiCfg.base_url" class="cfg" placeholder="base_url" title="OpenAI 兼容 API 地址" />
      <input v-model="apiCfg.api_key" class="cfg" type="password" placeholder="api_key" title="LLM API Key" />
      <input v-model="apiCfg.model" class="cfg" placeholder="model" title="模型名" />
      <button class="btn" :disabled="loading" @click="onSaveSettings">保存配置</button>
      <label class="btn">
        导入文档
        <input type="file" accept=".pdf,.docx" hidden @change="onFileChange" :disabled="loading" />
      </label>
      <button class="btn primary" :disabled="loading" @click="onExtract">解析并抽取</button>
      <button class="btn" :disabled="loading" @click="refreshGraph">刷新</button>
      <span class="sep" />
      <span class="btn-group-label">导出</span>
      <button class="btn" @click="onExportPng">PNG</button>
      <button class="btn" @click="onExportSvg">SVG</button>
      <button class="btn" @click="onExportJson">JSON</button>
      <button class="btn" @click="onExportCsv">CSV</button>
    </header>

    <div class="statusbar">
      <span v-if="loading" class="loading">处理中…</span>
      <span v-if="hasKey" class="notice">Key 已保存</span>
      <span v-if="notice" class="notice">{{ notice }}</span>
      <span v-if="error" class="error">{{ error }}</span>
    </div>

    <main class="layout">
      <aside class="panel left">
        <div class="panel-title">分组</div>
        <button class="group-item" :class="{ active: !selectedGroupId }" @click="selectGroup('')">全部</button>
        <button
          v-for="g in groups"
          :key="g.id"
          class="group-item"
          :class="{ active: selectedGroupId === g.id }"
          @click="selectGroup(g.id)"
        >{{ g.name }}</button>
        <div class="panel-title">文档（{{ documents.length }}）</div>
        <div v-for="d in documents" :key="d.id" class="doc-item">
          <span class="doc-name" :title="d.file_name">{{ d.file_name }}</span>
          <span class="doc-status" :class="'st-' + d.status">{{ d.status }}</span>
        </div>
      </aside>

      <section class="canvas-wrap">
        <div class="canvas-toolbar">
          <input v-model="search" class="search" placeholder="搜索实体…" />
          <button
            v-for="t in nodeTypes"
            :key="t"
            class="chip"
            :class="{ active: typeFilter === t }"
            @click="typeFilter = typeFilter === t ? '' : t"
          >{{ t }}</button>
          <span class="count">{{ graph.nodes.length }} 节点 / {{ graph.edges.length }} 边</span>
        </div>
        <GraphCanvas ref="canvasRef" :graph="graph" @select="onSelect" />
      </section>

      <aside class="panel right">
        <div class="panel-title">详情</div>
        <template v-if="selected">
          <h3>{{ selected.label }}</h3>
          <p>类型：{{ selected.type }}</p>
          <p>置信度：{{ selected.confidence ? selected.confidence.toFixed(2) : "-" }}</p>
        </template>
        <p v-else class="hint">点击图谱中的节点查看详情</p>
      </aside>
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
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #ddd;
  flex-wrap: wrap;
}
.badge {
  font-size: 12px;
  color: #888;
}
.spacer {
  flex: 1;
}
.cfg {
  width: 150px;
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.btn {
  padding: 5px 10px;
  font-size: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}
.btn.primary {
  background: #4e79a7;
  color: #fff;
  border-color: #4e79a7;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.sep {
  width: 1px;
  height: 20px;
  background: #ddd;
  margin: 0 4px;
}
.btn-group-label {
  font-size: 12px;
  color: #888;
}
.statusbar {
  padding: 4px 12px;
  font-size: 12px;
  min-height: 20px;
  border-bottom: 1px solid #eee;
}
.loading {
  color: #4e79a7;
}
.notice {
  color: #2e7d32;
  margin-right: 8px;
}
.error {
  color: #c62828;
}
.layout {
  display: flex;
  flex: 1;
  min-height: 0;
}
.panel {
  width: 220px;
  padding: 10px;
  overflow-y: auto;
  font-size: 13px;
  background: #fafafa;
}
.left {
  border-right: 1px solid #eee;
}
.right {
  border-left: 1px solid #eee;
}
.panel-title {
  font-weight: 600;
  margin: 8px 0 4px;
  color: #555;
}
.group-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 4px 8px;
  margin-bottom: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 4px;
}
.group-item.active {
  background: #e3edf7;
  color: #1e5a8a;
}
.doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 8px;
  border-bottom: 1px dashed #eee;
}
.doc-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 130px;
}
.doc-status {
  font-size: 11px;
  color: #888;
}
.st-parsed {
  color: #2e7d32;
}
.st-extracted {
  color: #4e79a7;
}
.st-failed {
  color: #c62828;
}
.canvas-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid #eee;
  flex-wrap: wrap;
}
.search {
  width: 180px;
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.chip {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid #ccc;
  border-radius: 10px;
  background: #fff;
  cursor: pointer;
}
.chip.active {
  background: #4e79a7;
  color: #fff;
  border-color: #4e79a7;
}
.count {
  margin-left: auto;
  font-size: 12px;
  color: #888;
}
.hint {
  color: #999;
}
</style>
