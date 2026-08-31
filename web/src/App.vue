<script setup lang="ts">
import { onMounted, ref } from "vue";
import GraphCanvas from "./components/GraphCanvas.vue";
import { api, type ApiConfig } from "./api";

const STORAGE_KEY = "docgraph_project_id";

const pid = ref<string | null>(localStorage.getItem(STORAGE_KEY));
const project = ref<any>(null);
const groups = ref<any[]>([]);
const documents = ref<any[]>([]);
const selectedGroupId = ref<string | null>(null);
const graph = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
const selected = ref<any>(null);
const loading = ref(false);
const error = ref("");
const notice = ref("");

const apiCfg = ref<ApiConfig>({
  base_url: "https://api.deepseek.com/v1",
  api_key: "",
  model: "deepseek-chat",
});

async function call(fn: () => Promise<void>, okMsg: string) {
  loading.value = true;
  error.value = "";
  notice.value = "";
  try {
    await fn();
    notice.value = okMsg;
  } catch (e: any) {
    error.value = String(e?.message ?? e);
  } finally {
    loading.value = false;
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
  graph.value = await api.getGraph(pid.value, selectedGroupId.value ?? undefined);
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
      "抽取完成：" + summary.documents + " 篇文档 / " + summary.entities + " 实体 / " + summary.relations + " 关系" +
      (summary.errors.length ? "（失败 " + summary.errors.length + " 篇）" : "");
  }, "");
}

function selectGroup(id: string) {
  selectedGroupId.value = id || null;
  refreshGraph();
}

function onSelect(data: any) {
  selected.value = data;
}

onMounted(() => call(ensureProject, "项目已就绪"));
</script>

<template>
  <div class="app-shell">
    <header class="toolbar">
      <strong>DocGraph</strong>
      <span class="badge">M1 dev</span>
      <span class="spacer" />
      <input v-model="apiCfg.base_url" class="cfg" placeholder="base_url" title="OpenAI 兼容 API 地址" />
      <input v-model="apiCfg.api_key" class="cfg" type="password" placeholder="api_key" title="LLM API Key（仅本次调用使用）" />
      <input v-model="apiCfg.model" class="cfg" placeholder="model" title="模型名" />
      <label class="btn">
        导入文档
        <input type="file" accept=".pdf,.docx" hidden @change="onFileChange" :disabled="loading" />
      </label>
      <button class="btn primary" :disabled="loading" @click="onExtract">解析并抽取</button>
      <button class="btn" :disabled="loading" @click="refreshGraph">刷新图谱</button>
    </header>

    <div class="statusbar">
      <span v-if="loading" class="loading">处理中…</span>
      <span v-if="notice" class="notice">{{ notice }}</span>
      <span v-if="error" class="error">{{ error }}</span>
    </div>

    <main class="layout">
      <aside class="panel left">
        <div class="panel-title">分组</div>
        <button class="group-item" :class="{ active: !selectedGroupId }" @click="selectGroup('')">
          全部
        </button>
        <button
          v-for="g in groups"
          :key="g.id"
          class="group-item"
          :class="{ active: selectedGroupId === g.id }"
          @click="selectGroup(g.id)"
        >
          {{ g.name }}
        </button>
        <div class="panel-title">文档（{{ documents.length }}）</div>
        <div v-for="d in documents" :key="d.id" class="doc-item">
          <span class="doc-name" :title="d.file_name">{{ d.file_name }}</span>
          <span class="doc-status" :class="'st-' + d.status">{{ d.status }}</span>
        </div>
      </aside>

      <section class="canvas">
        <GraphCanvas :graph="graph" @select="onSelect" />
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
  gap: 8px;
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
  width: 160px;
  padding: 4px 8px;
  font-size: 12px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
.btn {
  padding: 5px 12px;
  font-size: 13px;
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
  width: 230px;
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
  max-width: 140px;
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
.canvas {
  flex: 1;
  min-width: 0;
}
.hint {
  color: #999;
}
</style>
