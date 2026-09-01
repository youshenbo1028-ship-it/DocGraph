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
const selected = ref<{ kind: "node" | "edge"; data: any } | null>(null);
const detail = ref<any>(null);
const detailLoading = ref(false);
const loading = ref(false);
const hasKey = ref(false);
const search = ref("");
const typeFilter = ref<string>("");
const hideIsolated = ref(false);
const graphMode = ref<"pan" | "move">("move"); // 默认移动节点：点击实体可直接拖动，空白处仍可平移
const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null);
const showSettings = ref(false);
const showExport = ref(false);
const newGroupName = ref("");
const newGroupPreset = ref<"academic" | "legal">("academic");
const copyDoc = ref<any | null>(null);      // 正在选择「复制到哪个分组」的文档
const dragDocId = ref<string | null>(null); // 正在拖拽的文档
const dragOverGroup = ref<string | null>(null);

const apiCfg = ref<ApiConfig>({ base_url: "https://api.deepseek.com/v1", api_key: "", model: "deepseek-chat" });

// ---- Toast 通知 ----
interface ToastAction { label: string; fn: () => void }
interface Toast { id: number; type: "info" | "success" | "error"; msg: string; actions?: ToastAction[] }
const toasts = ref<Toast[]>([]);
let toastId = 0;
function toast(type: Toast["type"], msg: string, actions?: ToastAction[]) {
  const id = ++toastId;
  toasts.value.push({ id, type, msg, actions });
  const ttl = actions?.length ? 15000 : (type === "error" ? 6000 : 3200);
  setTimeout(() => { toasts.value = toasts.value.filter((t) => t.id !== id); }, ttl);
}

// ---- 筛选/统计 ----
const graph = computed(() => {
  const kw = search.value.trim().toLowerCase();
  const nodes = fullGraph.value.nodes.filter((n) => {
    const data = n.data;
    if (typeFilter.value && data.type !== typeFilter.value) return false;
    if (kw && !String(data.label).toLowerCase().includes(kw)) return false;
    return true;
  });
  const ids = new Set(nodes.map((n) => n.data.id));
  let edges = fullGraph.value.edges.filter((e) => ids.has(e.data.source) && ids.has(e.data.target));
  // 隐藏孤立节点：仅保留出现在边中的节点
  if (hideIsolated.value) {
    const connected = new Set(edges.flatMap((e) => [e.data.source, e.data.target]));
    const kept = nodes.filter((n) => connected.has(n.data.id));
    const keptIds = new Set(kept.map((n) => n.data.id));
    edges = edges.filter((e) => keptIds.has(e.data.source) && keptIds.has(e.data.target));
    return { nodes: kept, edges };
  }
  return { nodes, edges };
});
const nodeTypes = computed(() => Array.from(new Set(fullGraph.value.nodes.map((n) => n.data.type || "未知"))));

// ---- 分组与文档（组织查看） ----
// 「默认组」即未分组桶：新导入的文档默认落在这里，显示为「未分组」便于理解
const LEGAL_ET = ["法律/法规文件", "机构/组织", "人员/角色", "权利/义务", "行为/事项", "程序/制度", "处罚/责任", "概念/术语"];
const displayGroupName = (g: any) => (g?.name === "默认组" ? "未分组" : g?.name ?? "");
const groupPresetLabel = (g: any) => {
  if (!g) return "";
  if (g.entity_types?.length === LEGAL_ET.length && g.entity_types.every((t: string, i: number) => t === LEGAL_ET[i])) return "法律";
  if (g.relation_types?.includes("属于") && g.relation_types?.includes("提出")) return "学术";
  return "自定义";
};
const groupDocs = (gid: string) => documents.value.filter((d) => d.group_id === gid);
// 选中分组时只显示该组文档；「全部文件」显示全部
const visibleDocs = computed(() =>
  selectedGroupId.value ? documents.value.filter((d) => d.group_id === selectedGroupId.value) : documents.value,
);

// ---- 业务 ----
async function loadSettings() {
  try {
    const s = await api.getSettings();
    if (s.base_url) apiCfg.value.base_url = s.base_url;
    if (s.model) apiCfg.value.model = s.model;
    hasKey.value = !!s.has_key;
  } catch { /* 后端未启动 */ }
}
async function ensureProject() {
  // 优先恢复上一次/最近的项目（持久化在服务端，重启不丢）
  try {
    const active = await api.activeProject();
    if (active.project) {
      pid.value = active.project.id;
      localStorage.setItem(STORAGE_KEY, pid.value);
      await loadProject();
      return;
    }
  } catch { /* 后端未就绪时继续走新建 */ }
  const p = await api.createProject("我的知识库");
  pid.value = p.project.id;
  localStorage.setItem(STORAGE_KEY, pid.value);
  try { await api.activateProject(pid.value); } catch { /* 忽略 */ }
  await loadProject();
}
async function loadProject() {
  if (!pid.value) return;
  const p = await api.getProject(pid.value);
  project.value = p.project;
  groups.value = p.groups;
  documents.value = p.documents;
  // 默认「全部文件」视图（不自动选中第一个分组，避免用户困惑）
  await refreshGraph();
}
async function refreshGraph() {
  if (!pid.value) return;
  fullGraph.value = await api.getGraph(pid.value, selectedGroupId.value ?? undefined);
}

async function onDeleteDoc(d: any) {
  if (!pid.value) return;
  if (!confirm(`确定删除文档「${d.file_name}」？其抽取的实体与关系也会一并移除。`)) return;
  try {
    await api.deleteDocument(pid.value, d.id);
    await loadProject();
    toast("success", "已删除文档：" + d.file_name);
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  }
}

async function onFileChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const files = Array.from(input.files ?? []);
  if (!files.length || !pid.value) return;
  await importFiles(files);
  input.value = "";
}

async function onFolderChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const files = Array.from(input.files ?? []).filter((f) => /.(pdf|docx)$/i.test(f.name));
  if (!files.length) { toast("info", "所选文件夹中没有 PDF / DOCX 文件"); input.value = ""; return; }
  await importFiles(files);
  input.value = "";
}

async function importFiles(files: File[]) {
  if (!pid.value) return;
  loading.value = true;
  try {
    let ok = 0, skip = 0;
    for (const f of files) {
      try {
        // 导入默认进「全部文件（未分组/默认组）」，之后可拖拽/复制到其他分组
        await api.importDocument(pid.value!, f);
        ok++;
      } catch { skip++; }
    }
    await loadProject();
    toast("success", `已导入 ${ok} 个文档到「全部文件」` + (skip ? `（失败/重名跳过 ${skip} 个）` : ""));
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  } finally {
    loading.value = false;
  }
}
async function onExtract() {
  if (!pid.value) return;
  if (!hasKey.value && !apiCfg.value.api_key) {
    toast("info", "请先在设置中填写 API Key");
    showSettings.value = true;
    return;
  }
  loading.value = true;
  try {
    const summary = await api.extract(pid.value!, selectedGroupId.value, apiCfg.value);
    await loadProject();
    const failed = summary.errors.length;
    if (failed) {
      const firstErr = summary.errors[0]?.error ?? "";
      toast("error",
        `抽取失败 ${failed} 篇：${firstErr.slice(0, 160)}`);
    } else {
      toast("success",
        `完成：${summary.documents} 篇 / ${summary.entities} 实体 / ${summary.relations} 关系`);
    }
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  } finally {
    loading.value = false;
  }
}
async function onSaveSettings() {
  loading.value = true;
  try {
    const s = await api.saveSettings(apiCfg.value);
    hasKey.value = !!s.has_key;
    toast("success", "配置已保存" + (s.has_key ? "，API Key 已安全存储" : ""));
    apiCfg.value.api_key = "";
    showSettings.value = false;
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  } finally {
    loading.value = false;
  }
}
async function onCreateGroup() {
  if (!pid.value || !newGroupName.value.trim()) return;
  try {
    await api.createGroup(pid.value, newGroupName.value.trim(), newGroupPreset.value);
    newGroupName.value = "";
    await loadProject();
    toast("success", "分组已创建（" + (newGroupPreset.value === "legal" ? "法律法规" : "学术论文") + "抽取类型）");
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  }
}
function selectGroup(id: string) { selectedGroupId.value = id || null; refreshGraph(); }

// 拖拽文档 -> 分组 = 移动（FR-310：一个文档属于一个分组）
function onDocDragStart(e: DragEvent, d: any) {
  dragDocId.value = d.id;
  if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; }
}
async function onDropToGroup(groupId: string) {
  const docId = dragDocId.value;
  dragOverGroup.value = null;
  dragDocId.value = null;
  if (!docId || !pid.value) return;
  const g = groups.value.find((x) => x.id === groupId);
  try {
    await api.moveDocument(pid.value, docId, groupId);
    await loadProject();
    toast("success", "已移动文档到「" + displayGroupName(g) + "」");
  } catch (e: any) {
    toast("error", "移动失败：" + String(e?.message ?? e));
  }
}
// 复制到其他分组 = 自动复制 + 重命名（FR-310：跨分组复用同一源文档）
async function doCopyTo(groupId: string) {
  const d = copyDoc.value;
  copyDoc.value = null;
  if (!d || !pid.value) return;
  const g = groups.value.find((x) => x.id === groupId);
  try {
    const nd = await api.copyDocument(pid.value, d.id, groupId);
    await loadProject();
    toast("success", "已复制为「" + nd.file_name + "」到「" + displayGroupName(g) + "」（副本为独立文档，可单独抽取）");
  } catch (e: any) {
    toast("error", "复制失败：" + String(e?.message ?? e));
  }
}
async function onSelect(sel: any) {
  selected.value = sel;
  detail.value = null;
  if (!sel || !pid.value) return;
  detailLoading.value = true;
  try {
    detail.value = sel.kind === "node"
      ? await api.entityDetail(pid.value, sel.data.id)
      : await api.relationDetail(pid.value, sel.data.id);
  } catch { detail.value = null; }
  finally { detailLoading.value = false; }
}

function utf8ToB64(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
function openFolder(dir: string) {
  const api_ = (window as any).pywebview?.api;
  if (api_?.open_folder) api_.open_folder(dir);
  else toast("info", "导出目录：" + dir);
}
// 导出：写入固定导出目录（%LOCALAPPDATA%\DocGraph\exports\<项目名>），并提示路径 + 打开文件夹
async function onExport(kind: "png" | "svg" | "json" | "csv") {
  showExport.value = false;
  if (!pid.value) return;
  try {
    const jobs: { kind: string; filename: string; contentB64?: string }[] = [];
    if (kind === "png") {
      const url = canvasRef.value?.exportPng();
      if (!url) { toast("error", "导出失败：画布暂无内容"); return; }
      jobs.push({ kind: "png", filename: "graph.png", contentB64: url.split(",")[1] ?? "" });
    } else if (kind === "svg") {
      const svg = canvasRef.value?.exportSvg();
      if (!svg) { toast("error", "导出失败：画布暂无内容"); return; }
      jobs.push({ kind: "svg", filename: "graph.svg", contentB64: utf8ToB64(svg) });
    } else if (kind === "json") {
      jobs.push({ kind: "graph.json", filename: "graph.json" });
    } else {
      jobs.push({ kind: "nodes.csv", filename: "nodes.csv" });
      jobs.push({ kind: "edges.csv", filename: "edges.csv" });
    }
    const paths: string[] = [];
    let dir = "";
    for (const j of jobs) {
      const res = await api.saveExport(pid.value, j.kind, j.filename, j.contentB64, selectedGroupId.value ?? undefined);
      paths.push(res.path);
      dir = res.dir;
    }
    toast("success", "已导出 " + paths.length + " 个文件：\n" + paths.join("\n"), [
      { label: "打开文件夹", fn: () => openFolder(dir) },
    ]);
  } catch (e: any) {
    toast("error", "导出失败：" + String(e?.message ?? e));
  }
}

const STATUS_LABEL: Record<string, string> = { pending: "待处理", parsing: "解析中", parsed: "已解析", extracting: "抽取中", extracted: "已抽取", failed: "失败" };

// 窗口控制（打包模式经 window.pywebview.api 调用；浏览器开发模式优雅降级）
const pyweb = () => (window as any).pywebview?.api;
function winMin() { pyweb()?.minimize(); }
function winMax() { pyweb()?.toggle_maximize(); }
function winClose() { pyweb()?.close(); }

// 工具栏自定义窗口拖拽（Windows frameless：pywebview 不实现拖拽区，用 SetWindowPos 程序化移动）
let winDragging = false;
let winDragTimer = 0;
function onToolbarMousedown(e: MouseEvent) {
  const t = e.target as HTMLElement;
  if (t.closest("button, input, label, select, .dropdown-wrap, .settings-pop, .win-btn, .icon-btn")) return;
  if (e.button !== 0) return;
  winDragging = true;
  pyweb()?.start_move();
  const loop = () => {
    if (!winDragging) return;
    pyweb()?.move_window();
    winDragTimer = window.setTimeout(loop, 16); // ~60fps 跟随光标
  };
  winDragTimer = window.setTimeout(loop, 16);
}
function onDocMouseUp() {
  if (!winDragging) return;
  winDragging = false;
  clearTimeout(winDragTimer);
  pyweb()?.end_move();
}

// ---- 模型 API 调用日志 ----
const showTraces = ref(false);
const traces = ref<any[]>([]);
const tracesLoading = ref(false);
const expandedTrace = ref<string | null>(null);

async function onShowTraces() {
  if (!pid.value) return;
  showTraces.value = true;
  tracesLoading.value = true;
  try {
    traces.value = await api.traces(pid.value);
  } catch { traces.value = []; }
  finally { tracesLoading.value = false; }
}
function toggleTrace(id: string) {
  expandedTrace.value = expandedTrace.value === id ? null : id;
}
function fmtLatency(ms: number) {
  return ms >= 1000 ? (ms / 1000).toFixed(2) + "s" : ms + "ms";
}

const TYPE_COLORS: Record<string, string> = {
  "概念/方法/理论": "#4d7cba", 人物: "#e0890c", "组织/机构": "#d64545", "论文/文献": "#2f9e63",
  "数据集/工具": "#7a5bd6", 事件: "#c9a227", 指标: "#b35a8e",
};
function detailColor(type: string) { return TYPE_COLORS[type] ?? "#8a94a6"; }

onMounted(async () => {
  window.addEventListener("mouseup", onDocMouseUp);
  try { await loadSettings(); await ensureProject(); toast("success", "项目已就绪"); }
  catch (e: any) { toast("error", String(e?.message ?? e)); }
  // 自测钩子（仅测试使用，正常使用无副作用）
  if (new URLSearchParams(window.location.search).get("seltest") === "1") {
    (window as any).__docgraph_select_first = () => (canvasRef.value as any)?.selectFirstNode?.();
  }
});
</script>

<template>
  <div class="app-shell">
    <!-- 顶部工具栏 -->
    <header class="toolbar" @mousedown="onToolbarMousedown">
      <div class="brand">
        <span class="logo" />
        <span class="name">DocGraph</span>
        <span class="ver">MVP</span>
      </div>
      <div class="toolbar-actions">
        <label class="btn primary">
          <span class="icon">＋</span> 导入文档
          <input type="file" accept=".pdf,.docx" multiple hidden @change="onFileChange" :disabled="loading" />
        </label>
        <label class="btn">
          <span class="icon">📂</span> 导入文件夹
          <input type="file" webkitdirectory hidden @change="onFolderChange" :disabled="loading" />
        </label>
        <button class="btn accent" :disabled="loading" @click="onExtract">
          <span class="icon" v-if="!loading">⚡</span>
          <span class="spinner" v-else />
          {{ loading ? "处理中…" : "解析并抽取" }}
        </button>
        <button class="btn ghost" :disabled="loading" @click="refreshGraph">刷新</button>
        <div class="dropdown-wrap">
          <button class="btn ghost" @click="showExport = !showExport">导出 ▾</button>
          <div v-if="showExport" class="dropdown">
            <button @click="onExport('png')">导出 PNG 图片</button>
            <button @click="onExport('svg')">导出 SVG 矢量图</button>
            <button @click="onExport('json')">导出图谱 JSON</button>
            <button @click="onExport('csv')">导出 CSV（节点+边）</button>
          </div>
        </div>
        <button class="btn ghost" @click="onShowTraces">调用日志</button>
      </div>
      <span class="spacer" />
      <button class="icon-btn" title="设置 (API 配置)" @click="showSettings = !showSettings">⚙︎</button>
      <div class="win-controls">
        <button class="win-btn" title="最小化" @click="winMin">─</button>
        <button class="win-btn" title="最大化 / 还原" @click="winMax">▢</button>
        <button class="win-btn close" title="关闭" @click="winClose">✕</button>
      </div>

      <!-- 设置弹层 -->
      <div v-if="showSettings" class="settings-pop" @click.stop>
        <div class="pop-title">LLM API 配置</div>
        <label class="field">
          <span>Base URL</span>
          <input v-model="apiCfg.base_url" placeholder="https://api.deepseek.com/v1" />
        </label>
        <label class="field">
          <span>API Key <em v-if="hasKey" class="ok">已保存</em></span>
          <input v-model="apiCfg.api_key" type="password" placeholder="sk-..." />
        </label>
        <label class="field">
          <span>模型</span>
          <input v-model="apiCfg.model" placeholder="deepseek-chat" />
        </label>
        <div class="pop-actions">
          <button class="btn accent sm" :disabled="loading" @click="onSaveSettings">保存配置</button>
        </div>
        <p class="pop-hint">支持任意 OpenAI 兼容接口（DeepSeek / OpenAI / 通义 / Kimi 等）。Key 存储于系统凭据库。</p>
      </div>
    </header>

    <!-- 主区域 -->
    <main class="layout">
      <!-- 左：分组 + 文档（全部文件 = 所有文档；拖文档到分组 = 移动；⧉ = 复制） -->
      <aside class="panel left">
        <div class="sec-head">分组与文档</div>
        <button class="group-item" :class="{ active: !selectedGroupId }" @click="selectGroup('')">
          <span class="gicon">🗂</span> 全部文件 <span class="gcount">{{ documents.length }}</span>
        </button>
        <div
          v-for="g in groups"
          :key="g.id"
          class="group-item"
          :class="{ active: selectedGroupId === g.id, 'drag-over': dragOverGroup === g.id }"
          @click="selectGroup(g.id)"
          @dragover.prevent="dragOverGroup = g.id"
          @dragleave="dragOverGroup = null"
          @drop="onDropToGroup(g.id)"
        >
          <span class="gicon">📁</span> {{ displayGroupName(g) }}
          <span class="gcount">{{ groupDocs(g.id).length }}</span>
          <span class="g-preset">{{ groupPresetLabel(g) }}</span>
        </div>
        <div class="group-add">
          <input v-model="newGroupName" placeholder="新分组名…" @keyup.enter="onCreateGroup" />
          <select v-model="newGroupPreset" class="preset-select" title="抽取类型表预设">
            <option value="academic">学术论文</option>
            <option value="legal">法律法规</option>
          </select>
          <button class="icon-btn sm" title="创建分组" @click="onCreateGroup">＋</button>
        </div>

        <div class="sec-head">文档 <span class="count">{{ visibleDocs.length }}</span></div>
        <div v-if="!visibleDocs.length" class="empty-mini">该视图暂无文档<br />点击「导入文档」开始（默认进入全部文件）</div>
        <div
          v-for="d in visibleDocs"
          :key="d.id"
          class="doc-item"
          draggable="true"
          @dragstart="onDocDragStart($event, d)"
          @dragend="dragDocId = null"
        >
          <span class="doc-name" :title="d.file_name">{{ d.file_name }}</span>
          <span class="pill" :class="'pill-' + d.status">{{ STATUS_LABEL[d.status] ?? d.status }}</span>
          <button class="doc-copy" title="复制到其他分组（自动重命名，副本独立抽取）" @click.stop="copyDoc = d">⧉</button>
          <button class="doc-del" title="删除该文档（含其抽取结果）" @click="onDeleteDoc(d)">✕</button>
        </div>
        <div v-if="dragDocId" class="drag-hint">拖动到上方分组可移动该文档</div>

        <!-- 复制到分组小菜单 -->
        <div v-if="copyDoc" class="copy-pop" @click.stop>
          <div class="pop-title">复制「{{ copyDoc.file_name }}」到：</div>
          <button
            v-for="g in groups"
            :key="g.id"
            class="group-item"
            :disabled="g.id === copyDoc.group_id"
            @click="doCopyTo(g.id)"
          >{{ displayGroupName(g) }}</button>
          <button class="btn ghost sm" @click="copyDoc = null">取消</button>
        </div>
      </aside>

      <!-- 中：图谱 -->
      <section class="canvas-wrap">
        <div class="canvas-toolbar">
          <input v-model="search" class="search" placeholder="搜索实体…" />
          <button v-for="t in nodeTypes" :key="t" class="chip" :class="{ active: typeFilter === t }" @click="typeFilter = typeFilter === t ? '' : t">{{ t }}</button>
          <button class="mode-btn" :class="{'active': graphMode === 'pan'}" @click="graphMode = 'pan'" title="拖拽任意处平移画布">🖐 平移</button>
          <button class="mode-btn" :class="{'active': graphMode === 'move'}" @click="graphMode = 'move'" title="拖拽节点以移动其位置（空白仍可平移）">✋ 移动节点</button>
          <label class="iso-toggle" title="仅显示与其他实体有关联的节点">
            <input type="checkbox" v-model="hideIsolated" /> 隐藏孤立节点
          </label>
          <span class="stats">{{ graph.nodes.length }} 节点 · {{ graph.edges.length }} 关系</span>
        </div>
        <div class="graph-area">
          <GraphCanvas ref="canvasRef" :graph="graph" :mode="graphMode" @select="onSelect" />
          <div v-if="!graph.nodes.length" class="empty-graph">
            <div class="empty-ico">🕸</div>
            <div class="empty-title">图谱为空</div>
            <div class="empty-sub">导入 PDF / Word 文档并点击「解析并抽取」，<br />实体与关系将在这里生成知识网络</div>
          </div>
        </div>
      </section>

      <!-- 右：详情 -->
      <aside class="panel right">
        <div class="sec-head">详情</div>
        <template v-if="selected && detail">
          <template v-if="selected.kind === 'node'">
            <div class="detail-head">
              <span class="dot" :style="{ background: detailColor(detail.type) }" />
              <h3 class="detail-name">{{ detail.canonical_name }}</h3>
            </div>
            <div class="detail-row"><span class="k">类型</span><span class="v">{{ detail.type || "-" }}</span></div>
            <div class="detail-row"><span class="k">置信度</span><span class="v">{{ detail.confidence ? detail.confidence.toFixed(2) : "-" }}</span></div>
            <div class="detail-row"><span class="k">别名</span><span class="v">{{ (detail.aliases || []).join("、") || "-" }}</span></div>
            <div class="detail-row"><span class="k">描述</span><span class="v">{{ detail.description || "-" }}</span></div>
            <div class="detail-row"><span class="k">来源文档</span><span class="v">{{ (detail.source_docs || []).join("、") || "-" }}</span></div>
          </template>
          <template v-else>
            <div class="detail-head">
              <h3 class="detail-name">
                {{ detail.source }}
                <span class="rel-type"> —{{ detail.type }}→ </span>
                {{ detail.target }}
              </h3>
            </div>
            <div class="detail-row"><span class="k">置信度</span><span class="v">{{ detail.confidence ? detail.confidence.toFixed(2) : "-" }}</span></div>
            <div class="detail-row"><span class="k">来源文档</span><span class="v">{{ (detail.source_docs || []).join("、") || "-" }}</span></div>
          </template>

          <div class="sec-head" style="margin-top:14px">原文依据</div>
          <div v-if="(detail.evidence || []).length" class="evidence">
            <div v-for="(ev, i) in detail.evidence" :key="i" class="ev-item">
              <div class="ev-quote">{{ typeof ev === "string" ? ev : ev.quote }}</div>
              <div class="ev-src" v-if="typeof ev !== 'string'">—《{{ ev.document }}》{{ ev.page ? "第 " + ev.page + " 页" : "" }}</div>
            </div>
          </div>
          <p v-else class="detail-hint">无直接原文摘录</p>
        </template>
        <div v-else-if="selected" class="empty-mini">加载详情…</div>
        <div v-else class="empty-mini">点击图中的<span class="hlb">实体</span>或<span class="hlb">关系线</span><br />查看来源与原文依据</div>
      </aside>
    </main>

    <!-- 调用日志 Modal（模型 API 请求 / 响应） -->
    <div v-if="showTraces" class="trace-modal" @click.self="showTraces = false">
      <div class="trace-card">
        <div class="trace-head">
          <strong>模型 API 调用日志</strong>
          <span class="trace-count">{{ traces.length }} 条</span>
          <button class="icon-btn sm" @click="showTraces = false">✕</button>
        </div>
        <div class="trace-body">
          <div v-if="tracesLoading" class="trace-empty">加载中…</div>
          <div v-else-if="!traces.length" class="trace-empty">暂无调用记录（执行「解析并抽取」后查看）</div>
          <div v-for="tr in traces" :key="tr.id" class="trace-item" @click="toggleTrace(tr.id)">
            <div class="trace-row">
              <span class="trace-doc">{{ tr.model }}</span>
              <span class="trace-latency">{{ fmtLatency(tr.latency_ms) }}</span>
              <span class="trace-status">{{ tr.status }}</span>
              <span class="trace-time">{{ new Date(tr.created_at).toLocaleTimeString() }}</span>
            </div>
            <div v-if="expandedTrace === tr.id" class="trace-detail">
              <div class="td-label">请求（发送给模型）</div>
              <pre class="td-json">{{ JSON.stringify(tr.request, null, 2) }}</pre>
              <div class="td-label">响应（模型返回）</div>
              <pre class="td-json">{{ tr.response }}</pre>
              <div v-if="tr.raw_response" class="td-label">原始响应</div>
              <pre v-if="tr.raw_response" class="td-json">{{ tr.raw_response }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div class="toasts">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="'toast-' + t.type">
        <span class="toast-msg">{{ t.msg }}</span>
        <button v-for="a in t.actions" :key="a.label" class="toast-act" @click="a.fn()">{{ a.label }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: flex; flex-direction: column; height: 100%; position: relative; }

/* 无边框窗口：工具栏由 JS 触发原生窗口拖动（start_drag），交互元素不触发 */
.toolbar { user-select: none; cursor: default; }
.toolbar .btn, .toolbar .icon-btn, .toolbar input, .toolbar .dropdown-wrap, .toolbar .win-btn, .toolbar .settings-pop { -webkit-app-region: no-drag; }
.win-controls { display: flex; align-items: center; gap: 2px; margin-left: 6px; }
.win-btn { display: flex; align-items: center; justify-content: center; width: 34px; height: 30px; border: none; background: transparent; cursor: pointer; font-size: 13px; color: var(--text-2); border-radius: 6px; }
.win-btn:hover { background: var(--surface-2); }
.win-btn.close:hover { background: #e81123; color: #fff; }

/* 工具栏 */
.toolbar { display: flex; align-items: center; gap: 12px; padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--border); position: relative; z-index: 20; }
.brand { display: flex; align-items: center; gap: 8px; }
.logo { width: 20px; height: 20px; border-radius: 6px; background: linear-gradient(135deg, #4d7cba, #63a6e0); box-shadow: var(--shadow); }
.name { font-weight: 700; font-size: 16px; letter-spacing: .2px; }
.ver { font-size: 11px; color: var(--muted); background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 1px 8px; }
.toolbar-actions { display: flex; align-items: center; gap: 8px; }
.spacer { flex: 1; }

.btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; font-size: 13px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); color: var(--text); cursor: pointer; transition: all .15s; }
.btn:hover { border-color: var(--border-strong); box-shadow: var(--shadow); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn .icon { font-size: 14px; }
.btn.primary { background: var(--surface); }
.btn.accent { background: var(--primary); border-color: var(--primary); color: #fff; }
.btn.accent:hover { background: var(--primary-600); }
.btn.ghost { background: transparent; }
.btn.sm { padding: 5px 12px; font-size: 12px; }
.icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); cursor: pointer; font-size: 16px; }
.icon-btn:hover { box-shadow: var(--shadow); }
.icon-btn.sm { width: 26px; height: 26px; font-size: 14px; }
.spinner { width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.5); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 下拉 */
.dropdown-wrap { position: relative; }
.dropdown { position: absolute; right: 0; top: 110%; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-lg); padding: 6px; min-width: 190px; z-index: 30; }
.dropdown button { display: block; width: 100%; text-align: left; padding: 8px 10px; background: none; border: none; border-radius: var(--radius-sm); cursor: pointer; font-size: 13px; }
.dropdown button:hover { background: var(--surface-2); }

/* 设置弹层 */
.settings-pop { position: absolute; right: 16px; top: 52px; width: 300px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow-lg); padding: 14px; z-index: 40; }
.pop-title { font-weight: 600; margin-bottom: 10px; }
.field { display: block; margin-bottom: 10px; }
.field span { display: block; font-size: 12px; color: var(--text-2); margin-bottom: 4px; }
.field .ok { color: var(--success); font-style: normal; margin-left: 6px; }
.field input { width: 100%; padding: 7px 9px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; outline: none; }
.field input:focus { border-color: var(--primary); }
.pop-actions { margin-top: 6px; }
.pop-hint { font-size: 11px; color: var(--muted); margin: 10px 0 0; line-height: 1.5; }

/* 主布局 */
.layout { display: flex; flex: 1; min-height: 0; }
.panel { position: relative; width: 232px; padding: 14px 12px; overflow-y: auto; background: var(--surface); }
.panel.left { border-right: 1px solid var(--border); }
.panel.right { border-right: 1px solid var(--border); background: var(--surface-2); }
.sec-head { font-size: 12px; font-weight: 600; color: var(--text-2); text-transform: uppercase; letter-spacing: .5px; margin: 12px 4px 8px; display: flex; align-items: center; justify-content: space-between; }
.sec-head .count { background: var(--primary-100); color: var(--primary); border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: 600; }
.sec-head:first-child { margin-top: 2px; }

.group-item { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; padding: 7px 10px; margin-bottom: 2px; border: none; background: transparent; cursor: pointer; border-radius: var(--radius-sm); font-size: 13px; color: var(--text-2); }
.group-item:hover { background: var(--surface-2); }
.group-item.active { background: var(--primary-100); color: var(--primary-600); font-weight: 600; }
.gicon { font-size: 14px; }
.gcount { margin-left: auto; font-size: 11px; color: var(--text-3); background: var(--surface-2); border-radius: 8px; padding: 0 6px; line-height: 16px; }
.g-preset { font-size: 10px; color: var(--primary-600); background: var(--primary-100); border-radius: 4px; padding: 0 4px; margin-left: 4px; flex-shrink: 0; }
.group-item.drag-over { background: var(--primary-100); outline: 2px dashed var(--primary-500); }
.preset-select { font-size: 11px; padding: 3px 4px; border: 1px solid var(--border); border-radius: 4px; background: var(--surface-1); color: var(--text-2); max-width: 84px; }
.doc-copy { border: none; background: transparent; color: #8a94a6; cursor: pointer; font-size: 12px; line-height: 1; padding: 2px 5px; border-radius: 4px; flex-shrink: 0; }
.doc-copy:hover { color: var(--primary-600); background: var(--primary-100); }
.drag-hint { margin-top: 6px; font-size: 11px; color: var(--primary-600); text-align: center; }
.copy-pop { position: absolute; left: 10px; right: 10px; bottom: 60px; z-index: 30; background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-sm); box-shadow: 0 6px 24px rgba(0,0,0,.18); padding: 8px; }
.copy-pop .pop-title { font-size: 12px; color: var(--text-2); margin-bottom: 6px; font-weight: 600; }
.copy-pop .group-item:disabled { opacity: .4; cursor: not-allowed; }
.toast-msg { white-space: pre-line; }
.toast-act { margin-left: 10px; padding: 3px 10px; border: none; border-radius: 4px; background: var(--primary-500); color: #fff; cursor: pointer; font-size: 12px; flex-shrink: 0; }
.toast-act:hover { background: var(--primary-600); }
.group-add { display: flex; gap: 6px; margin: 6px 2px 0; }
.group-add input { flex: 1; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 12px; outline: none; }
.group-add input:focus { border-color: var(--primary); }

.doc-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 8px; margin-bottom: 4px; border-radius: var(--radius-sm); background: var(--surface-2); }
.doc-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.doc-del { border: none; background: transparent; color: #b7c0cd; cursor: pointer; font-size: 12px; line-height: 1; padding: 2px 5px; border-radius: 4px; flex-shrink: 0; }
.doc-del:hover { color: #d64545; background: #fbeaea; }
.pill { font-size: 10px; padding: 2px 7px; border-radius: 8px; white-space: nowrap; }
.pill-pending { background: #eef0f4; color: var(--muted); }
.pill-parsed { background: var(--success-100); color: var(--success); }
.pill-extracting { background: #e9edfb; color: #4756b8; }
.pill-extracted { background: var(--primary-100); color: var(--primary-600); }
.pill-failed { background: var(--error-100); color: var(--error); }
.empty-mini { color: var(--muted); font-size: 12px; text-align: center; padding: 22px 10px; line-height: 1.7; }

/* 中间画布 */
.canvas-wrap { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.canvas-toolbar { display: flex; align-items: center; gap: 6px; padding: 8px 12px; background: var(--surface); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.search { width: 200px; padding: 7px 11px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 13px; outline: none; }
.search:focus { border-color: var(--primary); }
.chip { font-size: 11px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); cursor: pointer; color: var(--text-2); }
.chip:hover { border-color: var(--border-strong); }
.chip.active { background: var(--primary); color: #fff; border-color: var(--primary); }
.stats { margin-left: auto; font-size: 12px; color: var(--muted); }
.iso-toggle { font-size: 12px; color: var(--text-2); display: inline-flex; align-items: center; gap: 4px; cursor: pointer; user-select: none; }
.mode-btn { font-size: 11px; padding: 3px 9px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); cursor: pointer; color: var(--text-2); }
.mode-btn.active { background: #e6eef8; border-color: #bad2eb; color: #2c5c8a; font-weight: 600; }
.iso-toggle input { cursor: pointer; }

.graph-area { flex: 1; min-height: 0; position: relative; background: var(--surface); }
.empty-graph { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; color: var(--muted); pointer-events: none; }
.empty-ico { font-size: 44px; margin-bottom: 12px; opacity: .7; }
.empty-title { font-size: 17px; font-weight: 600; color: var(--text-2); margin-bottom: 6px; }
.empty-sub { font-size: 13px; line-height: 1.7; }

/* 右侧详情 */
.detail-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.dot { width: 12px; height: 12px; border-radius: 50%; }
.detail-name { font-size: 16px; margin: 0; }
.detail-row { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px dashed var(--border); font-size: 13px; }
.detail-row .k { color: var(--muted); }
.detail-row .v { color: var(--text); max-width: 60%; text-align: right; word-break: break-all; }
.detail-hint { color: var(--muted); font-size: 12px; margin-top: 14px; }
.rel-type { color: var(--primary); font-weight: 600; margin: 0 4px; font-size: 13px; }
.hlb { color: var(--primary); font-weight: 600; }
.evidence { max-height: 400px; overflow-y: auto; }
.ev-item { padding: 9px 11px; margin-bottom: 8px; background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-sm); border-left: 3px solid var(--primary); }
.ev-quote { font-size: 12.5px; line-height: 1.6; color: var(--text); }
.ev-src { font-size: 11px; color: var(--muted); margin-top: 6px; text-align: right; }

/* Toast */
.toasts { position: fixed; top: 16px; right: 16px; z-index: 100; display: flex; flex-direction: column; gap: 8px; max-width: 360px; }
.toast { padding: 11px 14px; border-radius: var(--radius); box-shadow: var(--shadow-lg); font-size: 13px; color: #fff; opacity: .98; animation: slidein .2s ease; }
.toast-success { background: var(--success); }
.toast-error { background: var(--error); }
.toast-info { background: var(--primary); }
@keyframes slidein { from { transform: translateX(20px); opacity: 0; } to { transform: none; opacity: 1; } }
/* 调用日志 Modal */
.trace-modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 90; }
.trace-card { width: 780px; max-width: 92vw; height: 80vh; background: var(--surface); border-radius: 12px; box-shadow: var(--shadow-lg); display: flex; flex-direction: column; overflow: hidden; }
.trace-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.trace-head strong { font-size: 15px; }
.trace-count { color: var(--muted); font-size: 12px; }
.trace-head .icon-btn { margin-left: auto; }
.trace-body { flex: 1; overflow-y: auto; padding: 10px 14px; }
.trace-empty { color: var(--muted); text-align: center; padding: 30px; }
.trace-item { border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 8px; cursor: pointer; overflow: hidden; }
.trace-item:hover { border-color: var(--border-strong); }
.trace-row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; font-size: 12px; }
.trace-doc { font-weight: 600; }
.trace-latency { color: var(--primary-600); }
.trace-status { color: var(--success); }
.trace-time { margin-left: auto; color: var(--muted); }
.trace-detail { border-top: 1px solid var(--border); padding: 10px 12px; background: var(--surface-2); }
.td-label { font-size: 11px; color: var(--muted); margin: 6px 0 3px; font-weight: 600; }
.td-json { margin: 0; padding: 8px; background: #0f172a; color: #d5e6ff; border-radius: 6px; font-size: 11px; max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word; }

</style>
