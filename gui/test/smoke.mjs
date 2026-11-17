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

const calls = [];
function fakeFetch(url) {
  calls.push(String(url));
  const target = String(url);
  const body = target.includes("/api/servers") ? SERVERS
    : target.includes("/api/version/info") ? VERSION_INFO
    : target.includes("/api/mods/local") ? LOCAL_MODS
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
  ["启动", "版本管理", "安装", "资源", "模组", "联机", "设置"],
  `导航项不对：${JSON.stringify(navLabels)}`,
);

// 默认落地页是启动页
assert.ok(doc.querySelector("#launch-main"), "启动页没有渲染出启动按钮");

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

console.log("gui smoke ok:", navLabels.join(" / "), "| 服务器行 2 条 | 版本 2 条 | 调用", calls.length, "次");
