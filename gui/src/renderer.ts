type View = "versions" | "install" | "resources" | "mods" | "settings";
const MICROSOFT_LOGIN_ENABLED = false;

interface VersionInfo {
  id: string; loader: string; java: number | null; mods: number; has_jar: boolean; type: string;
}
interface ConfigInfo {
  game_dir: string; java_path: string; memory_mb: number; username: string;
  isolate_versions: boolean; jobs: number; download_source: string; mirror_url: string;
  curseforge_configured: boolean; last_version: string; config_path: string; theme: string;
  ms_client_id: string; custom_skin: boolean; skin_model: string; skin_preview: string;
}
interface AccountInfo { name: string; uuid: string; }
interface StateInfo { version: string; config: ConfigInfo; versions: VersionInfo[]; platform: string;
  account: AccountInfo | null; default_client_id: string; }
interface RemoteVersion { id: string; type: string; release: string; }
interface RemoteInfo { latest: { release: string; snapshot: string }; versions: RemoteVersion[]; }
interface ModHit { slug: string; title: string; description: string; downloads: number; author: string; }
interface LocalMod { name: string; enabled: boolean; size: number; title: string; version: string; }
interface TaskInfo {
  id: string; kind: string; state: string; error: string | null; result: unknown;
  progress: { phase?: string; done_files?: number; total_files?: number; done_bytes?: number; total_bytes?: number };
  log: string[];
}

let state: StateInfo;
let view: View = "versions";
let remote: RemoteVersion[] = [];
let remoteLoaded = false;
let modsVersion = "";
let modsTimer: number | null = null;
let resourceKind = "shader";
let resourceVersion = "";
let settingsTab = "account";
let modsTab = "pack";
let installTab = "vanilla";
let installLoader = "";

const app = document.getElementById("app") as HTMLDivElement;
const toasts = (): HTMLElement => document.getElementById("toasts") as HTMLElement;

type ThemePref = "light" | "dark" | "system";
const darkMedia = window.matchMedia("(prefers-color-scheme: dark)");

function storedTheme(): string {
  try {
    return localStorage.getItem("mcl-theme") || "light";
  } catch {
    return "light";
  }
}

function applyTheme(pref: string): void {
  const value: ThemePref = pref === "dark" || pref === "system" ? pref : "light";
  const resolved = value === "system" ? (darkMedia.matches ? "dark" : "light") : value;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePref = value;
  try {
    localStorage.setItem("mcl-theme", value);
  } catch {
    // WebKit 隐私模式 / 禁用存储时忽略
  }
}

darkMedia.addEventListener("change", () => {
  if (document.documentElement.dataset.themePref === "system") applyTheme("system");
});

// Lucide icons (ISC), path data from PCL CE's icon pack.
const lucide = (body: string): string =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
const icons: Record<View, string> = {
  versions: lucide('<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>'),
  install: lucide('<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>'),
  resources: lucide('<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'),
  mods: lucide('<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><polyline points="3.29 7 12 12 20.71 7"/><path d="m7.5 4.27 9 5.15"/>'),
  settings: lucide('<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915"/><circle cx="12" cy="12" r="3"/>'),
};

function shell(): string {
  return `
  <div class="app">
    <header class="titlebar">
      <div class="brand">
        <div class="brand-mark">M</div>
        <div class="brand-text">
          <div class="brand-name">MCL</div>
          <div class="brand-version" id="brand-version">v—</div>
        </div>
      </div>
      <nav class="nav" id="nav">
        ${(["versions", "install", "resources", "mods", "settings"] as View[]).map((name) => `
          <button class="nav-item" data-view="${name}">
            ${icons[name]}<span>${labelOf(name)}</span>
          </button>`).join("")}
      </nav>
      <div class="titlebar-tools">
        <div class="inline" id="top-actions"></div>
        <span class="path-chip" id="side-foot"></span>
      </div>
    </header>
    <main class="main">
      <header class="pagebar" style="display:none">
        <div>
          <h1 id="page-title">启动</h1>
          <div class="sub" id="page-sub"></div>
        </div>
      </header>
      <section class="content" id="content"></section>
    </main>
    <div class="task-panel" id="task-panel">
      <div class="task-head">
        <strong id="task-title">任务</strong>
        <span class="small muted" id="task-state">运行中</span>
      </div>
      <div class="progress"><div id="task-bar"></div></div>
      <div class="task-meta"><span id="task-files"></span><span id="task-bytes"></span></div>
      <div class="task-log" id="task-log"></div>
    </div>
    <div class="toasts" id="toasts"></div>
  </div>`;
}
function labelOf(value: View): string {
  return { versions: "启动", install: "安装", resources: "资源", mods: "模组", settings: "设置" }[value];
}

function esc(text: unknown): string {
  return String(text).replace(/[&<>"']/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char] as string
  ));
}

function size(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((data as { error?: string }).error || response.statusText);
  return data as T;
}

function toast(message: string, kind: "ok" | "error" | "" = ""): void {
  const node = document.createElement("div");
  node.className = `toast ${kind}`;
  node.textContent = message;
  toasts().appendChild(node);
  window.setTimeout(() => node.remove(), 4500);
}

function setHeader(title: string, sub: string): void {
  (document.getElementById("page-title") as HTMLElement).textContent = title;
  (document.getElementById("page-sub") as HTMLElement).textContent = sub;
}

function typeLabel(type: string): string {
  return ({ release: "正式版", snapshot: "快照", old_beta: "远古 Beta", old_alpha: "远古 Alpha" } as Record<string, string>)[type] || type;
}

function badge(loader: string): string {
  const label = { vanilla: "原版", fabric: "Fabric", quilt: "Quilt", forge: "Forge", neoforge: "NeoForge" }[loader] || loader;
  const cls = loader === "vanilla" ? "" : "blue";
  return `<span class="badge ${cls}">${esc(label)}</span>`;
}

async function refreshState(): Promise<void> {
  state = await api<StateInfo>("/api/state");
  applyTheme(state.config.theme || "light");
  (document.getElementById("brand-version") as HTMLElement).textContent = `v${state.version}`;
  (document.getElementById("side-foot") as HTMLElement).textContent = state.config.game_dir;
  if (!modsVersion || !state.versions.some((item) => item.id === modsVersion)) {
    modsVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  render();
}

function render(): void {
  document.querySelectorAll<HTMLButtonElement>("#nav .nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  const content = document.getElementById("content") as HTMLElement;
  content.classList.toggle("content-flush", view === "versions");
  const actions = document.getElementById("top-actions") as HTMLElement;
  actions.innerHTML = "";
  if (view === "versions") {
    renderVersions();
  } else if (view === "install") {
    renderInstall();
  } else if (view === "resources") {
    renderResources();
  } else if (view === "mods") {
    renderMods();
  } else {
    renderSettings();
  }
}

// ---------------------------------------------------------------- 版本
function renderVersions(): void {
  setHeader("启动", `${state.versions.length} 个已安装版本`);
  const content = document.getElementById("content") as HTMLElement;
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}">${esc(version.id)} · ${esc(version.loader)}</option>`).join("");
  const selected = state.versions.some((item) => item.id === state.config.last_version)
    ? state.config.last_version
    : (state.versions[0]?.id || "");
  content.innerHTML = `
    <div class="launch-layout">
      <aside class="launch-side">
        <div class="account-line"><span class="online-dot"></span>离线模式</div>
        <div class="account-avatar">${state.config.skin_preview
          ? `<div class="skin-head" style="--skin:url('${state.config.skin_preview}')"></div>`
          : esc((state.config.username || "P").slice(0, 1).toUpperCase())}</div>
        <div class="account-name">${esc(state.config.username || "Player")}</div>
        <div class="launch-field">
          <label>游戏版本</label>
          <select id="launch-select">${options || '<option value="">没有已安装版本</option>'}</select>
        </div>
        <button class="btn primary launch-big" id="launch-main" ${state.versions.length ? "" : "disabled"}>启动游戏</button>
        <button class="btn launch-sub" id="go-install">下载游戏 / 安装新版本</button>
        <div class="launch-note">${state.versions.length ? "启动前会自动检查 Java 和依赖库。" : "还没有安装任何版本。"}</div>
      </aside>
      <section class="launch-main">
        ${state.versions.length ? `
        <div class="card">
          <div class="card-head">
            <span class="card-title">已安装版本</span>
            <button class="btn sm" id="refresh">刷新</button>
          </div>
          <div class="list">
            ${state.versions.map((version) => `
              <div class="list-row">
                <div class="grow">
                  <div class="title">${esc(version.id)} ${badge(version.loader)}
                    ${version.has_jar ? "" : '<span class="badge red">缺客户端</span>'}</div>
                  <div class="desc">Java ${version.java ?? "?"} · ${version.mods} 个模组</div>
                </div>
                <button class="btn sm" data-settings="${esc(version.id)}">设置</button>
                <button class="btn sm" data-crash="${esc(version.id)}">崩溃分析</button>
                <button class="btn sm" data-loader="${esc(version.id)}">装加载器</button>
                <button class="btn sm danger" data-delete="${esc(version.id)}">删除</button>
              </div>`).join("")}
          </div>
        </div>` : `
        <div class="card"><div class="empty">
          还没有安装任何版本。<br><br>
          <button class="btn primary" id="go-install-empty">去安装一个</button>
        </div></div>`}
      </section>
    </div>`;
  const select = content.querySelector("#launch-select") as HTMLSelectElement | null;
  if (select) select.value = selected;
  const launchSelected = () => {
    const id = select?.value || selected;
    if (!id) return;
    const button = content.querySelector("#launch-main") as HTMLButtonElement | null;
    if (button) void launch(id, button);
  };
  content.querySelector("#launch-main")?.addEventListener("click", launchSelected);
  content.querySelector("#go-install")?.addEventListener("click", () => setView("install"));
  content.querySelector("#go-install-empty")?.addEventListener("click", () => setView("install"));
  content.querySelector("#refresh")?.addEventListener("click", () => refreshState());
  content.querySelectorAll<HTMLButtonElement>("[data-loader]").forEach((button) => {
    button.addEventListener("click", () => openLoader(button.dataset.loader as string));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-settings]").forEach((button) => {
    button.addEventListener("click", () => void openVersionSettings(button.dataset.settings as string));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-crash]").forEach((button) => {
    button.addEventListener("click", () => openCrash(button.dataset.crash as string));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-delete]").forEach((button) => {
    button.addEventListener("click", () => openDelete(button.dataset.delete as string));
  });
}
function openDelete(id: string): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  const detail = state.config.isolate_versions
    ? "该版本目录里的存档、模组和配置会一起删除。"
    : "只删除版本文件，公共存档和模组不会动。";
  overlay.innerHTML = `<div class="modal">
    <h3>删除 ${esc(id)}</h3>
    <div class="small muted" style="margin-bottom:16px">${detail}</div>
    <div class="actions">
      <button class="btn" id="delete-cancel">取消</button>
      <button class="btn danger" id="delete-confirm">删除</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#delete-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  overlay.querySelector("#delete-confirm")?.addEventListener("click", async () => {
    const button = overlay.querySelector("#delete-confirm") as HTMLButtonElement;
    button.disabled = true;
    try {
      await api("/api/versions/remove", { method: "POST", body: JSON.stringify({ id }) });
      close();
      toast(`已删除 ${id}`, "ok");
      await refreshState();
    } catch (error) {
      button.disabled = false;
      toast(`删除失败：${(error as Error).message}`, "error");
    }
  });
}

async function openVersionSettings(id: string): Promise<void> {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal" style="width:520px">
    <h3>版本设置 · ${esc(id)}</h3>
    <div class="small muted" style="margin-bottom:12px">留空表示跟随全局设置。</div>
    <div class="field"><label>内存（MB）</label><input id="vs-memory" type="number" min="512" max="65536" /></div>
    <div class="inline" style="align-items:flex-start">
      <div class="field" style="flex:1"><label>窗口宽度</label><input id="vs-width" type="number" min="320" max="10000" /></div>
      <div class="field" style="flex:1"><label>窗口高度</label><input id="vs-height" type="number" min="240" max="10000" /></div>
    </div>
    <div class="field"><label>额外 JVM 参数</label><textarea id="vs-jvm" rows="2" placeholder="-XX:+UseG1GC"></textarea></div>
    <div class="field"><label>额外游戏参数</label><textarea id="vs-game" rows="2" placeholder="--fullscreen"></textarea></div>
    <div class="actions">
      <button class="btn" id="vs-cancel">取消</button>
      <button class="btn primary" id="vs-save">保存</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#vs-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  try {
    const data = await api<{ options: { memory_mb: number | null; width: number | null; height: number | null; jvm_args: string; game_args: string } }>(
      `/api/version/options?id=${encodeURIComponent(id)}`);
    const opts = data.options;
    (overlay.querySelector("#vs-memory") as HTMLInputElement).value = opts.memory_mb?.toString() || "";
    (overlay.querySelector("#vs-width") as HTMLInputElement).value = opts.width?.toString() || "";
    (overlay.querySelector("#vs-height") as HTMLInputElement).value = opts.height?.toString() || "";
    (overlay.querySelector("#vs-jvm") as HTMLTextAreaElement).value = opts.jvm_args || "";
    (overlay.querySelector("#vs-game") as HTMLTextAreaElement).value = opts.game_args || "";
  } catch (error) {
    toast((error as Error).message, "error");
  }
  overlay.querySelector("#vs-save")?.addEventListener("click", async () => {
    const value = (selector: string) => (overlay.querySelector(selector) as HTMLInputElement).value.trim();
    try {
      await api("/api/version/options", {
        method: "POST",
        body: JSON.stringify({
          id,
          memory_mb: value("#vs-memory") || null,
          width: value("#vs-width") || null,
          height: value("#vs-height") || null,
          jvm_args: value("#vs-jvm"),
          game_args: value("#vs-game"),
        }),
      });
      close();
      toast(`已保存 ${id} 的版本设置`, "ok");
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

async function launch(id: string, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  button.textContent = "启动中…";
  try {
    const result = await api<{ pid: number }>("/api/launch", { method: "POST", body: JSON.stringify({ id }) });
    toast(`已启动 ${id}（PID ${result.pid}）`, "ok");
  } catch (error) {
    toast(`启动失败：${(error as Error).message}`, "error");
  } finally {
    button.disabled = false;
    button.textContent = "启动";
  }
}

async function openCrash(id: string): Promise<void> {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal" style="width:720px"><h3>崩溃分析 · ${esc(id)}</h3>
    <div class="small muted">正在读取日志…</div><div class="actions"><button class="btn" id="crash-close">关闭</button></div></div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#crash-close")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  try {
    const data = await api<{ path: string; findings: { title: string; detail: string; fix: string }[];
      tail: string; message: string }>(`/api/crash?version=${encodeURIComponent(id)}`);
    const findings = data.findings || [];
    overlay.innerHTML = `<div class="modal" style="width:720px">
      <h3>崩溃分析 · ${esc(id)}</h3>
      <div class="small muted" style="margin-bottom:12px">${esc(data.path || "没有找到日志")}</div>
      ${findings.length ? findings.map((finding) => `
        <div class="finding">
          <div class="title">${esc(finding.title)}</div>
          <div class="desc">${esc(finding.detail)}</div>
          <div class="small" style="margin-top:4px">→ ${esc(finding.fix)}</div>
        </div>`).join("") : `<div class="empty">${esc(data.message || "没有识别出常见原因")}</div>`}
      ${data.tail ? `<details><summary class="small muted">日志末尾</summary><pre class="log-tail">${esc(data.tail)}</pre></details>` : ""}
      <div class="actions"><button class="btn" id="crash-close">关闭</button></div>
    </div>`;
    overlay.querySelector("#crash-close")?.addEventListener("click", close);
  } catch (error) {
    overlay.querySelector(".modal")!.innerHTML = `<h3>崩溃分析</h3><div class="empty">${esc((error as Error).message)}</div>
      <div class="actions"><button class="btn" id="crash-close">关闭</button></div>`;
    overlay.querySelector("#crash-close")?.addEventListener("click", close);
  }
}

function openLoader(id: string): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `
    <div class="modal">
      <h3>给 ${esc(id)} 装加载器</h3>
      <div class="field">
        <label>选择加载器</label>
        <select id="loader-select">
          <option value="fabric">Fabric</option>
          <option value="quilt">Quilt</option>
          <option value="forge">Forge</option>
          <option value="neoforge">NeoForge</option>
        </select>
      </div>
      <div class="small muted">Forge / NeoForge 会跑官方安装器，可能需要几分钟。</div>
      <div class="actions">
        <button class="btn" id="loader-cancel">取消</button>
        <button class="btn primary" id="loader-start">开始</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#loader-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  overlay.querySelector("#loader-start")?.addEventListener("click", async () => {
    const loader = (overlay.querySelector("#loader-select") as HTMLSelectElement).value;
    close();
    try {
      const task = await api<TaskInfo>("/api/loader", { method: "POST", body: JSON.stringify({ id, loader }) });
      watchTask(task, "装加载器");
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

// ---------------------------------------------------------------- 安装
async function renderInstall(): Promise<void> {
  setHeader("安装原版", "从 Mojang 官方源下载，镜像可选");
  const content = document.getElementById("content") as HTMLElement;
  content.innerHTML = `
    <div class="page-layout">
      <aside class="page-nav">
        <button class="page-nav-item ${installTab === "vanilla" ? "active" : ""}" data-tab="vanilla">原版游戏</button>
        <button class="page-nav-item ${installTab === "installed" ? "active" : ""}" data-tab="installed">已安装版本</button>
        <button class="page-nav-item ${installTab === "modpack" ? "active" : ""}" data-tab="modpack">整合包</button>
      </aside>
      <div class="page-main">
    <div class="install-page ${installTab === "vanilla" ? "active" : ""}" data-page="vanilla">
    <div class="loader-tabs">
      ${[["", "原版"], ["fabric", "Fabric"], ["quilt", "Quilt"], ["forge", "Forge"], ["neoforge", "NeoForge"]].map(([value, label]) => `
        <button class="loader-tab ${installLoader === value ? "active" : ""}" data-loader="${value}">${label}</button>`).join("")}
    </div>
    <div class="card">
      <div class="card-head">
        <span class="card-title">版本清单</span>
        <div class="inline">
          <input class="search" id="remote-filter" placeholder="搜索版本，例如 1.20.1" />
          <button class="btn" id="remote-refresh">刷新</button>
        </div>
      </div>
      <div class="card-body row-between">
        <label class="checkbox"><input type="checkbox" id="with-assets" checked /> 下载资源文件（音效、语言）</label>
        <span class="small muted" id="remote-hint">加载中…</span>
      </div>
      <div class="list" id="remote-list"></div>
    </div>
    </div>
    <div class="install-page ${installTab === "installed" ? "active" : ""}" data-page="installed">
      <div class="card">
        <div class="card-head"><span class="card-title">已安装版本</span></div>
        ${state.versions.length ? `<div class="list">${state.versions.map((version) => `
          <div class="list-row">
            <div class="grow">
              <div class="title">${esc(version.id)} ${badge(version.loader)}
                ${version.has_jar ? "" : '<span class="badge red">缺客户端</span>'}</div>
              <div class="desc">Java ${version.java ?? "?"} · ${version.mods} 个模组</div>
            </div>
            <button class="btn sm" data-installed-settings="${esc(version.id)}">设置</button>
            <button class="btn sm" data-installed-loader="${esc(version.id)}">装加载器</button>
            <button class="btn sm danger" data-installed-delete="${esc(version.id)}">删除</button>
            <button class="btn primary sm" data-installed-launch="${esc(version.id)}">启动</button>
          </div>`).join("")}</div>` : `<div class="empty">还没有安装任何版本</div>`}
      </div>
    </div>
    <div class="install-page ${installTab === "modpack" ? "active" : ""}" data-page="modpack">
      <div class="card">
        <div class="card-head"><span class="card-title">导入整合包</span></div>
        <div class="card-body">
          <div class="inline">
            <input type="file" id="install-pack-file" accept=".mrpack,.zip" />
            <input id="install-pack-name" placeholder="实例名（可选）" style="width:200px" />
            <button class="btn primary" id="install-pack-import">导入</button>
          </div>
          <div class="small muted" style="margin-top:8px">支持 Modrinth .mrpack；CurseForge 需要先配 API key</div>
        </div>
      </div>
    </div>
      </div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>(".page-nav-item[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      installTab = button.dataset.tab as string;
      content.querySelectorAll(".page-nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      content.querySelectorAll<HTMLElement>(".install-page").forEach((page) => {
        page.classList.toggle("active", page.dataset.page === installTab);
      });
    });
  });
  content.querySelectorAll<HTMLButtonElement>(".loader-tab").forEach((button) => {
    button.addEventListener("click", () => {
      installLoader = button.dataset.loader as string;
      content.querySelectorAll(".loader-tab").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      toast(installLoader ? `安装时使用 ${installLoader}` : "安装原版", "ok");
    });
  });
  content.querySelectorAll<HTMLButtonElement>("[data-installed-launch]").forEach((button) => {
    button.addEventListener("click", () => launch(button.dataset.installedLaunch as string, button));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-installed-settings]").forEach((button) => {
    button.addEventListener("click", () => void openVersionSettings(button.dataset.installedSettings as string));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-installed-loader]").forEach((button) => {
    button.addEventListener("click", () => openLoader(button.dataset.installedLoader as string));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-installed-delete]").forEach((button) => {
    button.addEventListener("click", () => openDelete(button.dataset.installedDelete as string));
  });
  content.querySelector("#install-pack-import")?.addEventListener("click", async () => {
    const fileInput = content.querySelector("#install-pack-file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) { toast("先选一个 .mrpack / .zip", "error"); return; }
    const name = (content.querySelector("#install-pack-name") as HTMLInputElement).value.trim();
    try {
      const response = await fetch("/api/modpack/install", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
          "X-Pack-Name": encodeURIComponent(name),
        },
        body: await file.arrayBuffer(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      watchTask(data as TaskInfo, `导入 ${file.name}`);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  const input = content.querySelector("#remote-filter") as HTMLInputElement;
  input.addEventListener("input", () => paintRemote());
  content.querySelector("#remote-refresh")?.addEventListener("click", () => loadRemote(true));
  if (!remoteLoaded) await loadRemote(false); else paintRemote();
}

async function loadRemote(force: boolean): Promise<void> {
  const hint = document.getElementById("remote-hint");
  if (hint) hint.textContent = "加载中…";
  try {
    const data = await api<RemoteInfo>("/api/remote");
    remote = data.versions;
    remoteLoaded = true;
    const latest = document.getElementById("remote-hint");
    if (latest) latest.textContent = `最新正式版 ${data.latest.release} · 最新快照 ${data.latest.snapshot} · ${remote.length} 个版本`;
    paintRemote();
  } catch (error) {
    if (hint) hint.textContent = "加载失败";
    toast((error as Error).message, "error");
  }
}

function paintRemote(): void {
  const list = document.getElementById("remote-list");
  if (!list) return;
  const needle = (document.getElementById("remote-filter") as HTMLInputElement)?.value.trim().toLowerCase() || "";
  const items = remote.filter((item) => !needle || item.id.toLowerCase().includes(needle)).slice(0, 150);
  if (!items.length) {
    list.innerHTML = `<div class="empty">没有匹配的版本</div>`;
    return;
  }
  list.innerHTML = items.map((item) => `
    <div class="list-row">
      <div class="grow">
        <div class="title">${esc(item.id)} <span class="badge">${esc(typeLabel(item.type))}</span></div>
        <div class="desc">${esc(item.release)}</div>
      </div>
      <button class="btn primary sm" data-install="${esc(item.id)}">安装</button>
    </div>`).join("");
  list.querySelectorAll<HTMLButtonElement>("[data-install]").forEach((button) => {
    button.addEventListener("click", async () => {
      const assets = (document.getElementById("with-assets") as HTMLInputElement).checked;
      try {
        const task = await api<TaskInfo>("/api/install", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.install, assets, loader: installLoader }),
        });
        watchTask(task, `安装 ${button.dataset.install}`);
      } catch (error) {
        toast((error as Error).message, "error");
      }
    });
  });
}

// ---------------------------------------------------------------- 资源
function renderResources(): void {
  setHeader("资源", "光影 / 材质包，来自 Modrinth");
  const content = document.getElementById("content") as HTMLElement;
  if (!resourceVersion || !state.versions.some((item) => item.id === resourceVersion)) {
    resourceVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === resourceVersion ? "selected" : ""}>${esc(version.id)}</option>`).join("");
  content.innerHTML = `
    <div class="page-layout">
      <aside class="page-nav">
        <button class="page-nav-item ${resourceKind === "shader" ? "active" : ""}" data-kind="shader">光影</button>
        <button class="page-nav-item ${resourceKind === "resourcepack" ? "active" : ""}" data-kind="resourcepack">材质包</button>
      </aside>
      <div class="page-main">
    <div class="card" id="res-local-card">
      <div class="card-head">
        <span class="card-title">已安装</span>
        <div class="inline">
          <select id="res-kind">
            <option value="shader" ${resourceKind === "shader" ? "selected" : ""}>光影</option>
            <option value="resourcepack" ${resourceKind === "resourcepack" ? "selected" : ""}>材质包</option>
          </select>
          <select id="res-version">${options || '<option value="">没有已装版本</option>'}</select>
          <button class="btn" id="res-refresh">刷新</button>
        </div>
      </div>
      <div class="list" id="res-local"><div class="empty">加载中…</div></div>
    </div>
    <div class="card" id="res-search-card">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth</span>
        <div class="inline">
          <input class="search" id="res-query" placeholder="例如 Complementary" />
          <button class="btn primary" id="res-search">搜索</button>
        </div>
      </div>
      <div class="list" id="res-results"><div class="empty">输入关键词搜索</div></div>
    </div>
      </div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>(".page-nav .page-nav-item[data-kind]").forEach((button) => {
    button.addEventListener("click", () => {
      resourceKind = button.dataset.kind as string;
      (content.querySelector("#res-kind") as HTMLSelectElement).value = resourceKind;
      renderResources();
    });
  });
  (content.querySelector("#res-kind") as HTMLSelectElement).addEventListener("change", (event) => {
    resourceKind = (event.target as HTMLSelectElement).value;
    renderResources();
  });
  (content.querySelector("#res-version") as HTMLSelectElement).addEventListener("change", (event) => {
    resourceVersion = (event.target as HTMLSelectElement).value;
    void loadResourceLocal();
  });
  content.querySelector("#res-refresh")?.addEventListener("click", () => void loadResourceLocal());
  content.querySelector("#res-search")?.addEventListener("click", () => void searchResources());
  (content.querySelector("#res-query") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void searchResources();
  });
  void loadResourceLocal();
}

async function loadResourceLocal(): Promise<void> {
  const list = document.getElementById("res-local");
  if (!list || !resourceVersion) return;
  try {
    const data = await api<{ files: { name: string; size: number; dir: boolean }[] }>(
      `/api/resources?kind=${resourceKind}&version=${encodeURIComponent(resourceVersion)}`);
    if (!data.files.length) {
      list.innerHTML = `<div class="empty">还没有安装</div>`;
      return;
    }
    list.innerHTML = data.files.map((item) => `
      <div class="list-row">
        <div class="grow"><div class="title">${esc(item.name)}</div>
          <div class="desc">${item.size ? `${(item.size / 1048576).toFixed(1)} MB` : "文件夹"}</div></div>
        <button class="btn sm danger" data-res-del="${esc(item.name)}">删除</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-res-del]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/resources/delete", { method: "POST", body: JSON.stringify({
          kind: resourceKind, version: resourceVersion, name: button.dataset.resDel,
        }) });
        toast("已删除", "ok");
        void loadResourceLocal();
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

async function searchResources(): Promise<void> {
  const input = document.getElementById("res-query") as HTMLInputElement;
  const query = input.value.trim();
  const list = document.getElementById("res-results");
  if (!query || !resourceVersion || !list) return;
  list.innerHTML = `<div class="empty">搜索中…</div>`;
  try {
    const data = await api<{ hits: { slug: string; title: string; description: string; downloads: number }[] }>(
      `/api/resources?kind=${resourceKind}&version=${encodeURIComponent(resourceVersion)}&q=${encodeURIComponent(query)}`);
    if (!data.hits.length) {
      list.innerHTML = `<div class="empty">没有搜到结果</div>`;
      return;
    }
    list.innerHTML = data.hits.map((hit) => `
      <div class="list-row">
        <div class="grow"><div class="title">${esc(hit.title)}</div>
          <div class="desc">${esc(hit.description)}</div></div>
        <span class="small muted">${hit.downloads.toLocaleString()} 次</span>
        <button class="btn primary sm" data-res-install="${esc(hit.slug)}">安装</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-res-install]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const task = await api<TaskInfo>("/api/resources/install", {
            method: "POST", body: JSON.stringify({
              kind: resourceKind, version: resourceVersion, slug: button.dataset.resInstall,
            }),
          });
          watchTask(task, "安装资源");
        } catch (error) {
          toast((error as Error).message, "error");
        }
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

// ---------------------------------------------------------------- 模组
function renderMods(): void {
  setHeader("模组", "Modrinth 搜索与本地管理");
  const content = document.getElementById("content") as HTMLElement;
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === modsVersion ? "selected" : ""}>${esc(version.id)} (${esc(version.loader)})</option>`).join("");
  content.innerHTML = `
    <div class="page-layout">
      <aside class="page-nav">
        <button class="page-nav-item ${modsTab === "pack" ? "active" : ""}" data-tab="pack">整合包</button>
        <button class="page-nav-item ${modsTab === "local" ? "active" : ""}" data-tab="local">本地模组</button>
        <button class="page-nav-item ${modsTab === "search" ? "active" : ""}" data-tab="search">搜索模组</button>
      </aside>
      <div class="page-main">
    <div class="card mods-page ${modsTab === "pack" ? "active" : ""}" data-page="pack" id="mods-pack">
      <div class="card-head"><span class="card-title">导入整合包</span></div>
      <div class="card-body">
        <div class="inline">
          <input type="file" id="pack-file" accept=".mrpack,.zip" />
          <input id="pack-name" placeholder="实例名（可选）" style="width:200px" />
          <button class="btn primary" id="pack-import">导入</button>
        </div>
        <div class="small muted" style="margin-top:8px">支持 Modrinth .mrpack；CurseForge 需要先配 API key</div>
      </div>
    </div>
    <div class="card mods-page ${modsTab === "local" ? "active" : ""}" data-page="local" id="mods-local">
      <div class="card-head">
        <span class="card-title">本地模组</span>
        <div class="inline">
          <select id="mods-version">${options || '<option value="">没有已装版本</option>'}</select>
          <button class="btn" id="mods-refresh">刷新</button>
        </div>
      </div>
      <div class="list" id="local-mods"><div class="empty">加载中…</div></div>
    </div>
    <div class="card mods-page ${modsTab === "search" ? "active" : ""}" data-page="search" id="mods-search">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth</span>
        <div class="inline">
          <input class="search" id="mods-query" placeholder="例如 sodium" />
          <button class="btn primary" id="mods-search">搜索</button>
        </div>
      </div>
      <div class="list" id="mod-results"><div class="empty">输入关键词搜索</div></div>
    </div>
      </div>
    </div>`;
  const select = content.querySelector("#mods-version") as HTMLSelectElement;
  content.querySelectorAll<HTMLButtonElement>(".page-nav-item[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      modsTab = button.dataset.tab as string;
      content.querySelectorAll(".page-nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      content.querySelectorAll<HTMLElement>(".mods-page").forEach((page) => {
        page.classList.toggle("active", page.dataset.page === modsTab);
      });
    });
  });
  select.addEventListener("change", () => {
    modsVersion = select.value;
    void loadLocalMods();
  });
  content.querySelector("#mods-refresh")?.addEventListener("click", () => void loadLocalMods());
  content.querySelector("#mods-search")?.addEventListener("click", () => void searchMods());
  content.querySelector("#pack-import")?.addEventListener("click", async () => {
    const input = content.querySelector("#pack-file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) { toast("先选一个 .mrpack / .zip", "error"); return; }
    const name = (content.querySelector("#pack-name") as HTMLInputElement).value.trim();
    try {
      const response = await fetch("/api/modpack/install", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Filename": encodeURIComponent(file.name),
          "X-Pack-Name": encodeURIComponent(name),
        },
        body: await file.arrayBuffer(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      watchTask(data as TaskInfo, `导入 ${file.name}`);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  (content.querySelector("#mods-query") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void searchMods();
  });
  void loadLocalMods();
}

async function loadLocalMods(): Promise<void> {
  const list = document.getElementById("local-mods");
  if (!list || !modsVersion) return;
  try {
    const data = await api<{ mods: LocalMod[] }>(`/api/mods/local?version=${encodeURIComponent(modsVersion)}`);
    if (!data.mods.length) {
      list.innerHTML = `<div class="empty">还没有模组</div>`;
      return;
    }
    list.innerHTML = data.mods.map((mod) => `
      <div class="list-row">
        <div class="grow">
          <div class="title">${esc(mod.title)} ${mod.enabled ? '<span class="badge green">启用</span>' : '<span class="badge red">禁用</span>'}</div>
          <div class="desc">${esc(mod.version || mod.name)} · ${size(mod.size)}</div>
        </div>
        <button class="btn sm" data-toggle="${esc(mod.name)}">${mod.enabled ? "禁用" : "启用"}</button>
        <button class="btn sm danger" data-remove="${esc(mod.name)}">删除</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-toggle]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/mods/local/toggle", { method: "POST", body: JSON.stringify({ version: modsVersion, name: button.dataset.toggle }) });
        void loadLocalMods();
      });
    });
    list.querySelectorAll<HTMLButtonElement>("[data-remove]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/mods/local/remove", { method: "POST", body: JSON.stringify({ version: modsVersion, name: button.dataset.remove }) });
        toast("已删除", "ok");
        void loadLocalMods();
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

async function searchMods(): Promise<void> {
  const input = document.getElementById("mods-query") as HTMLInputElement;
  const query = input.value.trim();
  const list = document.getElementById("mod-results");
  if (!query || !modsVersion || !list) return;
  list.innerHTML = `<div class="empty">搜索中…</div>`;
  try {
    const data = await api<{ loader: string; game: string; hits: ModHit[] }>(
      `/api/mods?version=${encodeURIComponent(modsVersion)}&q=${encodeURIComponent(query)}`);
    if (!data.hits.length) {
      list.innerHTML = `<div class="empty">没有搜到结果</div>`;
      return;
    }
    list.innerHTML = data.hits.map((hit) => `
      <div class="list-row">
        <div class="grow">
          <div class="title">${esc(hit.title)} <span class="badge blue">${esc(data.loader)}</span></div>
          <div class="desc">${esc(hit.description)}</div>
        </div>
        <span class="small muted">${hit.downloads.toLocaleString()} 次</span>
        <button class="btn primary sm" data-mod="${esc(hit.slug)}">安装</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-mod]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const task = await api<TaskInfo>("/api/mods/install", {
            method: "POST",
            body: JSON.stringify({ version: modsVersion, slug: button.dataset.mod }),
          });
          watchTask(task, "安装模组");
        } catch (error) {
          toast((error as Error).message, "error");
        }
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

// ---------------------------------------------------------------- 设置
function renderSettings(): void {
  setHeader("设置", "修改会立即写入配置文件");
  const cfg = state.config;
  const content = document.getElementById("content") as HTMLElement;
  const account = state.account;
  content.innerHTML = `
    <div class="settings-layout">
      <aside class="settings-nav">
        <button class="settings-nav-item ${settingsTab === "account" ? "active" : ""}" data-tab="account">账号</button>
        <button class="settings-nav-item ${settingsTab === "skin" ? "active" : ""}" data-tab="skin">皮肤</button>
        <button class="settings-nav-item ${settingsTab === "general" ? "active" : ""}" data-tab="general">常规</button>
        <button class="settings-nav-item ${settingsTab === "download" ? "active" : ""}" data-tab="download">下载</button>
        <button class="settings-nav-item ${settingsTab === "appearance" ? "active" : ""}" data-tab="appearance">外观</button>
      </aside>
      <div class="settings-main">
    <div class="card settings-page ${settingsTab === "account" ? "active" : ""}" data-page="account" id="settings-account">
      <div class="card-head"><span class="card-title">微软账号</span></div>
      <div class="card-body">
        ${account ? `
          <div class="row-between">
            <div class="grow">
              <div class="title">${esc(account.name)}</div>
              <div class="desc">${esc(account.uuid)}</div>
            </div>
            <button class="btn danger" id="ms-logout">退出登录</button>
          </div>` : `
          ${MICROSOFT_LOGIN_ENABLED ? `
          <div class="field"><label>Azure 应用 client id（留空用内置 MCL 应用）</label>
            <input id="ms-client-id" type="text" value="${esc(cfg.ms_client_id)}" placeholder="${esc(state.default_client_id)}" />
          </div>
          <div class="inline">
            <button class="btn primary" id="ms-login">登录微软账号</button>
            <span class="small muted">内置应用开箱即用；想用自己的 app 再填</span>
          </div>` : `
          <div class="inline">
            <button class="btn" id="ms-login" aria-disabled="true" style="opacity:.55;cursor:not-allowed">微软登录（暂不可用）</button>
            <span class="small muted">Mojang 未通过 MCL 的申请，目前仅支持离线模式</span>
          </div>`}`}
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "skin" ? "active" : ""}" data-page="skin" id="settings-skin">
      <div class="card-head"><span class="card-title">离线皮肤</span></div>
      <div class="card-body">
        <div class="skin-row">
          <div class="skin-preview">${cfg.skin_preview
            ? `<div class="skin-head" style="--skin:url('${cfg.skin_preview}')"></div>`
            : `<span>${esc((cfg.username || "P").slice(0, 1).toUpperCase())}</span>`}</div>
          <div class="grow">
            <div class="title">自定义皮肤</div>
            <div class="desc">资源包模式：替换默认 Steve/Alex 贴图，离线可用。</div>
            <div class="inline" style="margin-top:8px">
              <select id="skin-model">
                <option value="classic" ${cfg.skin_model === "classic" ? "selected" : ""}>Steve（经典）</option>
                <option value="slim" ${cfg.skin_model === "slim" ? "selected" : ""}>Alex（纤细）</option>
              </select>
              <button class="btn" id="skin-pick">选择 PNG</button>
              <button class="btn" id="skin-off" ${cfg.custom_skin ? "" : "disabled"}>移除</button>
              <input id="skin-file" type="file" accept="image/png" hidden />
            </div>
          </div>
        </div>
        <div class="small muted" style="margin-top:10px">
          64×32 或 64×64 PNG，≤24 KB。资源包会替换所有默认皮肤，多人里其他默认皮肤玩家也会看到这张图。
        </div>
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "general" ? "active" : ""}" data-page="general" id="settings-general">
      <div class="card-head"><span class="card-title">常规</span></div>
      <div class="card-body">
        <div class="field"><label>游戏目录</label><input id="set-dir" type="text" value="${esc(cfg.game_dir)}" /></div>
        <div class="field"><label>Java 路径（留空自动按版本选）</label><input id="set-java" type="text" value="${esc(cfg.java_path)}" /></div>
        <div class="field"><label>内存（MB）</label><input id="set-memory" type="number" value="${cfg.memory_mb}" /></div>
        <div class="field"><label>离线用户名</label><input id="set-username" type="text" value="${esc(cfg.username)}" /></div>
        <div class="field"><label>版本隔离</label>
          <label class="checkbox"><input type="checkbox" id="set-isolate" ${cfg.isolate_versions ? "checked" : ""} /> 每个版本独立存档与模组目录</label>
        </div>
        <div class="inline">
          <button class="btn primary" id="set-save">保存</button>
          <span class="small muted">${esc(cfg.config_path)}</span>
        </div>
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "download" ? "active" : ""}" data-page="download" id="settings-download">
      <div class="card-head"><span class="card-title">下载</span></div>
      <div class="card-body">
        <div class="field"><label>下载源</label>
          <select id="set-source">
            <option value="official" ${cfg.download_source === "official" ? "selected" : ""}>仅官方</option>
            <option value="auto" ${cfg.download_source === "auto" ? "selected" : ""}>BMCLAPI 优先</option>
            <option value="custom" ${cfg.download_source === "custom" ? "selected" : ""}>自定义镜像</option>
          </select>
        </div>
        <div class="field"><label>自定义镜像 URL（根路径清单）</label>
          <input id="set-mirror" type="text" value="${esc(cfg.mirror_url)}" placeholder="http://home.free369.one:8000/mc" />
        </div>
        <div class="inline">
          <button class="btn primary" id="set-save-download">保存</button>
        </div>
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "appearance" ? "active" : ""}" data-page="appearance" id="settings-appearance">
      <div class="card-head"><span class="card-title">外观</span></div>
      <div class="card-body">
        <div class="field"><label>主题</label>
          <select id="set-theme">
            <option value="light" ${cfg.theme === "light" ? "selected" : ""}>浅色</option>
            <option value="dark" ${cfg.theme === "dark" ? "selected" : ""}>深色</option>
            <option value="system" ${cfg.theme === "system" ? "selected" : ""}>跟随系统</option>
          </select>
        </div>
        <div class="small muted">切换后立即生效并写入配置。</div>
      </div>
    </div>
      </div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>(".settings-nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      settingsTab = button.dataset.tab as string;
      content.querySelectorAll(".settings-nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      content.querySelectorAll<HTMLElement>(".settings-page").forEach((page) => {
        page.classList.toggle("active", page.dataset.page === settingsTab);
      });
    });
  });
  const themeSelect = content.querySelector("#set-theme") as HTMLSelectElement;
  themeSelect.addEventListener("change", async () => {
    applyTheme(themeSelect.value);
    try {
      await api("/api/config", { method: "POST", body: JSON.stringify({ theme: themeSelect.value }) });
      toast("主题已切换", "ok");
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  content.querySelector("#ms-logout")?.addEventListener("click", async () => {
    await api("/api/logout", { method: "POST", body: "{}" });
    toast("已退出微软账号", "ok");
    await refreshState();
  });
  content.querySelector("#ms-login")?.addEventListener("click", async () => {
    if (!MICROSOFT_LOGIN_ENABLED) {
      toast("微软登录暂不可用：Mojang 未通过申请，目前只支持离线模式", "error");
      return;
    }
    const clientId = (content.querySelector("#ms-client-id") as HTMLInputElement).value.trim();
    try {
      if (clientId) {
        await api("/api/config", { method: "POST", body: JSON.stringify({ ms_client_id: clientId }) });
      }
      const task = await api<TaskInfo>("/api/login/start", {
        method: "POST", body: JSON.stringify({ client_id: clientId }),
      });
      showLogin(task);
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  const skinFile = content.querySelector("#skin-file") as HTMLInputElement | null;
  content.querySelector("#skin-pick")?.addEventListener("click", () => skinFile?.click());
  skinFile?.addEventListener("change", async () => {
    const file = skinFile.files?.[0];
    if (!file) return;
    const model = (content.querySelector("#skin-model") as HTMLSelectElement).value;
    try {
      const response = await fetch("/api/skin", {
        method: "POST",
        headers: { "Content-Type": "image/png", "X-Skin-Model": model },
        body: await file.arrayBuffer(),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "上传失败");
      state.config = data.config;
      toast("皮肤已保存，启动时自动应用", "ok");
      renderSettings();
    } catch (error) {
      toast(`皮肤不可用：${(error as Error).message}`, "error");
    } finally {
      skinFile.value = "";
    }
  });
  content.querySelector("#skin-off")?.addEventListener("click", async () => {
    try {
      const data = await api<{ config: ConfigInfo }>("/api/skin/remove", { method: "POST", body: "{}" });
      state.config = data.config;
      toast("已移除自定义皮肤", "ok");
      renderSettings();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  content.querySelector("#skin-model")?.addEventListener("change", async (event) => {
    const model = (event.target as HTMLSelectElement).value;
    try {
      const data = await api<{ config: ConfigInfo }>("/api/config", {
        method: "POST", body: JSON.stringify({ skin_model: model }),
      });
      state.config = data.config;
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  content.querySelector("#set-save-download")?.addEventListener("click", () => {
    (content.querySelector("#set-save") as HTMLButtonElement)?.click();
  });
  content.querySelector("#set-save")?.addEventListener("click", async () => {
    try {
      await api("/api/config", {
        method: "POST",
        body: JSON.stringify({
          game_dir: (content.querySelector("#set-dir") as HTMLInputElement).value.trim(),
          java_path: (content.querySelector("#set-java") as HTMLInputElement).value.trim(),
          memory_mb: Number((content.querySelector("#set-memory") as HTMLInputElement).value),
          username: (content.querySelector("#set-username") as HTMLInputElement).value.trim() || "Player",
          download_source: (content.querySelector("#set-source") as HTMLSelectElement).value,
          mirror_url: (content.querySelector("#set-mirror") as HTMLInputElement).value.trim(),
          isolate_versions: (content.querySelector("#set-isolate") as HTMLInputElement).checked,
          theme: (content.querySelector("#set-theme") as HTMLSelectElement).value,
          ms_client_id: (content.querySelector("#ms-client-id") as HTMLInputElement)?.value.trim() ?? cfg.ms_client_id,
        }),
      });
      toast("设置已保存", "ok");
      await refreshState();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

function showLogin(task: TaskInfo): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `
    <div class="modal">
      <h3>微软登录</h3>
      <div class="field"><label>在浏览器打开</label>
        <div class="inline"><code id="login-uri">https://microsoft.com/devicelogin</code></div>
      </div>
      <div class="field"><label>输入代码</label>
        <div class="title" id="login-code" style="font-size:22px;letter-spacing:2px">等待微软返回…</div>
      </div>
      <div class="small muted" id="login-status">正在申请设备代码…</div>
      <div class="actions"><button class="btn" id="login-close">关闭</button></div>
    </div>`;
  document.body.appendChild(overlay);
  const close = () => { window.clearInterval(timer); overlay.remove(); };
  overlay.querySelector("#login-close")?.addEventListener("click", close);
  const timer = window.setInterval(async () => {
    try {
      const info = await api<TaskInfo>(`/api/task/${task.id}`);
      const result = info.result as { user_code?: string; verification_uri?: string } | null;
      if (result?.user_code) {
        (overlay.querySelector("#login-code") as HTMLElement).textContent = result.user_code;
        if (result.verification_uri) {
          (overlay.querySelector("#login-uri") as HTMLElement).textContent = result.verification_uri;
        }
      }
      (overlay.querySelector("#login-status") as HTMLElement).textContent =
        (info.log || []).slice(-1)[0] || "等待浏览器里完成登录…";
      if (info.state !== "running") {
        window.clearInterval(timer);
        if (info.state === "done") {
          overlay.remove();
          toast("登录成功", "ok");
          await refreshState();
        } else {
          (overlay.querySelector("#login-status") as HTMLElement).textContent = info.error || "登录失败";
          (overlay.querySelector("#login-close") as HTMLElement).textContent = "关闭";
        }
      }
    } catch (error) {
      window.clearInterval(timer);
      (overlay.querySelector("#login-status") as HTMLElement).textContent = (error as Error).message;
    }
  }, 1200);
}

// ---------------------------------------------------------------- 任务
function watchTask(task: TaskInfo, title: string): void {
  const panel = document.getElementById("task-panel") as HTMLElement;
  const bar = document.getElementById("task-bar") as HTMLElement;
  const stateLabel = document.getElementById("task-state") as HTMLElement;
  const files = document.getElementById("task-files") as HTMLElement;
  const bytes = document.getElementById("task-bytes") as HTMLElement;
  const log = document.getElementById("task-log") as HTMLElement;
  (document.getElementById("task-title") as HTMLElement).textContent = title;
  panel.classList.add("show");
  bar.style.width = "0%";
  log.textContent = "";
  stateLabel.textContent = "运行中";

  if (modsTimer) window.clearInterval(modsTimer);
  modsTimer = window.setInterval(async () => {
    try {
      const info = await api<TaskInfo>(`/api/task/${task.id}`);
      const progress = info.progress || {};
      const done = progress.done_bytes || 0;
      const total = progress.total_bytes || 0;
      const bySize = total > 0 ? done / total : 0;
      const byFiles = (progress.total_files || 0) > 0 ? (progress.done_files || 0) / (progress.total_files || 1) : 0;
      bar.style.width = `${Math.min(100, Math.round(Math.max(bySize, byFiles) * 100))}%`;
      files.textContent = `${progress.phase || ""} ${progress.done_files || 0}/${progress.total_files || 0}`;
      bytes.textContent = `${size(done)} / ${size(total)}`;
      log.textContent = (info.log || []).slice(-8).join("\n");
      if (info.state !== "running") {
        window.clearInterval(modsTimer as number);
        modsTimer = null;
        stateLabel.textContent = info.state === "done" ? "完成" : info.state === "error" ? "失败" : "已停止";
        bar.style.width = "100%";
        if (info.state === "error") toast(info.error || "任务失败", "error");
        else if (info.state === "done") toast(`${title} 完成`, "ok");
        await refreshState();
        window.setTimeout(() => panel.classList.remove("show"), 3500);
      }
    } catch (error) {
      window.clearInterval(modsTimer as number);
      modsTimer = null;
      stateLabel.textContent = "失败";
      toast((error as Error).message, "error");
    }
  }, 600);
}

// ---------------------------------------------------------------- 启动
async function boot(): Promise<void> {
  applyTheme(storedTheme());
  view = viewFromHash();
  app.innerHTML = shell();
  window.addEventListener("hashchange", () => {
    const next = viewFromHash();
    if (next !== view) { view = next; render(); }
  });
  document.querySelectorAll<HTMLButtonElement>("#nav .nav-item").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view as View));
  });
  try {
    await refreshState();
  } catch (error) {
    (document.getElementById("content") as HTMLElement).innerHTML =
      `<div class="card"><div class="empty">连接后端失败：${esc((error as Error).message)}</div></div>`;
  }
}

function setView(next: View): void {
  view = next;
  if (location.hash !== `#/${next}`) location.hash = `#/${next}`;
  render();
}

function viewFromHash(): View {
  const value = location.hash.replace(/^#\/?/, "");
  return (["versions", "install", "resources", "mods", "settings"] as View[]).includes(value as View)
    ? (value as View)
    : "versions";
}

boot().catch((error) => {
  console.error("MCL UI failed to start", error);
});
