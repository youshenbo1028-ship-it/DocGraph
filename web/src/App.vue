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
const canvasRef = ref<InstanceType<typeof GraphCanvas> | null>(null);
const showSettings = ref(false);
const showExport = ref(false);
const newGroupName = ref("");

const apiCfg = ref<ApiConfig>({ base_url: "https://api.deepseek.com/v1", api_key: "", model: "deepseek-chat" });

// ---- Toast 通知 ----
interface Toast { id: number; type: "info" | "success" | "error"; msg: string }
const toasts = ref<Toast[]>([]);
let toastId = 0;
function toast(type: Toast["type"], msg: string) {
  const id = ++toastId;
  toasts.value.push({ id, type, msg });
  setTimeout(() => { toasts.value = toasts.value.filter((t) => t.id !== id); }, type === "error" ? 6000 : 3200);
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
  const edges = fullGraph.value.edges.filter((e) => ids.has(e.data.source) && ids.has(e.data.target));
  return { nodes, edges };
});
const nodeTypes = computed(() => Array.from(new Set(fullGraph.value.nodes.map((n) => n.data.type || "未知"))));

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
  if (!selectedGroupId.value && groups.value.length) selectedGroupId.value = groups.value[0].id;
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
  loading.value = true;
  try {
    await api.importDocument(pid.value!, file, selectedGroupId.value ?? undefined);
    await loadProject();
    toast("success", "文档已导入，点击「解析并抽取」生成图谱");
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  } finally {
    loading.value = false;
    input.value = "";
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
    await api.createGroup(pid.value, newGroupName.value.trim());
    newGroupName.value = "";
    await loadProject();
    toast("success", "分组已创建");
  } catch (e: any) {
    toast("error", String(e?.message ?? e));
  }
}
function selectGroup(id: string) { selectedGroupId.value = id || null; refreshGraph(); }
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

function downloadDataUrl(url: string | null, filename: string) {
  if (!url) return;
  const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
}
function onExport(kind: "png" | "svg" | "json" | "csv") {
  showExport.value = false;
  if (kind === "png") downloadDataUrl(canvasRef.value?.exportPng() ?? null, "graph.png");
  else if (kind === "svg") {
    const svg = canvasRef.value?.exportSvg(); if (!svg) return;
    const u = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    downloadDataUrl(u, "graph.svg"); URL.revokeObjectURL(u);
  } else if (kind === "json" && pid.value) api.downloadExport(pid.value, "graph.json", selectedGroupId.value ?? undefined);
  else if (kind === "csv" && pid.value) {
    api.downloadExport(pid.value, "nodes.csv", selectedGroupId.value ?? undefined);
    api.downloadExport(pid.value, "edges.csv", selectedGroupId.value ?? undefined);
  }
}

const STATUS_LABEL: Record<string, string> = { pending: "待处理", parsing: "解析中", parsed: "已解析", extracting: "抽取中", extracted: "已抽取", failed: "失败" };

// 窗口控制（打包模式经 window.pywebview.api 调用；浏览器开发模式优雅降级）
const pyweb = () => (window as any).pywebview?.api;
function winMin() { pyweb()?.minimize(); }
function winMax() { pyweb()?.toggle_maximize(); }
function winClose() { pyweb()?.close(); }

const TYPE_COLORS: Record<string, string> = {
  "概念/方法/理论": "#4d7cba", 人物: "#e0890c", "组织/机构": "#d64545", "论文/文献": "#2f9e63",
  "数据集/工具": "#7a5bd6", 事件: "#c9a227", 指标: "#b35a8e",
};
function detailColor(type: string) { return TYPE_COLORS[type] ?? "#8a94a6"; }

onMounted(async () => {
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
    <header class="toolbar">
      <div class="brand">
        <span class="logo" />
        <span class="name">DocGraph</span>
        <span class="ver">MVP</span>
      </div>
      <div class="toolbar-actions">
        <label class="btn primary">
          <span class="icon">＋</span> 导入文档
          <input type="file" accept=".pdf,.docx" hidden @change="onFileChange" :disabled="loading" />
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
      <!-- 左：分组 + 文档 -->
      <aside class="panel left">
        <div class="sec-head">分组</div>
        <button class="group-item" :class="{ active: !selectedGroupId }" @click="selectGroup('')">
          <span class="gicon">🗂</span> 全部
        </button>
        <button v-for="g in groups" :key="g.id" class="group-item" :class="{ active: selectedGroupId === g.id }" @click="selectGroup(g.id)">
          <span class="gicon">📁</span> {{ g.name }}
        </button>
        <div class="group-add">
          <input v-model="newGroupName" placeholder="新建分组…" @keyup.enter="onCreateGroup" />
          <button class="icon-btn sm" title="创建分组" @click="onCreateGroup">＋</button>
        </div>

        <div class="sec-head">文档 <span class="count">{{ documents.length }}</span></div>
        <div v-if="!documents.length" class="empty-mini">还没有文档<br />点击「导入文档」开始</div>
        <div v-for="d in documents" :key="d.id" class="doc-item">
          <span class="doc-name" :title="d.file_name">{{ d.file_name }}</span>
          <span class="pill" :class="'pill-' + d.status">{{ STATUS_LABEL[d.status] ?? d.status }}</span>
        </div>
      </aside>

      <!-- 中：图谱 -->
      <section class="canvas-wrap">
        <div class="canvas-toolbar">
          <input v-model="search" class="search" placeholder="搜索实体…" />
          <button v-for="t in nodeTypes" :key="t" class="chip" :class="{ active: typeFilter === t }" @click="typeFilter = typeFilter === t ? '' : t">{{ t }}</button>
          <span class="stats">{{ graph.nodes.length }} 节点 · {{ graph.edges.length }} 关系</span>
        </div>
        <div class="graph-area">
          <GraphCanvas ref="canvasRef" :graph="graph" @select="onSelect" />
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

    <!-- Toast -->
    <div class="toasts">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="'toast-' + t.type">{{ t.msg }}</div>
    </div>
  </div>
</template>

<style scoped>
.app-shell { display: flex; flex-direction: column; height: 100%; position: relative; }

/* 无边框窗口：顶部工具栏作为拖拽区，交互元素设为 no-drag */
.toolbar { -webkit-app-region: drag; }
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
.panel { width: 232px; padding: 14px 12px; overflow-y: auto; background: var(--surface); }
.panel.left { border-right: 1px solid var(--border); }
.panel.right { border-right: 1px solid var(--border); background: var(--surface-2); }
.sec-head { font-size: 12px; font-weight: 600; color: var(--text-2); text-transform: uppercase; letter-spacing: .5px; margin: 12px 4px 8px; display: flex; align-items: center; justify-content: space-between; }
.sec-head .count { background: var(--primary-100); color: var(--primary); border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: 600; }
.sec-head:first-child { margin-top: 2px; }

.group-item { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; padding: 7px 10px; margin-bottom: 2px; border: none; background: transparent; cursor: pointer; border-radius: var(--radius-sm); font-size: 13px; color: var(--text-2); }
.group-item:hover { background: var(--surface-2); }
.group-item.active { background: var(--primary-100); color: var(--primary-600); font-weight: 600; }
.gicon { font-size: 14px; }
.group-add { display: flex; gap: 6px; margin: 6px 2px 0; }
.group-add input { flex: 1; min-width: 0; padding: 6px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-size: 12px; outline: none; }
.group-add input:focus { border-color: var(--primary); }

.doc-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 8px; margin-bottom: 4px; border-radius: var(--radius-sm); background: var(--surface-2); }
.doc-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
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
</style>
