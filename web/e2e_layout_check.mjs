
import { chromium } from "@playwright/test";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 880 } });
await page.goto("http://127.0.0.1:8765/?seltest=1", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector(".graph-canvas canvas", { timeout: 30000 });
// 等待布局完成（轮询 zoom 稳定在 0.75）
let st = null;
for (let i = 0; i < 40; i++) {
  await page.waitForTimeout(1000);
  st = await page.evaluate(() => {
    const cy = window.__docgraph_cy();
    const v = window.__docgraph_view();
    return { nodes: cy.nodes().length, zoom: Math.round(v.zoom * 100) / 100, pan: v.pan };
  });
  if (st.zoom >= 0.7) break;
}
console.log("initial view:", JSON.stringify(st));
// 初始视图内的可读性：渲染字号 + 视图内节点数
const rd = await page.evaluate(() => {
  const cy = window.__docgraph_cy();
  const vp = { x1: 0, y1: 0, x2: 1440, y2: 880 };
  let visible = 0;
  cy.nodes().forEach((n) => {
    const p = n.renderedPosition();
    if (p.x >= vp.x1 && p.x <= vp.x2 && p.y >= vp.y1 && p.y <= vp.y2) visible++;
  });
  return { fontSizePx: Math.round(11 * cy.zoom() * 10) / 10, visibleNodes: visible, total: cy.nodes().length };
});
console.log("readability:", JSON.stringify(rd));
await page.screenshot({ path: "C:/Users/10274/AppData/Local/Temp/dg_v0501.png" });
await browser.close();
console.log("DONE");
