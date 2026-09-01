
import { chromium } from "@playwright/test";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 880 } });
await page.goto("http://127.0.0.1:8765/?seltest=1", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector(".graph-canvas canvas", { timeout: 30000 });
const counts = {};
// 默认（≥1）
await page.waitForTimeout(6000);
counts.default_min1 = await page.evaluate(() => {
  const cy = window.__docgraph_cy();
  return { nodes: cy.nodes().length, edges: cy.edges().length, zoom: Math.round((window.__docgraph_view().zoom) * 100) / 100 };
});
// 切 ≥2
await page.selectOption(".degree-filter", "2");
await page.waitForTimeout(4000);
counts.min2 = await page.evaluate(() => {
  const cy = window.__docgraph_cy();
  return { nodes: cy.nodes().length, edges: cy.edges().length };
});
// 切 ≥3
await page.selectOption(".degree-filter", "3");
await page.waitForTimeout(4000);
counts.min3 = await page.evaluate(() => {
  const cy = window.__docgraph_cy();
  return { nodes: cy.nodes().length, edges: cy.edges().length };
});
// 全部
await page.selectOption(".degree-filter", "0");
await page.waitForTimeout(4000);
counts.all = await page.evaluate(() => {
  const cy = window.__docgraph_cy();
  return { nodes: cy.nodes().length, edges: cy.edges().length };
});
console.log(JSON.stringify(counts, null, 1));
await browser.close();
console.log("DONE");
