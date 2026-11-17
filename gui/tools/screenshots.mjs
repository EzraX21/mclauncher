// 截 README / 官网用的界面图。
//
//   cd gui && npm run shots
//
// 做的事：造一个演示游戏目录 → 起本地服务 → 用 Chromium 逐页截图 → 关服务。
// 图存到 docs/，文件名沿用旧的，这样 README 和官网（MCL-web）都不用改引用。
//
// 需要：playwright（devDependency）+ `npx playwright install chromium`。

import { spawn } from "node:child_process";
import { mkdir, rm, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch {
  console.error(
    "截图需要 playwright（可选依赖）：\n" +
    "  cd gui && npm install --include=optional && npx playwright install chromium\n" +
    "然后再跑 npm run shots。",
  );
  process.exit(1);
}

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "../..");
const DOCS = resolve(REPO, "docs");
const WORK = resolve(REPO, ".screenshots");
const PORT = Number(process.env.MCL_SHOT_PORT || 8791);
const BASE = `http://127.0.0.1:${PORT}/`;
const PYTHON = process.env.MCL_PYTHON || resolve(REPO, ".venv/bin/python");

// 和官网 / README 里 <img width="1200" height="760"> 的比例对齐，避免被 object-fit 裁掉
const VIEWPORT = { width: 1200, height: 760 };

// file 沿用旧名字（README 和官网都引用这些名字）
const SHOTS = [
  { file: "gui-versions.png", hash: "#/versions", wait: "#launch-main", dark: false },
  { file: "gui-instance.png", hash: "#/instance", wait: "#instance-detail .kv-grid", dark: false },
  { file: "gui-install.png", hash: "#/download", wait: "#remote-list .list-row", dark: false },
  { file: "gui-mods.png", hash: "#/download", tab: "mods",
    type: { selector: "#mods-query", text: "sodium" }, press: "#mods-search",
    wait: "#mod-results .list-row", dark: false },
  { file: "gui-datapacks.png", hash: "#/download", tab: "datapack",
    select: { selector: "#dp-world", value: "新世界" }, wait: "#dp-local .list-row", dark: false },
  { file: "gui-resources.png", hash: "#/download", tab: "shader",
    type: { selector: "#res-query", text: "complementary" }, press: "#res-search",
    wait: "#res-results .list-row", dark: false },
  { file: "gui-link.png", hash: "#/link", wait: "#link-list .list-row", dark: false },
  { file: "gui-toolbox.png", hash: "#/toolbox", wait: "#tb-checks .check-row", dark: false },
  // 设置默认落在「启动」页，账号/常规/Java/下载都在这一页
  { file: "gui-settings.png", hash: "#/settings", wait: "#set-dir", dark: false },
  { file: "gui-dark.png", hash: "#/instance", wait: "#instance-detail .kv-grid", dark: true },
];

function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { stdio: "inherit", ...options });
    child.on("error", reject);
    child.on("exit", (code) => (code === 0 ? resolvePromise() : reject(new Error(`${command} exited ${code}`))));
  });
}

async function waitForServer(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url + "api/state");
      if (response.ok) return;
    } catch {
      // 还没起来
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`服务没起来：${url}`);
}

async function main() {
  await rm(WORK, { recursive: true, force: true });
  await mkdir(WORK, { recursive: true });
  await mkdir(DOCS, { recursive: true });

  console.log("造演示游戏目录 …");
  await run(PYTHON, [resolve(HERE, "demo_game.py"), resolve(WORK, "fixture")], { cwd: REPO });

  console.log("起本地服务 …");
  const server = spawn(PYTHON, ["-m", "mcl", "gui", "--web", "--no-browser", "--port", String(PORT)], {
    cwd: REPO,
    stdio: "ignore",
    env: { ...process.env, MCL_CONFIG: resolve(WORK, "fixture/config.json") },
  });

  try {
    await waitForServer(BASE);
    const browser = await chromium.launch();
    const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
    const page = await context.newPage();

    for (const shot of SHOTS) {
      await page.goto(BASE + shot.hash, { waitUntil: "domcontentloaded" });
      if (shot.click) {
        await page.click(shot.click);
      }
      if (shot.tab) {
        // 分类是点出来的，先切分类再等目标元素
        await page.waitForSelector(`[data-dtab="${shot.tab}"]`, { timeout: 15000 });
        await page.click(`[data-dtab="${shot.tab}"]`);
      }
      if (shot.select) {
        // 存档按修改时间排序，测试环境里 mtime 可能撞车，截图时显式选一个有内容的
        // option 元素在 Playwright 里不算「可见」，必须用 attached
        await page.waitForSelector(`${shot.select.selector} option[value="${shot.select.value}"]`,
                                   { timeout: 15000, state: "attached" });
        await page.selectOption(shot.select.selector, shot.select.value);
      }
      if (shot.type) {
        await page.fill(shot.type.selector, shot.type.text);
        await page.click(shot.press);
      }
      await page.waitForSelector(shot.wait, { timeout: 20000 });
      if (shot.dark) {
        await page.evaluate(() => {
          document.documentElement.dataset.theme = "dark";
          document.documentElement.dataset.themePref = "dark";
        });
      }
      // 等列表里的异步数据（服务器 ping / 资源列表）落地
      await page.waitForTimeout(1200);
      const path = resolve(DOCS, shot.file);
      await page.screenshot({ path });
      const info = await stat(path);
      console.log(`  ${shot.file}  ${Math.round(info.size / 1024)} KB`);
    }

    await browser.close();
  } finally {
    server.kill("SIGTERM");
    await rm(WORK, { recursive: true, force: true });
  }
}

main().catch((error) => {
  const text = String(error && error.message ? error.message : error);
  if (/Executable doesn't exist|browserType\.launch/i.test(text)) {
    console.error("Chromium 没装好，先跑：cd gui && npx playwright install chromium");
  } else {
    console.error(error);
  }
  process.exit(1);
});
