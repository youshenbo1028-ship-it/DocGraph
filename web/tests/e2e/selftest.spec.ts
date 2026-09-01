import { test, expect } from "@playwright/test";

// 交互自测：覆盖主界面渲染、文档显示、图谱渲染、节点->详情与原文依据、设置/导出弹层。
// 需要后端运行（selftest.ps1 会启动），且种子项目含自测文档+图谱。

test("加载：主界面渲染，无控制台错误", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text()); });

  await page.goto("/?seltest=1");
  await expect(page.getByText("DocGraph").first()).toBeVisible({ timeout: 20000 });
  await expect(page.getByText("分组")).toBeVisible();
  await expect(page.getByText("详情")).toBeVisible();
  await expect(page.getByText("图谱为空").first()).toBeVisible({ timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(2000);
  expect(errors, "存在控制台错误: " + errors.join(" | ")).toEqual([]);
});

test("文档：左栏显示已导入文档，图谱画布出现", async ({ page }) => {
  await page.goto("/?seltest=1");
  await expect(page.locator(".doc-item").first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(2500);
  await expect(page.locator(".graph-canvas canvas").first()).toBeVisible();
});

test("交互：设置弹层可打开", async ({ page }) => {
  await page.goto("/?seltest=1");
  await page.waitForTimeout(2000);
  await page.locator(".icon-btn").first().click();
  await expect(page.getByText("LLM API 配置")).toBeVisible({ timeout: 6000 });
});

test("交互：导出下拉可打开", async ({ page }) => {
  await page.goto("/?seltest=1");
  await page.waitForTimeout(2000);
  await page.getByText("导出").click();
  await expect(page.getByText("导出 PNG 图片")).toBeVisible({ timeout: 6000 });
});

test("详情：点击节点显示实体信息与原文依据", async ({ page }) => {
  await page.goto("/?seltest=1");
  await page.waitForSelector(".graph-canvas canvas", { state: "visible", timeout: 20000 });
  await page.waitForTimeout(3000);
  // 触发首个节点选择（测试钩子）
  await page.evaluate(() => (window as any).__docgraph_select_first?.());
  await page.waitForTimeout(1500);
  await expect(page.getByText("原文依据")).toBeVisible({ timeout: 8000 });
  const evidence = await page.locator(".ev-item").count();
  expect(evidence).toBeGreaterThan(0);
});
test("交互：删除文档（确认后从列表移除）", async ({ page }) => {
  await page.goto("/?seltest=1");
  await expect(page.locator(".doc-item").first()).toBeVisible({ timeout: 20000 });
  const first = page.locator(".doc-item").first();
  const name = (await first.locator(".doc-name").innerText()).trim();
  // 接受删除确认对话框
  page.once("dialog", (d) => d.accept());
  await first.locator(".doc-del").click();
  await page.waitForTimeout(1500);
  // 该文档应从列表移除
  const names = await page.locator(".doc-name").allInnerTexts();
  expect(names.map((s) => s.trim())).not.toContain(name);
});

