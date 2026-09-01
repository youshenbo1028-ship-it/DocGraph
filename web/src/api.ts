// DocGraph API 客户端（后端内置服务 http://127.0.0.1:8765）
const BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://127.0.0.1:8765";

export interface ApiConfig {
  base_url: string;
  api_key: string;
  model: string;
}

async function request(path: string, init?: RequestInit): Promise<any> {
  const resp = await fetch(BASE + path, init);
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* 忽略非 JSON 响应体 */
    }
    throw new Error(detail);
  }
  return resp.json();
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

async function downloadFromApi(path: string, filename: string) {
  const resp = await fetch(BASE + path);
  if (!resp.ok) throw new Error("下载失败：" + resp.status);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  health: () => request("/api/health"),

  createProject: (name: string) => request("/api/projects", json("POST", { name })),

  getProject: (pid: string) => request("/api/projects/" + pid),

  activeProject: () => request("/api/projects/active"),

  activateProject: (pid: string) =>
    request("/api/projects/" + pid + "/activate", { method: "POST" }),

  createGroup: (pid: string, name: string) =>
    request("/api/projects/" + pid + "/groups", json("POST", { name })),

  importDocument: (pid: string, file: File, groupId?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (groupId) fd.append("group_id", groupId);
    return request("/api/projects/" + pid + "/documents", { method: "POST", body: fd });
  },

  parseDocument: (pid: string, docId: string) =>
    request("/api/projects/" + pid + "/documents/" + docId + "/parse", { method: "POST" }),

  deleteDocument: (pid: string, docId: string) =>
    request("/api/projects/" + pid + "/documents/" + docId, { method: "DELETE" }),

  extract: (pid: string, groupId: string | null, apiCfg: ApiConfig) =>
    request(
      "/api/projects/" + pid + "/extract",
      json("POST", { group_id: groupId, api: apiCfg }),
    ),

  getGraph: (pid: string, groupId?: string) =>
    request(
      "/api/projects/" + pid + "/graph" +
        (groupId ? "?group_id=" + encodeURIComponent(groupId) : ""),
    ),

  getSettings: () => request("/api/settings"),

  saveSettings: (cfg: ApiConfig) =>
    request(
      "/api/settings",
      json("POST", { base_url: cfg.base_url, api_key: cfg.api_key, model: cfg.model }),
    ),

  entityDetail: (pid: string, eid: string) =>
    request("/api/projects/" + pid + "/entities/" + eid),

  relationDetail: (pid: string, rid: string) =>
    request("/api/projects/" + pid + "/relations/" + rid),

  traces: (pid: string, documentId?: string) =>
    request(
      "/api/projects/" + pid + "/traces" +
        (documentId ? "?document_id=" + encodeURIComponent(documentId) : ""),
    ),

  downloadExport: (pid: string, kind: "nodes.csv" | "edges.csv" | "graph.json", groupId?: string) =>
    downloadFromApi(
      "/api/projects/" + pid + "/export/" + kind +
        (groupId ? "?group_id=" + encodeURIComponent(groupId) : ""),
      kind,
    ),
};
