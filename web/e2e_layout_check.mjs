
import { chromium } from "@playwright/test";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 880 } });
await page.goto("http://127.0.0.1:8765/?seltest=1", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector(".graph-canvas canvas", { timeout: 30000 });
// 等待 fcose 收敛：轮询直到节点重叠不再明显下降
let prev = -1, stable = 0;
let m = null;
for (let i = 0; i < 30; i++) {
  await page.waitForTimeout(1000);
  m = await page.evaluate(() => {
    const cy = window.__docgraph_cy();
    const ns = cy.nodes().toArray();
    const bb = (n) => n.boundingBox();
    let boxOverlap = 0;
    for (let a = 0; a < ns.length; a++) for (let b = a + 1; b < ns.length; b++) {
      const x = bb(ns[a]), y = bb(ns[b]);
      if (x.x1 < y.x2 && x.x2 > y.x1 && x.y1 < y.y2 && x.y2 > y.y1) boxOverlap++;
    }
    return { nodes: ns.length, overlap: boxOverlap };
  });
  if (m.overlap === prev) { stable++; if (stable >= 3) break; } else stable = 0;
  prev = m.overlap;
}
console.log("FINAL layout:", JSON.stringify(m));
// 截图存档
await page.screenshot({ path: "C:/Users/10274/AppData/Local/Temp/dg_layout_final.png" });
await browser.close();
console.log("DONE");
