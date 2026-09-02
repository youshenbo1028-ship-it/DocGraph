
import { chromium } from "@playwright/test";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 880 } });
const errors = [];
page.on("pageerror", (e) => errors.push("pageerror: " + String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });
await page.goto("http://127.0.0.1:8765/?seltest=1", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector(".graph-canvas canvas", { timeout: 30000 });
await page.waitForTimeout(6000);
const st = await page.evaluate(() => {
  const cy = window.__docgraph_cy ? window.__docgraph_cy() : null;
  return { cy: !!cy, nodes: cy ? cy.nodes().length : 0, docs: document.querySelectorAll(".doc-item").length, zoom: Math.round((window.__docgraph_view ? window.__docgraph_view().zoom : 0) * 100) / 100 };
});
console.log("PG-mode page:", JSON.stringify(st));
console.log("errors:", errors.length ? errors.join(" | ") : "none");
await browser.close();
console.log("DONE");
