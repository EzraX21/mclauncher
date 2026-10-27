type View = "versions" | "install" | "mods" | "settings";

interface VersionInfo {
  id: string; loader: string; java: number | null; mods: number; has_jar: boolean; type: string;
}
interface ConfigInfo {
  game_dir: string; java_path: string; memory_mb: number; username: string;
  isolate_versions: boolean; jobs: number; download_source: string;
  curseforge_configured: boolean; last_version: string; config_path: string; theme: string;
  ms_client_id: string;
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

const app = document.getElementById("app") as HTMLDivElement;
const toasts = (): HTMLElement => document.getElementById("toasts") as HTMLElement;

type ThemePref = "light" | "dark" | "system";
const darkMedia = window.matchMedia("(prefers-color-scheme: dark)");

function applyTheme(pref: string): void {
  const value: ThemePref = pref === "dark" || pref === "system" ? pref : "light";
  const resolved = value === "system" ? (darkMedia.matches ? "dark" : "light") : value;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themePref = value;
  localStorage.setItem("mcl-theme", value);
}

darkMedia.addEventListener("change", () => {
  if (document.documentElement.dataset.themePref === "system") applyTheme("system");
});

const icons: Record<View, string> = {
  versions: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M2 2h5v5H2V2zm7 0h5v5H9V2zM2 9h5v5H2V9zm7 0h5v5H9V9z"/></svg>',
  install: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a1 1 0 0 1 1 1v6.6l2.3-2.3 1.4 1.4L8 12.4 3.3 7.7l1.4-1.4L7 8.6V2a1 1 0 0 1 1-1zM2 13h12v2H2v-2z"/></svg>',
  mods: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M6 1v2h4V1h2v2h2v2h-2v4h2v2h-2v2H2v-2H1V9h2V5H1V3h2V1h3zm0 2H3v2h2v4H3v2h10v-2h-2V5h2V3h-2v2H6V3z"/></svg>',
  settings: '<svg viewBox="0 0 16 16" fill="currentColor"><path d="M8 5.5A2.5 2.5 0 1 0 8 10.5 2.5 2.5 0 0 0 8 5.5zm0-1.5 1.1-1.9 1.7.7.2 2.2 1.9 1.1V8l-1.9 1.1-.2 2.2-1.7.7L8 12l-1.1 1.9-1.7-.7-.2-2.2L3.1 9.9V8L5 6.9l.2-2.2 1.7-.7L8 4z"/></svg>',
};

function shell(): string {
  return `
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">M</div>
        <div>
          <div class="brand-name">MCL</div>
          <div class="brand-version" id="brand-version">v—</div>
        </div>
      </div>
      <nav class="nav" id="nav">
        ${(["versions", "install", "mods", "settings"] as View[]).map((name) => `
          <button class="nav-item" data-view="${name}">
            ${icons[name]}<span>${labelOf(name)}</span>
          </button>`).join("")}
      </nav>
      <div class="sidebar-foot" id="side-foot"></div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div>
          <h1 id="page-title">版本列表</h1>
          <div class="sub" id="page-sub"></div>
        </div>
        <div class="inline" id="top-actions"></div>
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
  return { versions: "版本列表", install: "安装", mods: "模组", settings: "设置" }[value];
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
  const actions = document.getElementById("top-actions") as HTMLElement;
  actions.innerHTML = "";
  if (view === "versions") {
    actions.innerHTML = `<button class="btn" id="refresh">刷新</button>`;
    actions.querySelector("#refresh")?.addEventListener("click", () => refreshState());
    renderVersions();
  } else if (view === "install") {
    renderInstall();
  } else if (view === "mods") {
    renderMods();
  } else {
    renderSettings();
  }
  actions.insertAdjacentHTML("beforeend",
    `<button class="btn sm" id="account-btn">${state.account ? esc(state.account.name) : "离线"}</button>`);
  actions.querySelector("#account-btn")?.addEventListener("click", () => setView("settings"));
}

// ---------------------------------------------------------------- 版本
function renderVersions(): void {
  setHeader("版本列表", `${state.versions.length} 个已安装版本`);
  const content = document.getElementById("content") as HTMLElement;
  if (!state.versions.length) {
    content.innerHTML = `
      <div class="card"><div class="empty">
        还没有安装任何版本。<br><br>
        <button class="btn primary" id="go-install">去安装一个</button>
      </div></div>`;
    content.querySelector("#go-install")?.addEventListener("click", () => setView("install"));
    return;
  }
  content.innerHTML = `
    <div class="card">
      <div class="list">
        ${state.versions.map((version) => `
          <div class="list-row">
            <div class="grow">
              <div class="title">${esc(version.id)} ${badge(version.loader)}
                ${version.has_jar ? "" : '<span class="badge red">缺客户端</span>'}</div>
              <div class="desc">Java ${version.java ?? "?"} · ${version.mods} 个模组</div>
            </div>
            <button class="btn" data-loader="${esc(version.id)}">装加载器</button>
            <button class="btn primary" data-launch="${esc(version.id)}">启动</button>
          </div>`).join("")}
      </div>
    </div>`;
  content.querySelectorAll<HTMLButtonElement>("[data-launch]").forEach((button) => {
    button.addEventListener("click", () => launch(button.dataset.launch as string, button));
  });
  content.querySelectorAll<HTMLButtonElement>("[data-loader]").forEach((button) => {
    button.addEventListener("click", () => openLoader(button.dataset.loader as string));
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
    </div>`;
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
          body: JSON.stringify({ id: button.dataset.install, assets }),
        });
        watchTask(task, `安装 ${button.dataset.install}`);
      } catch (error) {
        toast((error as Error).message, "error");
      }
    });
  });
}

// ---------------------------------------------------------------- 模组
function renderMods(): void {
  setHeader("模组", "Modrinth 搜索与本地管理");
  const content = document.getElementById("content") as HTMLElement;
  const options = state.versions.map((version) =>
    `<option value="${esc(version.id)}" ${version.id === modsVersion ? "selected" : ""}>${esc(version.id)} (${esc(version.loader)})</option>`).join("");
  content.innerHTML = `
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
    </div>
    <div class="card">
      <div class="card-head">
        <span class="card-title">本地模组</span>
        <div class="inline">
          <select id="mods-version">${options || '<option value="">没有已装版本</option>'}</select>
          <button class="btn" id="mods-refresh">刷新</button>
        </div>
      </div>
      <div class="list" id="local-mods"><div class="empty">加载中…</div></div>
    </div>
    <div class="card">
      <div class="card-head">
        <span class="card-title">搜索 Modrinth</span>
        <div class="inline">
          <input class="search" id="mods-query" placeholder="例如 sodium" />
          <button class="btn primary" id="mods-search">搜索</button>
        </div>
      </div>
      <div class="list" id="mod-results"><div class="empty">输入关键词搜索</div></div>
    </div>`;
  const select = content.querySelector("#mods-version") as HTMLSelectElement;
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
    <div class="card">
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
          <div class="field"><label>Azure 应用 client id（留空用内置 MCL 应用）</label>
            <input id="ms-client-id" type="text" value="${esc(cfg.ms_client_id)}" placeholder="${esc(state.default_client_id)}" />
          </div>
          <div class="inline">
            <button class="btn primary" id="ms-login">登录微软账号</button>
            <span class="small muted">内置应用开箱即用；想用自己的 app 再填</span>
          </div>`}
      </div>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">常规</span></div>
      <div class="card-body">
        <div class="field"><label>游戏目录</label><input id="set-dir" type="text" value="${esc(cfg.game_dir)}" /></div>
        <div class="field"><label>Java 路径（留空自动按版本选）</label><input id="set-java" type="text" value="${esc(cfg.java_path)}" /></div>
        <div class="field"><label>内存（MB）</label><input id="set-memory" type="number" value="${cfg.memory_mb}" /></div>
        <div class="field"><label>离线用户名</label><input id="set-username" type="text" value="${esc(cfg.username)}" /></div>
        <div class="field"><label>下载源</label>
          <select id="set-source">
            <option value="official" ${cfg.download_source === "official" ? "selected" : ""}>仅官方</option>
            <option value="auto" ${cfg.download_source === "auto" ? "selected" : ""}>BMCLAPI 优先</option>
          </select>
        </div>
        <div class="field"><label>主题</label>
          <select id="set-theme">
            <option value="light" ${cfg.theme === "light" ? "selected" : ""}>浅色</option>
            <option value="dark" ${cfg.theme === "dark" ? "selected" : ""}>深色</option>
            <option value="system" ${cfg.theme === "system" ? "selected" : ""}>跟随系统</option>
          </select>
        </div>
        <div class="field"><label>版本隔离</label>
          <label class="checkbox"><input type="checkbox" id="set-isolate" ${cfg.isolate_versions ? "checked" : ""} /> 每个版本独立存档与模组目录</label>
        </div>
        <div class="inline">
          <button class="btn primary" id="set-save">保存</button>
          <span class="small muted">${esc(cfg.config_path)}</span>
        </div>
      </div>
    </div>`;
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
  applyTheme(localStorage.getItem("mcl-theme") || "light");
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
  return (["versions", "install", "mods", "settings"] as View[]).includes(value as View)
    ? (value as View)
    : "versions";
}

void boot();
