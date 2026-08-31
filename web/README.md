# DocGraph Web 前端

Vue 3 + Vite + TypeScript + Cytoscape.js（图谱渲染）。

## 开发

```bash
npm install
npm run dev      # http://127.0.0.1:5173（后端 app/main.py 指向该地址）
```

## 构建

```bash
npm run build    # 输出 web/dist（打包 exe 时随包内嵌）
```

## 目录

- `src/App.vue` — 三栏布局（工具栏 / 分组文档树 / 画布 / 详情面板，PRD 6.1）
- `src/components/GraphCanvas.vue` — 图谱画布（Cytoscape.js，FR-501~504）
