// GUI 冒烟测试：在 jsdom 里真跑一遍 dist/renderer.js，断言页面能渲染出来。
// 不用浏览器、不连后端：fetch 被替换成固定数据。
// 跑法：npm test（会先 npm run build）

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const bundle = readFileSync(new URL("../dist/renderer.js", import.meta.url), "utf8");
const styles = readFileSync(new URL("../dist/styles.css", import.meta.url), "utf8");

const STATE = {
  version: "test",
  platform: "linux",
  account: null,
  default_client_id: "client-id",
  config: {
    game_dir: "/tmp/game", java_path: "", memory_mb: 4096, username: "Alex",
    isolate_versions: true, jobs: 8, download_source: "official", mirror_url: "",
    curseforge_configured: false, last_version: "1.20.1", config_path: "/tmp/config.json",
    theme: "light", ms_client_id: "", custom_skin: false, skin_model: "classic", skin_preview: "",
  },
  versions: [
    { id: "1.20.1", loader: "vanilla", java: 17, mods: 2, has_jar: true, type: "release" },
    { id: "fabric-1.20.1", loader: "fabric", java: 17, mods: 1, has_jar: true, type: "release" },
  ],
};

const SERVERS = {
  version: "1.20.1",
  path: "/tmp/game/versions/1.20.1/servers.dat",
  servers: [
    {
      index: 0, name: "Hypixel", ip: "mc.hypixel.net", host: "mc.hypixel.net", port: 25565,
      icon: "", accept_textures: true,
      status: {
        online: true, error: "", latency_ms: 12,
        players: { online: 3, max: 20 }, version: "1.20.1", motd: "欢迎来玩",
      },
    },
    {
      index: 1, name: "关掉的服", ip: "127.0.0.1:25599", host: "127.0.0.1", port: 25599,
      icon: "", accept_textures: true,
      status: {
        online: false, error: "timed out", latency_ms: null,
        players: { online: 0, max: 0 }, version: "", motd: "",
      },
    },
  ],
};

const VERSION_INFO = {
  id: "1.20.1", path: "/tmp/game/versions/1.20.1", size: 209715200, loader: "vanilla",
  java: 17, mods: 2, has_jar: true, type: "release", inherits: "",
  options: { memory_mb: 8192, width: null, height: null, jvm_args: "-XX:+UseG1GC", game_args: "" },
};

const LOCAL_MODS = {
  mods: [
    { name: "sodium.jar", enabled: true, size: 1048576, title: "Sodium", version: "0.5.11" },
    { name: "old.jar.disabled", enabled: false, size: 2048, title: "Old", version: "" },
  ],
};

const REMOTE = {
  latest: { release: "1.21.4", snapshot: "25w01a" },
  versions: [
    { id: "1.21.4", type: "release", release: "2024-12-03" },
    { id: "1.20.1", type: "release", release: "2023-06-12" },
  ],
};

const RESOURCES = { files: [{ name: "Complementary.zip", size: 2097152, dir: false }] };

const ABOUT = {
  version: "9.9.9", python: "3.12.4", platform: "Linux test (x86_64)",
  config_path: "/tmp/config.json", game_dir: "/tmp/game", exports_dir: "/tmp/game/exports",
  license: "GPL-3.0-or-later", repo: "https://github.com/EzraX21/mclauncher",
  releases: "https://github.com/EzraX21/mclauncher/releases",
};

const DOCTOR = {
  version: "9.9.9", problems: 1,
  checks: [
    { label: "Python", value: "3.12.4", status: "info" },
    { label: "Textual", value: "8.2.8", status: "ok" },
    { label: "游戏目录", value: "/tmp/game", status: "ok" },
    { label: "Java", value: "没找到", status: "warn" },
  ],
  java: [],
};

const JAVA = {
  runtimes: [
    { display: "Java 17 (17.0.9)", path: "/usr/lib/jvm/java-17/bin/java", major: 17, version: "17.0.9", configured: false },
    { display: "Java 21 (21.0.2)", path: "/usr/lib/jvm/java-21/bin/java", major: 21, version: "21.0.2", configured: true },
  ],
  configured: "/usr/lib/jvm/java-21/bin/java",
  components: [{ major: 17, component: "java-runtime-beta" }, { major: 21, component: "java-runtime-delta" }],
};

const WORLDS = {
  version: "1.20.1",
  worlds: [
    { name: "新世界", path: "/tmp/game/saves/新世界", has_level: true, datapacks: 1, modified: 1 },
    { name: "老存档", path: "/tmp/game/saves/老存档", has_level: true, datapacks: 0, modified: 2 },
  ],
};

const UPDATE = {
  current: "9.9.9", latest: "v9.9.10", update_available: true,
  page: "https://example/releases", published: "2026-11-17T10:00:00Z", prerelease: false,
  name: "v9.9.10",
  notes: "## What's Changed\n* feat: 联机页 by @EzraX21 in https://x/1\n\n**Full Changelog**: https://x/y",
  cached: false,
  assets: [{ name: "setup.exe", size: 1, url: "https://example/x" }],
};

const calls = [];
function fakeFetch(url) {
  calls.push(String(url));
  const target = String(url);
  const body = target.includes("/api/servers") ? SERVERS
    : target.includes("/api/version/info") ? VERSION_INFO
    : target.includes("/api/mods/local") ? LOCAL_MODS
    : target.includes("/api/update") ? UPDATE
    : target.includes("/api/java") ? JAVA
    : target.includes("/api/about") ? ABOUT
    : target.includes("/api/doctor") ? DOCTOR
    : target.includes("/api/worlds") ? WORLDS
    : target.includes("/api/remote") ? REMOTE
    : target.includes("/api/resources") ? RESOURCES
    : STATE;
  return Promise.resolve({
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  });
}

const dom = new JSDOM(
  `<!doctype html><html><head><style>${styles}</style></head><body><div id="app"></div><div id="toasts"></div></body></html>`,
  { url: "http://127.0.0.1:9/", runScripts: "outside-only", pretendToBeVisual: true },
);

const { window } = dom;
window.fetch = fakeFetch;
window.matchMedia = () => ({
  matches: false, media: "", addEventListener() {}, removeEventListener() {},
  addListener() {}, removeListener() {}, dispatchEvent: () => false,
});

const flush = () => new Promise((resolve) => window.setTimeout(resolve, 0));

window.eval(bundle);
await flush();

const doc = window.document;
const navLabels = [...doc.querySelectorAll("#nav .nav-item span")].map((node) => node.textContent);
assert.deepEqual(
  navLabels,
  ["启动", "版本管理", "下载", "联机", "百宝箱", "设置"],
  `导航项不对：${JSON.stringify(navLabels)}`,
);

// 默认落地页是启动页
assert.ok(doc.querySelector("#launch-main"), "启动页没有渲染出启动按钮");

// 启动页公告：最新版本 + 发布说明（Markdown 要拍平）
const news = doc.querySelector("#launch-news");
assert.ok(news, "启动页没有最新版本卡片");
assert.ok(!news.textContent.includes("加载中"), "公告卡片还停在加载中");
assert.ok(news.textContent.includes("v9.9.10"), `公告没显示版本：${news.textContent.slice(0, 80)}`);
assert.ok(news.querySelectorAll(".news-line").length >= 2, "发布说明没渲染成行");
assert.ok(news.textContent.includes("联机页"), "发布说明内容缺失");
assert.ok(!news.textContent.includes("Full Changelog"), "Full Changelog 应该被过滤");
assert.ok(!news.textContent.includes("##"), "Markdown 标题应该被清掉");
assert.ok(news.querySelector('a[href^="https://example/releases"]'), "公告没有「查看全部」链接");
assert.ok(news.textContent.includes("有新版本"), "有更新时应该显示徽章");

// 切到下载页：分类导航 + 版本清单
window.location.hash = "#/download";
window.dispatchEvent(new window.Event("hashchange"));
await flush();
await flush();

const dlTabs = [...doc.querySelectorAll("[data-dtab]")].map((node) => node.dataset.dtab);
assert.deepEqual(dlTabs, ["game", "mods", "pack", "datapack", "resourcepack", "shader"], `下载分类不对：${dlTabs}`);
assert.ok(doc.querySelector("#remote-list"), "下载页没渲染版本清单");
assert.ok(!doc.querySelector("#remote-list").textContent.includes("加载中"), "版本清单还停在加载中");
assert.ok(doc.querySelector("#remote-list").textContent.includes("1.21.4"), "版本清单没渲染版本");
assert.ok(doc.querySelector("#remote-hint").textContent.includes("最新正式版"), "没显示最新版本提示");

// 点一个版本 → 进入安装选项，带加载器标签
doc.querySelector("[data-version]").click();
await flush();
await flush();
assert.ok(doc.querySelector("#install-confirm"), "选中版本后没出现安装按钮");
const loaderTabs = [...doc.querySelectorAll(".loader-tab")].map((node) => node.textContent.trim());
assert.deepEqual(loaderTabs, ["原版", "Fabric", "Quilt", "Forge", "NeoForge"], `加载器标签不对：${loaderTabs}`);

// 数据包分类：要先选存档
[...doc.querySelectorAll("[data-dtab]")].find((node) => node.dataset.dtab === "datapack").click();
await flush();
await flush();
await flush();
const worldSelect = doc.querySelector("#dp-world");
assert.ok(worldSelect, "数据包分类没有存档选择");
assert.ok(!worldSelect.textContent.includes("加载存档中"), "存档列表还停在加载中");
assert.ok(worldSelect.textContent.includes("新世界"), `存档没渲染：${worldSelect.textContent}`);
assert.ok(worldSelect.textContent.includes("1 个数据包"), "存档没显示数据包数量");
assert.ok(doc.querySelector("#dp-query"), "数据包分类没有搜索框");
assert.ok(doc.querySelector("#dp-hint").textContent.includes("新世界"), "没显示当前存档");
assert.ok(
  calls.some((url) => url.includes("/api/resources") && url.includes("kind=datapack") && url.includes("world=")),
  "数据包分类没有按 world 查询本地列表",
);

// 光影分类
[...doc.querySelectorAll("[data-dtab]")].find((node) => node.dataset.dtab === "shader").click();
await flush();
await flush();
assert.ok(doc.querySelector("#res-local"), "光影分类没渲染已安装列表");
assert.ok(doc.querySelector("#res-local").textContent.includes("Complementary.zip"), "已安装光影没渲染出来");
assert.ok(doc.querySelector("#res-query"), "光影分类没有搜索框");

// 材质包分类切换后 kind 要跟着变
[...doc.querySelectorAll("[data-dtab]")].find((node) => node.dataset.dtab === "resourcepack").click();
await flush();
await flush();
assert.ok(
  calls.some((url) => url.includes("/api/resources") && url.includes("kind=resourcepack")),
  "切到材质包后没有按 resourcepack 查询",
);

// 模组分类
[...doc.querySelectorAll("[data-dtab]")].find((node) => node.dataset.dtab === "mods").click();
await flush();
assert.ok(doc.querySelector("#mods-query"), "模组分类没有搜索框");
assert.ok(doc.querySelector("#mods-version"), "模组分类没有版本选择");

// 设置：PCL 的四页结构，默认落在「启动」，Java 就在这一页
window.location.hash = "#/settings";
window.dispatchEvent(new window.Event("hashchange"));
await flush();
await flush();

const settingsTabs = [...doc.querySelectorAll(".settings-nav-item")].map((node) => node.dataset.tab);
assert.deepEqual(settingsTabs, ["launch", "ui", "system", "link"], `设置分页不对：${settingsTabs}`);
assert.ok(doc.querySelector('#settings-launch, [data-page="launch"]'), "没有「启动」分页容器");
assert.equal(doc.querySelectorAll('[data-page="launch"]').length, 4, "启动页应该容纳账号/常规/Java/下载四张卡");

const javaList = doc.querySelector("#java-runtimes");
assert.ok(javaList, "设置里没有 Java 列表");
assert.ok(!javaList.textContent.includes("检测中"), "Java 列表还停在检测中");
assert.ok(javaList.textContent.includes("Java 17"), `Java 列表没渲染：${javaList.textContent.slice(0, 80)}`);
assert.ok(javaList.textContent.includes("Java 21"), "Java 列表少了 Java 21");
assert.ok(javaList.textContent.includes("当前指定"), "没有标出当前指定的 Java");
assert.equal(javaList.querySelectorAll("[data-java-set]").length, 2, "设为默认按钮数量不对");
const disabledSet = [...javaList.querySelectorAll("[data-java-set]")].filter((b) => b.disabled);
assert.equal(disabledSet.length, 1, "当前指定的那个按钮应该是禁用的");
const installButtons = [...doc.querySelectorAll("[data-java-install]")].map((b) => b.dataset.javaInstall);
assert.deepEqual(installButtons, ["17", "21"], `下载按钮不对：${installButtons}`);
assert.ok(doc.querySelector("#java-auto"), "没有自动选择按钮");

// 「其他」页：配置路径 + 检查更新 + 诊断入口
[...doc.querySelectorAll(".settings-nav-item")].find((node) => node.dataset.tab === "system").click();
await flush();
const systemPage = doc.querySelector('[data-page="system"]');
assert.ok(systemPage.classList.contains("active"), "切到「其他」没生效");
assert.ok(systemPage.textContent.includes("config.json") || systemPage.textContent.includes("配置"),
          "「其他」页没显示配置路径");
doc.querySelector("#set-check-update").click();
await flush();
await flush();
assert.ok(doc.querySelector("#set-update-result").textContent.includes("v9.9.10"),
          "设置里的检查更新没显示结果");
assert.ok(doc.querySelector("#set-goto-toolbox"), "「其他」页没有诊断入口");

// 「联机」页：说明 + 跳转
[...doc.querySelectorAll(".settings-nav-item")].find((node) => node.dataset.tab === "link").click();
await flush();
assert.ok(doc.querySelector('[data-page="link"]').classList.contains("active"), "切到「联机」没生效");
assert.ok(doc.querySelector("#set-goto-link"), "联机设置页没有跳转按钮");

// 百宝箱
window.location.hash = "#/toolbox";
window.dispatchEvent(new window.Event("hashchange"));
await flush();
await flush();

const about = doc.querySelector("#tb-about");
assert.ok(about, "百宝箱没有关于卡片");
assert.ok(about.textContent.includes("v9.9.9"), `关于没显示版本：${about.textContent.slice(0, 80)}`);
assert.ok(about.textContent.includes("GPL-3.0-or-later"), "关于没显示许可证");
assert.ok(about.querySelector('a[href^="https://github.com/"]'), "关于没有项目链接");

const checks = doc.querySelector("#tb-checks");
assert.ok(checks, "百宝箱没有诊断列表");
assert.ok(!checks.textContent.includes("检测中"), "诊断还停在检测中");
assert.ok(checks.textContent.includes("1 个问题"), "诊断没显示问题数");
for (const label of ["Python", "Textual", "游戏目录", "Java"]) {
  assert.ok(checks.textContent.includes(label), `诊断缺少 ${label}`);
}
assert.equal(checks.querySelectorAll(".check-mark").length, 4, "诊断标记数量不对");
assert.ok(checks.querySelector(".check-mark.warn"), "警告状态没有对应样式");

// 检查更新：按钮是异步渲染出来的，点它要真的发请求并显示结果
const updateButton = doc.querySelector("#tb-update");
assert.ok(updateButton, "关于卡片没有检查更新按钮");
updateButton.click();
await flush();
await flush();
const updateResult = doc.querySelector("#tb-update-result");
assert.ok(updateResult.textContent.includes("v9.9.10"), `检查更新没显示新版本：${updateResult.textContent}`);
assert.ok(doc.querySelector('#tb-update-result a[href^="https://"]'), "检查更新没给下载链接");
assert.ok(
  calls.some((url) => url.includes("/api/update")),
  "点检查更新没有请求 /api/update",
);

const dirButtons = [...doc.querySelectorAll("[data-dir]")].map((node) => node.dataset.dir);
assert.deepEqual(dirButtons, ["config", "game", "logs", "exports"], `快捷目录按钮不对：${dirButtons}`);

// 切到联机页
window.location.hash = "#/link";
window.dispatchEvent(new window.Event("hashchange"));
await flush();
await flush();

const list = doc.querySelector("#link-list");
assert.ok(list, "联机页没有渲染服务器列表容器");
assert.ok(!list.textContent.includes("加载中"), "联机页还停在加载中");
assert.ok(list.textContent.includes("Hypixel"), `服务器行没渲染出来：${list.textContent}`);
assert.ok(list.textContent.includes("mc.hypixel.net"), "服务器地址没渲染出来");
assert.ok(list.textContent.includes("12 ms"), "延迟徽章没渲染出来");
assert.ok(list.textContent.includes("3/20 人"), "在线人数没渲染出来");
assert.ok(list.textContent.includes("欢迎来玩"), "MOTD 没渲染出来");
assert.ok(list.textContent.includes("关掉的服"), "离线服务器没渲染出来");
assert.ok(list.textContent.includes("离线"), "离线徽章没渲染出来");
assert.ok(doc.querySelector("#link-path").textContent.includes("servers.dat"), "servers.dat 路径没显示");

// 进服的按钮要按序号带上服务器下标
const joinButtons = [...doc.querySelectorAll("[data-join]")].map((node) => node.dataset.join);
assert.deepEqual(joinButtons, ["0", "1"], "进服按钮缺 data-join 序号");

assert.ok(
  calls.some((url) => url.includes("/api/servers") && url.includes("ping=1")),
  "联机页没有请求服务器状态",
);

// 切到版本管理页
window.location.hash = "#/instance";
window.dispatchEvent(new window.Event("hashchange"));
await flush();
await flush();

const detail = doc.querySelector("#instance-detail");
assert.ok(detail, "版本管理页没有详情容器");
assert.ok(!detail.textContent.includes("加载中"), "版本管理页还停在加载中");
assert.ok(detail.textContent.includes("1.20.1"), `概览没显示版本名：${detail.textContent.slice(0, 120)}`);
assert.ok(detail.textContent.includes("/tmp/game/versions/1.20.1"), "概览没显示版本路径");
assert.ok(detail.textContent.includes("Java 17"), "概览没显示 Java");
assert.ok(detail.textContent.includes("200.0 MB"), "概览没显示占用大小");
for (const buttonId of ["inst-launch", "inst-rename", "inst-copy", "inst-open", "inst-export", "inst-delete", "inst-loader", "inst-crash"]) {
  assert.ok(doc.querySelector(`#${buttonId}`), `概览缺少操作按钮 #${buttonId}`);
}
assert.equal(doc.querySelectorAll("[data-pick]").length, 2, "版本列表条数不对");

// 切到「设置」标签，应带出单版本设置
[...doc.querySelectorAll("[data-itab]")].find((node) => node.dataset.itab === "setup").click();
await flush();
await flush();
const memory = doc.querySelector("#inst-memory");
assert.ok(memory, "设置标签没渲染内存输入框");
assert.equal(memory.value, "8192", `内存没带出单版本设置：${memory.value}`);
assert.equal(doc.querySelector("#inst-jvm").value, "-XX:+UseG1GC", "JVM 参数没带出来");

// PCL 的版本管理是六个标签
const itabs = [...doc.querySelectorAll("[data-itab]")].map((node) => node.dataset.itab);
assert.deepEqual(itabs, ["overview", "setup", "modify", "mods", "mods-off", "export"],
                 `版本管理标签不对：${itabs}`);

// 「禁用模组」只看禁用的
[...doc.querySelectorAll("[data-itab]")].find((node) => node.dataset.itab === "mods-off").click();
await flush();
await flush();
const offText = doc.querySelector("#instance-detail").textContent;
assert.ok(offText.includes("已禁用的模组"), `禁用模组页标题不对：${offText.slice(0, 60)}`);
assert.ok(offText.includes("Old"), "禁用模组页没列出禁用的模组");
assert.ok(!offText.includes("Sodium"), "禁用模组页不该出现启用的模组");

// 「修改」页：改名 / 复制 / 打开 / 删除
[...doc.querySelectorAll("[data-itab]")].find((node) => node.dataset.itab === "modify").click();
await flush();
assert.ok(doc.querySelector("#mod-rename"), "修改页没有重命名");
assert.ok(doc.querySelector("#mod-copy"), "修改页没有复制");
assert.ok(doc.querySelector("#mod-open"), "修改页没有打开文件夹");
assert.ok(doc.querySelector("#mod-delete"), "修改页没有删除");
assert.ok(doc.querySelector("#mod-new-name").value === "1.20.1", "修改页没带出当前版本名");

// 「导出」页
[...doc.querySelectorAll("[data-itab]")].find((node) => node.dataset.itab === "export").click();
await flush();
assert.ok(doc.querySelector("#exp-go"), "导出页没有导出按钮");
assert.ok(doc.querySelector("#exp-saves"), "导出页没有连存档开关");

// 切到「模组」标签
[...doc.querySelectorAll("[data-itab]")].find((node) => node.dataset.itab === "mods").click();
await flush();
await flush();
const modText = doc.querySelector("#instance-detail").textContent;
assert.ok(modText.includes("Sodium"), `模组标签没渲染模组：${modText.slice(0, 120)}`);
assert.ok(modText.includes("禁用") && modText.includes("启用"), "模组启用状态没渲染");

assert.ok(
  calls.some((url) => url.includes("/api/version/info")),
  "版本管理页没有请求版本详情",
);
assert.ok(
  calls.some((url) => url.includes("/api/mods/local")),
  "模组标签没有请求本地模组",
);

// 断言跑完就收工：jsdom 关掉窗口后进程还会挂十几秒（内部定时器），显式退出。
// 断言失败会抛异常，走不到这里，所以退出码依然能反映成败。
window.close();
console.log("gui smoke ok:", navLabels.join(" / "), "| 服务器行 2 条 | 版本 2 条 | 调用", calls.length, "次");
process.exit(0);
