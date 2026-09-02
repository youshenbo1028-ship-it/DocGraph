
import { chromium } from "@playwright/test";
const browser = await chromium.launch({ channel: "msedge", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 880 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("http://127.0.0.1:8765/?seltest=1", { waitUntil: "networkidle", timeout: 30000 });
await page.waitForSelector(".graph-canvas canvas", { timeout: 30000 });
await page.waitForTimeout(3000);
const winBtns = await page.locator(".win-btn").count();
const collapseBtns = await page.locator(".collapse-btn").count();
console.log("browser winBtns:", winBtns, "collapseBtns:", collapseBtns, "errors:", errors.length);
await browser.close();
