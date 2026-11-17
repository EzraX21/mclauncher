type View = "versions" | "instance" | "download" | "link" | "toolbox" | "settings";
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
interface VersionOptions {
  memory_mb: number | null; width: number | null; height: number | null;
  jvm_args: string; game_args: string;
}
interface InstanceInfo {
  id: string; path: string; size: number; loader: string; java: number | null;
  mods: number; has_jar: boolean; type: string; inherits: string; options: VersionOptions;
}
interface JavaRuntimeInfo {
  display: string; path: string; major: number; version: string; configured: boolean;
}
interface JavaListing {
  runtimes: JavaRuntimeInfo[]; configured: string;
  components: { major: number; component: string }[];
}
interface UpdateInfo {
  current: string; latest: string; update_available: boolean;
  page: string; published: string; prerelease: boolean;
  assets: { name: string; size: number; url: string }[];
}
interface AboutInfo {
  version: string; python: string; platform: string; config_path: string;
  game_dir: string; exports_dir: string; license: string; repo: string; releases: string;
}
interface DoctorCheck { label: string; value: string; status: "ok" | "warn" | "bad" | "info"; }
interface DoctorReport {
  version: string; checks: DoctorCheck[]; problems: number;
  java: { display: string; path: string; major: number }[];
}
interface ServerStatus {
  online: boolean; error: string; latency_ms: number | null;
  players: { online: number; max: number }; version: string; motd: string;
}
interface ServerItem {
  index: number; name: string; ip: string; host: string; port: number;
  icon: string; accept_textures: boolean; status?: ServerStatus;
}
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
let settingsTab = "launch";
let downloadTab = "game";
let datapackVersion = "";
let datapackWorld = "";
let installLoader = "";
let installSelected = "";
let linkVersion = "";
let instanceId = "";
let instanceTab = "overview";

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
  instance: lucide('<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>'),
  download: lucide('<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>'),
  toolbox: lucide('<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'),
  link: lucide('<rect x="16" y="16" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="9" y="2" width="6" height="6" rx="1"/><path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/><path d="M12 12V8"/>'),
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
        ${(["versions", "instance", "download", "link", "toolbox", "settings"] as View[]).map((name) => `
          <button class="nav-item" data-view="${name}">
            ${icons[name]}<span>${labelOf(name)}</span>
          </button>`).join("")}
      </nav>
      <div class="titlebar-tools">
        <div class="inline" id="top-actions"></div>
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
  return { versions: "启动", instance: "版本管理", download: "下载",
    link: "联机", toolbox: "百宝箱", settings: "设置" }[value];
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
  } else if (view === "instance") {
    renderInstance();
  } else if (view === "download") {
    renderDownload();
  } else if (view === "link") {
    renderLink();
  } else if (view === "toolbox") {
    renderToolbox();
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
                <button class="btn sm" data-manage="${esc(version.id)}">管理</button>
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
  content.querySelector("#go-install")?.addEventListener("click", () => setView("download"));
  content.querySelector("#go-install-empty")?.addEventListener("click", () => setView("download"));
  content.querySelector("#refresh")?.addEventListener("click", () => refreshState());
  content.querySelectorAll<HTMLButtonElement>("[data-manage]").forEach((button) => {
    button.addEventListener("click", () => {
      instanceId = button.dataset.manage as string;
      setView("instance");
    });
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

// ---------------------------------------------------------------- 版本管理（PCL PageInstance）
function renderInstance(): void {
  setHeader("版本管理", "选中一个版本：概览、单版本设置、模组");
  const content = document.getElementById("content") as HTMLElement;
  if (!instanceId || !state.versions.some((item) => item.id === instanceId)) {
    instanceId = state.config.last_version || state.versions[0]?.id || "";
  }
  const rows = state.versions.map((version) => `
    <div class="list-row instance-row ${version.id === instanceId ? "active" : ""}" data-pick="${esc(version.id)}">
      <div class="grow">
        <div class="title">${esc(version.id)}</div>
        <div class="desc">${badge(version.loader)} Java ${version.java ?? "?"} · ${version.mods} 模组</div>
      </div>
    </div>`).join("");
  content.innerHTML = `
    <div class="instance-layout">
      <aside class="instance-side">
        <div class="card">
          <div class="card-head">
            <span class="card-title">已安装版本</span>
            <button class="btn sm" id="instance-refresh">刷新</button>
          </div>
          <div class="list" id="instance-list">
            ${rows || `<div class="empty">还没有版本，去「安装」页装一个</div>`}
          </div>
        </div>
      </aside>
      <div class="instance-main">
        <div class="loader-tabs" id="instance-tabs">
          ${[["overview", "概览"], ["setup", "设置"], ["mods", "模组"]].map(([value, label]) => `
            <button class="loader-tab ${instanceTab === value ? "active" : ""}" data-itab="${value}">${label}</button>`).join("")}
        </div>
        <div id="instance-detail"><div class="card"><div class="empty">加载中…</div></div></div>
      </div>
    </div>`;

  content.querySelectorAll<HTMLElement>("[data-pick]").forEach((row) => {
    row.addEventListener("click", () => {
      instanceId = row.dataset.pick as string;
      renderInstance();
    });
  });
  content.querySelector("#instance-refresh")?.addEventListener("click", () => void refreshState());
  content.querySelectorAll<HTMLButtonElement>("[data-itab]").forEach((button) => {
    button.addEventListener("click", () => {
      instanceTab = button.dataset.itab as string;
      content.querySelectorAll("[data-itab]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      void loadInstanceDetail();
    });
  });
  void loadInstanceDetail();
}

async function loadInstanceDetail(): Promise<void> {
  const host = document.getElementById("instance-detail");
  if (!host) return;
  if (!instanceId) {
    host.innerHTML = `<div class="card"><div class="empty">先装一个版本</div></div>`;
    return;
  }
  if (instanceTab === "mods") {
    await paintInstanceMods(host);
    return;
  }
  host.innerHTML = `<div class="card"><div class="empty">加载中…</div></div>`;
  try {
    const info = await api<InstanceInfo>(`/api/version/info?id=${encodeURIComponent(instanceId)}`);
    host.innerHTML = instanceTab === "setup" ? instanceSetupHtml(info) : instanceOverviewHtml(info);
    if (instanceTab === "setup") wireInstanceSetup(host, info);
    else wireInstanceOverview(host, info);
  } catch (error) {
    host.innerHTML = `<div class="card"><div class="empty">${esc((error as Error).message)}</div></div>`;
  }
}

function instanceOverviewHtml(info: InstanceInfo): string {
  const rows: [string, string][] = [
    ["版本名", info.id],
    ["加载器", info.loader === "vanilla" ? "原版" : info.loader],
    ["游戏版本", info.inherits || info.id],
    ["Java", info.java ? `Java ${info.java}` : "未确定"],
    ["模组", `${info.mods} 个`],
    ["占用", size(info.size)],
    ["类型", typeLabel(info.type)],
    ["路径", info.path],
  ];
  return `<div class="card">
    <div class="card-head">
      <span class="card-title">${esc(info.id)}</span>
      ${info.has_jar ? "" : '<span class="badge red">缺客户端</span>'}
    </div>
    <div class="card-body">
      <div class="kv-grid">
        ${rows.map(([key, value]) => `<div class="kv-key">${esc(key)}</div><div class="kv-value">${esc(value)}</div>`).join("")}
      </div>
    </div>
    <div class="card-body row-between instance-actions">
      <div class="inline">
        <button class="btn primary" id="inst-launch">启动</button>
        <button class="btn" id="inst-loader">装加载器</button>
        <button class="btn" id="inst-crash">崩溃分析</button>
      </div>
      <div class="inline">
        <button class="btn" id="inst-export">导出整合包</button>
        <button class="btn" id="inst-open">打开文件夹</button>
        <button class="btn" id="inst-rename">重命名</button>
        <button class="btn" id="inst-copy">复制</button>
        <button class="btn danger" id="inst-delete">删除</button>
      </div>
    </div>
  </div>`;
}

function wireInstanceOverview(host: HTMLElement, info: InstanceInfo): void {
  host.querySelector("#inst-launch")?.addEventListener("click", (event) => {
    void launch(info.id, event.target as HTMLButtonElement);
  });
  host.querySelector("#inst-loader")?.addEventListener("click", () => openLoader(info.id));
  host.querySelector("#inst-crash")?.addEventListener("click", () => void openCrash(info.id));
  host.querySelector("#inst-open")?.addEventListener("click", async () => {
    try {
      const data = await api<{ path: string }>("/api/versions/open", {
        method: "POST", body: JSON.stringify({ id: info.id }),
      });
      toast(`已打开 ${data.path}`, "ok");
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
  host.querySelector("#inst-export")?.addEventListener("click", () => openExport(info.id));
  host.querySelector("#inst-rename")?.addEventListener("click", () => openRename(info.id));
  host.querySelector("#inst-copy")?.addEventListener("click", () => openCopy(info.id));
  host.querySelector("#inst-delete")?.addEventListener("click", () => openDelete(info.id));
}

function instanceSetupHtml(info: InstanceInfo): string {
  const options = info.options;
  return `<div class="card">
    <div class="card-head"><span class="card-title">单版本设置 · ${esc(info.id)}</span></div>
    <div class="card-body">
      <div class="small muted" style="margin-bottom:12px">留空表示跟随全局设置。</div>
      <div class="field"><label>内存（MB）</label>
        <input id="inst-memory" type="number" min="512" max="65536" value="${options.memory_mb ?? ""}" /></div>
      <div class="inline" style="align-items:flex-start">
        <div class="field" style="flex:1"><label>窗口宽度</label>
          <input id="inst-width" type="number" min="320" max="10000" value="${options.width ?? ""}" /></div>
        <div class="field" style="flex:1"><label>窗口高度</label>
          <input id="inst-height" type="number" min="240" max="10000" value="${options.height ?? ""}" /></div>
      </div>
      <div class="field"><label>额外 JVM 参数</label>
        <textarea id="inst-jvm" rows="2" placeholder="-XX:+UseG1GC">${esc(options.jvm_args)}</textarea></div>
      <div class="field"><label>额外游戏参数</label>
        <textarea id="inst-game" rows="2" placeholder="--fullscreen">${esc(options.game_args)}</textarea></div>
      <div class="inline"><button class="btn primary" id="inst-save">保存</button></div>
    </div>
  </div>`;
}

function wireInstanceSetup(host: HTMLElement, info: InstanceInfo): void {
  host.querySelector("#inst-save")?.addEventListener("click", async () => {
    const value = (selector: string) => (host.querySelector(selector) as HTMLInputElement).value.trim();
    try {
      await api("/api/version/options", {
        method: "POST",
        body: JSON.stringify({
          id: info.id,
          memory_mb: value("#inst-memory") || null,
          width: value("#inst-width") || null,
          height: value("#inst-height") || null,
          jvm_args: value("#inst-jvm"),
          game_args: value("#inst-game"),
        }),
      });
      toast(`已保存 ${info.id} 的设置`, "ok");
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

async function paintInstanceMods(host: HTMLElement): Promise<void> {
  host.innerHTML = `<div class="card"><div class="empty">加载中…</div></div>`;
  try {
    const data = await api<{ mods: LocalMod[] }>(`/api/mods/local?version=${encodeURIComponent(instanceId)}`);
    host.innerHTML = `<div class="card">
      <div class="card-head">
        <span class="card-title">本地模组 · ${esc(instanceId)}</span>
        <div class="inline">
          <button class="btn sm" id="inst-mods-refresh">刷新</button>
          <button class="btn sm" id="inst-mods-search">去搜索安装</button>
        </div>
      </div>
      <div class="list">
        ${data.mods.length ? data.mods.map((mod) => `
          <div class="list-row">
            <div class="grow">
              <div class="title">${esc(mod.title)} ${mod.enabled ? '<span class="badge green">启用</span>' : '<span class="badge red">禁用</span>'}</div>
              <div class="desc">${esc(mod.version || mod.name)} · ${size(mod.size)}</div>
            </div>
            <button class="btn sm" data-itoggle="${esc(mod.name)}">${mod.enabled ? "禁用" : "启用"}</button>
            <button class="btn sm danger" data-iremove="${esc(mod.name)}">删除</button>
          </div>`).join("") : `<div class="empty">这个版本还没有模组</div>`}
      </div>
    </div>`;
    host.querySelector("#inst-mods-refresh")?.addEventListener("click", () => void paintInstanceMods(host));
    host.querySelector("#inst-mods-search")?.addEventListener("click", () => {
      modsVersion = instanceId;
      downloadTab = "mods";
      setView("download");
    });
    host.querySelectorAll<HTMLButtonElement>("[data-itoggle]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/mods/local/toggle", {
          method: "POST", body: JSON.stringify({ version: instanceId, name: button.dataset.itoggle }),
        });
        void paintInstanceMods(host);
      });
    });
    host.querySelectorAll<HTMLButtonElement>("[data-iremove]").forEach((button) => {
      button.addEventListener("click", async () => {
        await api("/api/mods/local/remove", {
          method: "POST", body: JSON.stringify({ version: instanceId, name: button.dataset.iremove }),
        });
        toast("已删除", "ok");
        void paintInstanceMods(host);
      });
    });
  } catch (error) {
    host.innerHTML = `<div class="card"><div class="empty">${esc((error as Error).message)}</div></div>`;
  }
}

function nameModal(title: string, label: string, value: string, action: string): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal" style="width:460px">
    <h3>${esc(title)}</h3>
    <div class="field"><label>${esc(label)}</label><input id="nm-value" type="text" value="${esc(value)}" /></div>
    <div class="actions">
      <button class="btn" id="nm-cancel">取消</button>
      <button class="btn primary" id="nm-ok">确定</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector("#nm-value") as HTMLInputElement;
  input.focus();
  input.select();
  const close = () => overlay.remove();
  overlay.querySelector("#nm-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  const submit = async () => {
    const newId = input.value.trim();
    if (!newId) { toast("名字不能为空", "error"); return; }
    try {
      const data = await api<{ id: string }>(action, {
        method: "POST", body: JSON.stringify({ id: instanceId, new_id: newId }),
      });
      close();
      instanceId = data.id;
      toast("完成", "ok");
      await refreshState();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  };
  overlay.querySelector("#nm-ok")?.addEventListener("click", () => void submit());
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") void submit(); });
}

interface ExportResult {
  path: string; name: string; game: string; loader: string;
  loader_version: string; files: number; size: number; warnings: string[];
}

function openExport(id: string): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal" style="width:520px">
    <h3>导出整合包 · ${esc(id)}</h3>
    <div class="small muted" style="margin-bottom:12px">
      导出成 Modrinth 格式 .mrpack：模组、配置、资源包打进去，加载器和游戏版本写进 dependencies，
      别的启动器也能导入。
    </div>
    <label class="checkbox"><input type="checkbox" id="ex-saves" /> 连存档（saves/）一起导出</label>
    <div class="actions">
      <button class="btn" id="ex-cancel">取消</button>
      <button class="btn primary" id="ex-go">导出</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#ex-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  overlay.querySelector("#ex-go")?.addEventListener("click", async () => {
    const button = overlay.querySelector("#ex-go") as HTMLButtonElement;
    const withSaves = (overlay.querySelector("#ex-saves") as HTMLInputElement).checked;
    button.disabled = true;
    button.textContent = "导出中…";
    try {
      const result = await api<ExportResult>("/api/modpack/export", {
        method: "POST", body: JSON.stringify({ version: id, with_saves: withSaves }),
      });
      const warnings = result.warnings.map((text) => `<div class="small" style="color:var(--danger)">${esc(text)}</div>`).join("");
      overlay.innerHTML = `<div class="modal" style="width:520px">
        <h3>导出完成</h3>
        <div class="kv-grid">
          <div class="kv-key">文件</div><div class="kv-value">${esc(result.path)}</div>
          <div class="kv-key">文件数</div><div class="kv-value">${result.files}</div>
          <div class="kv-key">大小</div><div class="kv-value">${size(result.size)}</div>
          <div class="kv-key">Minecraft</div><div class="kv-value">${esc(result.game)}</div>
          <div class="kv-key">加载器</div><div class="kv-value">${esc(`${result.loader} ${result.loader_version}`.trim())}</div>
        </div>
        ${warnings}
        <div class="actions">
          <button class="btn" id="ex-open">打开导出目录</button>
          <button class="btn primary" id="ex-done">关闭</button>
        </div>
      </div>`;
      overlay.querySelector("#ex-done")?.addEventListener("click", close);
      overlay.querySelector("#ex-open")?.addEventListener("click", async () => {
        try {
          await api("/api/exports/open", { method: "POST", body: JSON.stringify({ path: result.path }) });
        } catch (error) {
          toast((error as Error).message, "error");
        }
      });
      toast("整合包已导出", "ok");
    } catch (error) {
      button.disabled = false;
      button.textContent = "导出";
      toast((error as Error).message, "error");
    }
  });
}

function openRename(id: string): void {
  nameModal("重命名版本", "新名字（会改目录名和版本 JSON）", id, "/api/versions/rename");
}

function openCopy(id: string): void {
  nameModal("复制版本", "副本名字", `${id} 副本`, "/api/versions/copy");
}

// ---------------------------------------------------------------- 下载（PCL PageDownload）
// 顺序跟 PCL 的 PageDownloadLeft 一致：游戏本体 / 模组 / 整合包 / 数据包 / 材质包 / 光影
const DOWNLOAD_TABS: [string, string][] = [
  ["game", "游戏本体"], ["mods", "模组"], ["pack", "整合包"],
  ["datapack", "数据包"], ["resourcepack", "材质包"], ["shader", "光影"],
];

function renderDownload(): void {
  setHeader("下载", "游戏本体 / 加载器 / 整合包 / 模组 / 光影 / 材质包");
  const content = document.getElementById("content") as HTMLElement;
  content.innerHTML = `
    <div class="page-layout">
      <aside class="page-nav">
        ${DOWNLOAD_TABS.map(([value, label]) => `
          <button class="page-nav-item ${downloadTab === value ? "active" : ""}" data-dtab="${value}">${label}</button>`).join("")}
      </aside>
      <div class="page-main" id="dl-main"><div class="card"><div class="empty">加载中…</div></div></div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>("[data-dtab]").forEach((button) => {
    button.addEventListener("click", () => {
      downloadTab = button.dataset.dtab as string;
      renderDownload();
    });
  });
  void paintDownload();
}

async function paintDownload(): Promise<void> {
  const host = document.getElementById("dl-main");
  if (!host) return;
  if (downloadTab === "game") return paintDownloadGame(host);
  if (downloadTab === "pack") return paintDownloadPack(host);
  if (downloadTab === "mods") return paintDownloadMods(host);
  if (downloadTab === "datapack") return paintDownloadDatapacks(host);
  return paintDownloadResources(host, downloadTab);
}

function wireLoaderTabs(host: HTMLElement): void {
  host.querySelectorAll<HTMLButtonElement>(".loader-tab").forEach((button) => {
    button.addEventListener("click", () => {
      installLoader = button.dataset.loader as string;
      host.querySelectorAll(".loader-tab").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      toast(installLoader ? `安装时使用 ${installLoader}` : "安装原版", "ok");
    });
  });
}

async function paintDownloadGame(host: HTMLElement): Promise<void> {
  const selected = installSelected ? remote.find((item) => item.id === installSelected) : undefined;
  const loaderTabs = [["", "原版"], ["fabric", "Fabric"], ["quilt", "Quilt"],
    ["forge", "Forge"], ["neoforge", "NeoForge"]].map(([value, label]) => `
      <button class="loader-tab ${installLoader === value ? "active" : ""}" data-loader="${value}">${label}</button>`).join("");

  if (selected) {
    host.innerHTML = `
      <div class="card">
        <div class="card-head">
          <span class="card-title">安装 ${esc(selected.id)}</span>
          <button class="btn sm" id="install-back">返回版本列表</button>
        </div>
        <div class="card-body">
          <div class="small muted" style="margin-bottom:12px">${esc(typeLabel(selected.type))} · ${esc(selected.release)}</div>
          <div class="loader-tabs">${loaderTabs}</div>
          <div class="field"><label class="checkbox"><input type="checkbox" id="with-assets" checked /> 下载资源文件（音效、语言）</label></div>
          <button class="btn primary" id="install-confirm">安装 ${esc(selected.id)}</button>
        </div>
      </div>`;
    wireLoaderTabs(host);
    host.querySelector("#install-back")?.addEventListener("click", () => {
      installSelected = "";
      void paintDownload();
    });
    host.querySelector("#install-confirm")?.addEventListener("click", async () => {
      const assets = (host.querySelector("#with-assets") as HTMLInputElement).checked;
      const id = selected.id;
      try {
        const task = await api<TaskInfo>("/api/install", {
          method: "POST", body: JSON.stringify({ id, assets, loader: installLoader }),
        });
        installSelected = "";
        void paintDownload();
        watchTask(task, `安装 ${id}`);
      } catch (error) {
        toast((error as Error).message, "error");
      }
    });
    return;
  }

  host.innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">版本清单</span>
        <div class="inline">
          <input class="search" id="remote-filter" placeholder="搜索版本，例如 1.20.1" />
          <button class="btn" id="remote-refresh">刷新</button>
        </div>
      </div>
      <div class="card-body row-between">
        <span class="small muted">点一个版本进入安装选项</span>
        <span class="small muted" id="remote-hint">加载中…</span>
      </div>
      <div class="list" id="remote-list"></div>
    </div>`;
  const input = host.querySelector("#remote-filter") as HTMLInputElement;
  input.addEventListener("input", () => paintRemote());
  host.querySelector("#remote-refresh")?.addEventListener("click", () => void loadRemote(true));
  if (!remoteLoaded) await loadRemote(false); else paintRemote();
}

function paintDownloadPack(host: HTMLElement): void {
  host.innerHTML = `
    <div class="card">
      <div class="card-head"><span class="card-title">导入整合包</span></div>
      <div class="card-body">
        <div class="inline">
          <input type="file" id="pack-file" accept=".mrpack,.zip" />
          <input id="pack-name" placeholder="实例名（可选）" style="width:200px" />
          <button class="btn primary" id="pack-import">导入</button>
        </div>
        <div class="small muted" style="margin-top:8px">支持 Modrinth .mrpack；CurseForge 需要先配 API key</div>
      </div>
    </div>`;
  host.querySelector("#pack-import")?.addEventListener("click", async () => {
    const input = host.querySelector("#pack-file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) { toast("先选一个 .mrpack / .zip", "error"); return; }
    const name = (host.querySelector("#pack-name") as HTMLInputElement).value.trim();
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
}

function paintDownloadMods(host: HTMLElement): void {
  if (!modsVersion || !state.versions.some((version) => version.id === modsVersion)) {
    modsVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === modsVersion ? "selected" : ""}>${esc(version.id)} (${esc(version.loader)})</option>`).join("");
  host.innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth 模组</span>
        <div class="inline">
          <select id="mods-version">${options || '<option value="">没有已装版本</option>'}</select>
          <input class="search" id="mods-query" placeholder="例如 sodium" />
          <button class="btn primary" id="mods-search">搜索</button>
        </div>
      </div>
      <div class="list" id="mod-results"><div class="empty">输入关键词搜索；装好后在「版本管理 → 模组」里启停</div></div>
    </div>`;
  const select = host.querySelector("#mods-version") as HTMLSelectElement;
  select.addEventListener("change", () => { modsVersion = select.value; });
  host.querySelector("#mods-search")?.addEventListener("click", () => void searchMods());
  (host.querySelector("#mods-query") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void searchMods();
  });
}

async function paintDownloadDatapacks(host: HTMLElement): Promise<void> {
  if (!datapackVersion || !state.versions.some((version) => version.id === datapackVersion)) {
    datapackVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  const versionOptions = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === datapackVersion ? "selected" : ""}>${esc(version.id)}</option>`).join("");
  host.innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">数据包</span>
        <div class="inline">
          <select id="dp-version">${versionOptions || '<option value="">没有已装版本</option>'}</select>
          <select id="dp-world"><option value="">加载存档中…</option></select>
          <button class="btn" id="dp-refresh">刷新</button>
        </div>
      </div>
      <div class="card-body">
        <div class="small muted">数据包装在存档里，选好存档再装。<span id="dp-hint"></span></div>
      </div>
      <div class="list" id="dp-local"><div class="empty">先选存档</div></div>
    </div>
    <div class="card">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth 数据包</span>
        <div class="inline">
          <input class="search" id="dp-query" placeholder="例如 terralith" />
          <button class="btn primary" id="dp-search">搜索</button>
        </div>
      </div>
      <div class="list" id="dp-results"><div class="empty">输入关键词搜索</div></div>
    </div>`;
  const versionSelect = host.querySelector("#dp-version") as HTMLSelectElement;
  versionSelect.addEventListener("change", () => {
    datapackVersion = versionSelect.value;
    datapackWorld = "";
    void loadWorlds();
  });
  host.querySelector("#dp-refresh")?.addEventListener("click", () => void loadWorlds());
  host.querySelector("#dp-search")?.addEventListener("click", () => void searchDatapacks());
  (host.querySelector("#dp-query") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void searchDatapacks();
  });
  await loadWorlds();
}

async function loadWorlds(): Promise<void> {
  const select = document.getElementById("dp-world") as HTMLSelectElement | null;
  if (!select) return;
  if (!datapackVersion) {
    select.innerHTML = `<option value="">没有已装版本</option>`;
    return;
  }
  try {
    const data = await api<{ worlds: { name: string; datapacks: number }[] }>(
      `/api/worlds?version=${encodeURIComponent(datapackVersion)}`);
    if (!data.worlds.length) {
      select.innerHTML = `<option value="">这个版本还没有存档</option>`;
      datapackWorld = "";
      const list = document.getElementById("dp-local");
      if (list) list.innerHTML = `<div class="empty">这个版本还没有存档。先启动游戏进一次世界，存档才会出现。</div>`;
      return;
    }
    if (!datapackWorld || !data.worlds.some((world) => world.name === datapackWorld)) {
      datapackWorld = data.worlds[0].name;
    }
    select.innerHTML = data.worlds.map((world) =>
      `<option value="${esc(world.name)}" ${world.name === datapackWorld ? "selected" : ""}>${esc(world.name)}（${world.datapacks} 个数据包）</option>`).join("");
    select.onchange = () => {
      datapackWorld = select.value;
      void loadDatapacks();
    };
    await loadDatapacks();
  } catch (error) {
    select.innerHTML = `<option value="">加载失败</option>`;
    const list = document.getElementById("dp-local");
    if (list) list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

async function loadDatapacks(): Promise<void> {
  const list = document.getElementById("dp-local");
  const hint = document.getElementById("dp-hint");
  if (!list) return;
  if (!datapackWorld) {
    list.innerHTML = `<div class="empty">先选一个存档</div>`;
    return;
  }
  if (hint) hint.textContent = `当前：${datapackVersion} / ${datapackWorld}`;
  list.innerHTML = `<div class="empty">加载中…</div>`;
  try {
    const data = await api<{ files: { name: string; size: number; dir: boolean }[] }>(
      `/api/resources?kind=datapack&version=${encodeURIComponent(datapackVersion)}&world=${encodeURIComponent(datapackWorld)}`);
    if (!data.files.length) {
      list.innerHTML = `<div class="empty">这个存档还没有数据包</div>`;
      return;
    }
    list.innerHTML = data.files.map((item) => `
      <div class="list-row">
        <div class="grow"><div class="title">${esc(item.name)}</div>
          <div class="desc">${item.size ? `${(item.size / 1048576).toFixed(1)} MB` : "文件夹"}</div></div>
        <button class="btn sm danger" data-dp-del="${esc(item.name)}">删除</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-dp-del]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await api("/api/resources/delete", {
            method: "POST", body: JSON.stringify({
              kind: "datapack", version: datapackVersion, world: datapackWorld,
              name: button.dataset.dpDel,
            }),
          });
          toast("已删除", "ok");
          await loadDatapacks();
        } catch (error) {
          toast((error as Error).message, "error");
        }
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

async function searchDatapacks(): Promise<void> {
  const input = document.getElementById("dp-query") as HTMLInputElement;
  const query = input.value.trim();
  const list = document.getElementById("dp-results");
  if (!query || !datapackVersion || !list) return;
  if (!datapackWorld) {
    toast("先在左边选一个存档", "error");
    return;
  }
  list.innerHTML = `<div class="empty">搜索中…</div>`;
  try {
    const data = await api<{ hits: { slug: string; title: string; description: string; downloads: number }[] }>(
      `/api/resources?kind=datapack&version=${encodeURIComponent(datapackVersion)}&q=${encodeURIComponent(query)}`);
    if (!data.hits.length) {
      list.innerHTML = `<div class="empty">没有搜到结果</div>`;
      return;
    }
    list.innerHTML = data.hits.map((hit) => `
      <div class="list-row">
        <div class="grow"><div class="title">${esc(hit.title)}</div>
          <div class="desc">${esc(hit.description)}</div></div>
        <span class="small muted">${hit.downloads.toLocaleString()} 次</span>
        <button class="btn primary sm" data-dp-install="${esc(hit.slug)}">安装</button>
      </div>`).join("");
    list.querySelectorAll<HTMLButtonElement>("[data-dp-install]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          const task = await api<TaskInfo>("/api/resources/install", {
            method: "POST", body: JSON.stringify({
              kind: "datapack", version: datapackVersion, world: datapackWorld,
              slug: button.dataset.dpInstall,
            }),
          });
          watchTask(task, "安装数据包");
        } catch (error) {
          toast((error as Error).message, "error");
        }
      });
    });
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

async function paintDownloadResources(host: HTMLElement, kind: string): Promise<void> {
  resourceKind = kind === "resourcepack" ? "resourcepack" : "shader";
  if (!resourceVersion || !state.versions.some((version) => version.id === resourceVersion)) {
    resourceVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  const label = resourceKind === "shader" ? "光影" : "材质包";
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === resourceVersion ? "selected" : ""}>${esc(version.id)}</option>`).join("");
  host.innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">已安装${label}</span>
        <div class="inline">
          <select id="res-version">${options || '<option value="">没有已装版本</option>'}</select>
          <button class="btn" id="res-refresh">刷新</button>
        </div>
      </div>
      <div class="list" id="res-local"><div class="empty">加载中…</div></div>
    </div>
    <div class="card">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth ${label}</span>
        <div class="inline">
          <input class="search" id="res-query" placeholder="例如 Complementary" />
          <button class="btn primary" id="res-search">搜索</button>
        </div>
      </div>
      <div class="list" id="res-results"><div class="empty">输入关键词搜索</div></div>
    </div>`;
  (host.querySelector("#res-version") as HTMLSelectElement).addEventListener("change", (event) => {
    resourceVersion = (event.target as HTMLSelectElement).value;
    void loadResourceLocal();
  });
  host.querySelector("#res-refresh")?.addEventListener("click", () => void loadResourceLocal());
  host.querySelector("#res-search")?.addEventListener("click", () => void searchResources());
  (host.querySelector("#res-query") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void searchResources();
  });
  await loadResourceLocal();
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
    <div class="list-row version-pick" data-version="${esc(item.id)}">
      <div class="grow">
        <div class="title">${esc(item.id)} <span class="badge">${esc(typeLabel(item.type))}</span></div>
        <div class="desc">${esc(item.release)}</div>
      </div>
      <span class="chevron">›</span>
    </div>`).join("");
  list.querySelectorAll<HTMLElement>("[data-version]").forEach((row) => {
    row.addEventListener("click", () => {
      installSelected = row.dataset.version as string;
      void paintDownload();
    });
  });
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

// ---------------------------------------------------------------- 联机
function renderLink(): void {
  setHeader("联机", "服务器列表，点「进服」启动游戏并直连");
  const content = document.getElementById("content") as HTMLElement;
  if (!linkVersion || !state.versions.some((item) => item.id === linkVersion)) {
    linkVersion = state.config.last_version || state.versions[0]?.id || "";
  }
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === linkVersion ? "selected" : ""}>${esc(version.id)} (${esc(version.loader)})</option>`).join("");
  content.innerHTML = `
    <div class="card">
      <div class="card-head">
        <span class="card-title">服务器列表</span>
        <div class="inline">
          <select id="link-version">${options || '<option value="">没有已装版本</option>'}</select>
          <button class="btn" id="link-refresh">刷新状态</button>
        </div>
      </div>
      <div class="card-body">
        <div class="inline">
          <input id="link-name" placeholder="名字，例如 Hypixel" style="width:200px" />
          <input class="search" id="link-ip" placeholder="地址，例如 mc.hypixel.net" />
          <button class="btn primary" id="link-add">添加</button>
        </div>
        <div class="small muted" style="margin-top:8px">
          写进游戏自己的 servers.dat，在游戏里也能看到。<span id="link-path"></span>
        </div>
      </div>
      <div class="list" id="link-list"><div class="empty">加载中…</div></div>
    </div>`;

  const select = content.querySelector("#link-version") as HTMLSelectElement | null;
  select?.addEventListener("change", () => {
    linkVersion = select.value;
    void loadServers();
  });
  content.querySelector("#link-refresh")?.addEventListener("click", () => void loadServers());

  const submitAdd = async (): Promise<void> => {
    const nameInput = content.querySelector("#link-name") as HTMLInputElement;
    const ipInput = content.querySelector("#link-ip") as HTMLInputElement;
    const name = nameInput.value.trim();
    const ip = ipInput.value.trim();
    if (!ip) { toast("先填服务器地址", "error"); return; }
    try {
      await api("/api/servers/add", {
        method: "POST",
        body: JSON.stringify({ version: linkVersion, name: name || ip, ip }),
      });
      nameInput.value = "";
      ipInput.value = "";
      toast("已添加服务器", "ok");
      await loadServers();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  };
  content.querySelector("#link-add")?.addEventListener("click", () => void submitAdd());
  (content.querySelector("#link-ip") as HTMLInputElement).addEventListener("keydown", (event) => {
    if (event.key === "Enter") void submitAdd();
  });

  void loadServers();
}

async function loadServers(): Promise<void> {
  const list = document.getElementById("link-list");
  if (!list) return;
  if (!linkVersion) {
    list.innerHTML = `<div class="empty">先装一个版本：服务器列表跟着版本目录走</div>`;
    return;
  }
  list.innerHTML = `<div class="empty">正在查询服务器状态…</div>`;
  try {
    const data = await api<{ path: string; servers: ServerItem[] }>(
      `/api/servers?version=${encodeURIComponent(linkVersion)}&ping=1`);
    const pathLabel = document.getElementById("link-path");
    if (pathLabel) pathLabel.textContent = `（${data.path}）`;
    paintServers(data.servers);
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
}

function paintServers(items: ServerItem[]): void {
  const list = document.getElementById("link-list");
  if (!list) return;
  if (!items.length) {
    list.innerHTML = `<div class="empty">还没有服务器。上面填个名字和地址就能加进来。</div>`;
    return;
  }
  list.innerHTML = items.map((item) => serverRow(item)).join("");
  list.querySelectorAll<HTMLButtonElement>("[data-join]").forEach((button) => {
    button.addEventListener("click", () => void joinServer(Number(button.dataset.join), button));
  });
  list.querySelectorAll<HTMLButtonElement>("[data-edit]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items.find((entry) => entry.index === Number(button.dataset.edit));
      if (item) openServerEditor(item);
    });
  });
  list.querySelectorAll<HTMLButtonElement>("[data-del]").forEach((button) => {
    button.addEventListener("click", () => void removeServer(Number(button.dataset.del)));
  });
}

function serverRow(item: ServerItem): string {
  const status = item.status;
  const latency = status?.online
    ? `<span class="badge green">${status.latency_ms ?? 0} ms</span>`
    : status ? `<span class="badge red">离线</span>` : "";
  const players = status?.online
    ? `<span class="small muted">${status.players.online}/${status.players.max} 人</span>` : "";
  const gameVersion = status?.online && status.version
    ? `<span class="small muted">${esc(status.version)}</span>` : "";
  const motd = status?.online && status.motd ? ` · ${esc(status.motd)}` : "";
  const failure = status && !status.online && status.error
    ? `<div class="desc">${esc(status.error)}</div>` : "";
  return `
    <div class="list-row server-row">
      <div class="server-icon">${item.icon
        ? `<img src="${esc(item.icon)}" alt="" />`
        : esc(item.name.slice(0, 1).toUpperCase())}</div>
      <div class="grow">
        <div class="title">${esc(item.name)} ${latency}</div>
        <div class="desc">${esc(item.ip)}${motd}</div>
        ${failure}
      </div>
      <div class="inline">${players}${gameVersion}</div>
      <button class="btn sm" data-edit="${item.index}">编辑</button>
      <button class="btn sm danger" data-del="${item.index}">删除</button>
      <button class="btn primary sm" data-join="${item.index}">进服</button>
    </div>`;
}

async function joinServer(index: number, button: HTMLButtonElement): Promise<void> {
  button.disabled = true;
  const label = button.textContent;
  button.textContent = "启动中…";
  try {
    await api("/api/servers/join", {
      method: "POST",
      body: JSON.stringify({ version: linkVersion, index }),
    });
    toast("游戏已启动，正在进服", "ok");
  } catch (error) {
    toast(`进服失败：${(error as Error).message}`, "error");
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function openServerEditor(item: ServerItem): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal" style="width:460px">
    <h3>编辑服务器</h3>
    <div class="field"><label>名字</label><input id="srv-name" type="text" /></div>
    <div class="field"><label>地址</label><input id="srv-ip" type="text" /></div>
    <div class="actions">
      <button class="btn" id="srv-cancel">取消</button>
      <button class="btn primary" id="srv-save">保存</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  (overlay.querySelector("#srv-name") as HTMLInputElement).value = item.name;
  (overlay.querySelector("#srv-ip") as HTMLInputElement).value = item.ip;
  overlay.querySelector("#srv-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  overlay.querySelector("#srv-save")?.addEventListener("click", async () => {
    try {
      await api("/api/servers/update", {
        method: "POST",
        body: JSON.stringify({
          version: linkVersion,
          index: item.index,
          name: (overlay.querySelector("#srv-name") as HTMLInputElement).value.trim(),
          ip: (overlay.querySelector("#srv-ip") as HTMLInputElement).value.trim(),
        }),
      });
      close();
      toast("已保存", "ok");
      await loadServers();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

function removeServer(index: number): void {
  const overlay = document.createElement("div");
  overlay.className = "overlay";
  overlay.innerHTML = `<div class="modal">
    <h3>删除服务器</h3>
    <div class="small muted" style="margin-bottom:16px">只从 servers.dat 里去掉这一条，不会动游戏文件。</div>
    <div class="actions">
      <button class="btn" id="srv-del-cancel">取消</button>
      <button class="btn danger" id="srv-del-ok">删除</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector("#srv-del-cancel")?.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  overlay.querySelector("#srv-del-ok")?.addEventListener("click", async () => {
    try {
      await api("/api/servers/remove", {
        method: "POST",
        body: JSON.stringify({ version: linkVersion, index }),
      });
      close();
      toast("已删除", "ok");
      await loadServers();
    } catch (error) {
      toast((error as Error).message, "error");
    }
  });
}

// ---------------------------------------------------------------- 百宝箱（PCL PageOther）
const CHECK_ICON: Record<DoctorCheck["status"], string> = {
  ok: "✓", warn: "!", bad: "✗", info: "·",
};

function renderToolbox(): void {
  setHeader("百宝箱", "关于、环境诊断、快捷目录");
  const content = document.getElementById("content") as HTMLElement;
  content.innerHTML = `
    <div class="card" id="tb-about">
      <div class="card-head"><span class="card-title">关于</span></div>
      <div class="card-body"><div class="empty">加载中…</div></div>
    </div>
    <div class="card" id="tb-doctor">
      <div class="card-head">
        <span class="card-title">环境诊断</span>
        <button class="btn sm" id="tb-recheck">重新检测</button>
      </div>
      <div class="list" id="tb-checks"><div class="empty">检测中…</div></div>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">快捷目录</span></div>
      <div class="card-body">
        <div class="inline">
          <button class="btn" data-dir="config">配置目录</button>
          <button class="btn" data-dir="game">游戏目录</button>
          <button class="btn" data-dir="logs">日志目录</button>
          <button class="btn" data-dir="exports">导出目录</button>
        </div>
      </div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>("[data-dir]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await api("/api/open-dir", { method: "POST", body: JSON.stringify({ which: button.dataset.dir }) });
      } catch (error) {
        toast((error as Error).message, "error");
      }
    });
  });
  content.querySelector("#tb-recheck")?.addEventListener("click", () => void loadDoctor());
  void loadAbout();
  void loadDoctor();
}

async function loadAbout(): Promise<void> {
  const host = document.getElementById("tb-about");
  if (!host) return;
  try {
    const info = await api<AboutInfo>("/api/about");
    const rows: [string, string][] = [
      ["版本", `v${info.version}`],
      ["平台", info.platform],
      ["Python", info.python],
      ["许可证", info.license],
      ["配置", info.config_path],
      ["游戏目录", info.game_dir],
    ];
    host.innerHTML = `
      <div class="card-head"><span class="card-title">关于</span></div>
      <div class="card-body">
        <div class="kv-grid">
          ${rows.map(([key, value]) => `<div class="kv-key">${esc(key)}</div><div class="kv-value">${esc(value)}</div>`).join("")}
        </div>
        <div class="inline" style="margin-top:14px">
          <a class="btn" href="${esc(info.repo)}" target="_blank" rel="noreferrer">项目主页</a>
          <a class="btn" href="${esc(info.releases)}" target="_blank" rel="noreferrer">下载新版本</a>
          <button class="btn" id="tb-update">检查更新</button>
          <span class="small muted" id="tb-update-result"></span>
        </div>
      </div>`;
    // 这张卡片是异步渲染出来的，监听要挂在这里，不能挂在同步流程里
    host.querySelector("#tb-update")?.addEventListener("click", (event) => {
      void checkUpdate(event.target as HTMLButtonElement);
    });
  } catch (error) {
    host.innerHTML = `<div class="card-head"><span class="card-title">关于</span></div>
      <div class="card-body"><div class="empty">${esc((error as Error).message)}</div></div>`;
  }
}

async function checkUpdate(button: HTMLButtonElement, resultId = "tb-update-result"): Promise<void> {
  const result = document.getElementById(resultId);
  button.disabled = true;
  if (result) result.textContent = "查询中…";
  try {
    const data = await api<UpdateInfo>("/api/update");
    if (result) {
      result.innerHTML = data.update_available
        ? `<span class="badge red">有新版本 ${esc(data.latest)}</span>
           <a href="${esc(data.page)}" target="_blank" rel="noreferrer">去下载</a>`
        : `<span class="badge green">已是最新（${esc(data.latest)}）</span>`;
    }
    toast(data.update_available ? `有新版本 ${data.latest}` : "已经是最新版", "ok");
  } catch (error) {
    if (result) result.textContent = `查不到：${(error as Error).message}`;
    toast(`检查更新失败：${(error as Error).message}`, "error");
  } finally {
    button.disabled = false;
  }
}

async function loadDoctor(): Promise<void> {
  const list = document.getElementById("tb-checks");
  if (!list) return;
  list.innerHTML = `<div class="empty">检测中…</div>`;
  try {
    const data = await api<DoctorReport>("/api/doctor");
    const rows = data.checks.map((check) => `
      <div class="list-row check-row">
        <span class="check-mark ${check.status}">${CHECK_ICON[check.status] ?? "·"}</span>
        <div class="grow">
          <div class="title">${esc(check.label)}</div>
          <div class="desc">${esc(check.value)}</div>
        </div>
      </div>`).join("");
    const summary = data.problems
      ? `<div class="card-body"><span class="badge red">${data.problems} 个问题</span></div>`
      : `<div class="card-body"><span class="badge green">没发现问题</span></div>`;
    list.innerHTML = summary + rows;
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
        <button class="settings-nav-item ${settingsTab === "launch" ? "active" : ""}" data-tab="launch">启动</button>
        <button class="settings-nav-item ${settingsTab === "ui" ? "active" : ""}" data-tab="ui">个性化</button>
        <button class="settings-nav-item ${settingsTab === "system" ? "active" : ""}" data-tab="system">其他</button>
        <button class="settings-nav-item ${settingsTab === "link" ? "active" : ""}" data-tab="link">联机</button>
      </aside>
      <div class="settings-main">
    <div class="card settings-page ${settingsTab === "launch" ? "active" : ""}" data-page="launch" id="settings-account">
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
    <div class="card settings-page ${settingsTab === "ui" ? "active" : ""}" data-page="ui" id="settings-skin">
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
    <div class="card settings-page ${settingsTab === "launch" ? "active" : ""}" data-page="launch" id="settings-general">
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
    <div class="card settings-page ${settingsTab === "launch" ? "active" : ""}" data-page="launch" id="settings-java">
      <div class="card-head">
        <span class="card-title">Java 运行时</span>
        <button class="btn sm" id="java-refresh">重新检测</button>
      </div>
      <div class="list" id="java-runtimes"><div class="empty">检测中…</div></div>
      <div class="card-body" style="border-top:1px solid var(--border)">
        <div class="small muted" style="margin-bottom:10px">
          留空时按版本要求自动挑：要求 Java 8 的版本不会拿 Java 21 硬启动。
        </div>
        <div class="inline">
          <button class="btn" id="java-auto">自动选择</button>
          <span class="small muted">缺哪个版本就从 Mojang 下一份：</span>
          <span id="java-install"></span>
        </div>
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "launch" ? "active" : ""}" data-page="launch" id="settings-download">
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
    <div class="card settings-page ${settingsTab === "ui" ? "active" : ""}" data-page="ui" id="settings-appearance">
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
    <div class="card settings-page ${settingsTab === "system" ? "active" : ""}" data-page="system" id="settings-system">
      <div class="card-head"><span class="card-title">其他</span></div>
      <div class="card-body">
        <div class="kv-grid">
          <div class="kv-key">配置文件</div><div class="kv-value">${esc(cfg.config_path)}</div>
          <div class="kv-key">启动器版本</div><div class="kv-value">v${esc(state.version)}</div>
        </div>
        <div class="inline" style="margin-top:14px">
          <button class="btn" id="set-check-update">检查更新</button>
          <button class="btn" id="set-goto-toolbox">环境诊断</button>
          <span class="small muted" id="set-update-result"></span>
        </div>
      </div>
    </div>
    <div class="card settings-page ${settingsTab === "link" ? "active" : ""}" data-page="link" id="settings-link">
      <div class="card-head"><span class="card-title">联机</span></div>
      <div class="card-body">
        <div class="small muted" style="line-height:1.7">
          服务器列表跟版本走：写在某个版本的 <code>servers.dat</code> 里，
          开了版本隔离时每个实例有自己的列表。<br>
          延迟、在线人数和快速进服都在「联机」页里操作。
        </div>
        <div class="inline" style="margin-top:14px">
          <button class="btn primary" id="set-goto-link">打开联机页</button>
        </div>
      </div>
    </div>
      </div>
    </div>`;
  if (settingsTab === "launch") void loadJava();
  content.querySelectorAll<HTMLButtonElement>(".settings-nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      settingsTab = button.dataset.tab as string;
      content.querySelectorAll(".settings-nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      content.querySelectorAll<HTMLElement>(".settings-page").forEach((page) => {
        page.classList.toggle("active", page.dataset.page === settingsTab);
      });
      if (settingsTab === "launch") void loadJava();
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
  content.querySelector("#set-check-update")?.addEventListener("click", (event) => {
    void checkUpdate(event.target as HTMLButtonElement, "set-update-result");
  });
  content.querySelector("#set-goto-toolbox")?.addEventListener("click", () => setView("toolbox"));
  content.querySelector("#set-goto-link")?.addEventListener("click", () => setView("link"));
  content.querySelector("#java-refresh")?.addEventListener("click", () => void loadJava());
  content.querySelector("#java-auto")?.addEventListener("click", async () => {
    try {
      await api("/api/java/clear", { method: "POST", body: "{}" });
      toast("已改回自动选择", "ok");
      await loadJava();
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

async function loadJava(): Promise<void> {
  const list = document.getElementById("java-runtimes");
  const installHost = document.getElementById("java-install");
  if (!list) return;
  list.innerHTML = `<div class="empty">检测中…</div>`;
  try {
    const data = await api<JavaListing>("/api/java");
    if (!data.runtimes.length) {
      list.innerHTML = `<div class="empty">没找到 Java。可以下载一个 Mojang 运行时，或在下面手动指定。</div>`;
    } else {
      list.innerHTML = data.runtimes.map((runtime) => `
        <div class="list-row">
          <div class="grow">
            <div class="title">${esc(runtime.display)}
              ${runtime.configured ? '<span class="badge blue">当前指定</span>' : ""}</div>
            <div class="desc">${esc(runtime.path)}</div>
          </div>
          <button class="btn sm" data-java-set="${esc(runtime.path)}"
            ${runtime.configured ? "disabled" : ""}>设为默认</button>
        </div>`).join("");
      list.querySelectorAll<HTMLButtonElement>("[data-java-set]").forEach((button) => {
        button.addEventListener("click", async () => {
          try {
            await api("/api/java/set", {
              method: "POST", body: JSON.stringify({ path: button.dataset.javaSet }),
            });
            toast("已指定 Java", "ok");
            await loadJava();
          } catch (error) {
            toast((error as Error).message, "error");
          }
        });
      });
    }
    if (installHost) {
      installHost.innerHTML = data.components.map((item) =>
        `<button class="btn sm" data-java-install="${item.major}">Java ${item.major}</button>`).join(" ");
      installHost.querySelectorAll<HTMLButtonElement>("[data-java-install]").forEach((button) => {
        button.addEventListener("click", async () => {
          const major = button.dataset.javaInstall;
          button.disabled = true;
          try {
            const task = await api<TaskInfo>("/api/java/install", {
              method: "POST", body: JSON.stringify({ major: Number(major) }),
            });
            watchTask(task, `下载 Java ${major}`);
            window.setTimeout(() => { button.disabled = false; void loadJava(); }, 1500);
          } catch (error) {
            button.disabled = false;
            toast((error as Error).message, "error");
          }
        });
      });
    }
  } catch (error) {
    list.innerHTML = `<div class="empty">${esc((error as Error).message)}</div>`;
  }
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
  return (["versions", "instance", "download", "link", "toolbox", "settings"] as View[]).includes(value as View)
    ? (value as View)
    : "versions";
}

boot().catch((error) => {
  console.error("MCL UI failed to start", error);
});
