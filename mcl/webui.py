"""给 GUI 用的本地 HTTP + JSON 服务（只监听 127.0.0.1）。"""

from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, auth, crash, loaders, modpacks, modrinth, resources, skin
from .mods import find as find_mods, list_mods, remove as remove_mod, set_enabled
from .config import Config, config_path
from .installer import build_plan, execute
from .java import ensure_java
from .launch import build_command, ensure_libraries, prepare_natives, spawn
from .manifest import Manifest
from .rules import os_name
from .versions import VersionError, detect_loader, remove as remove_version, resolve, scan

TASKS: dict[str, dict] = {}
TASKS_LOCK = threading.Lock()
MANIFEST_CACHE: dict[str, Manifest] = {}


def _log(task: dict, message: str) -> None:
    with TASKS_LOCK:
        task["log"].append(message)
        del task["log"][:-300]


def _progress(task: dict, label: str, files: int, total_bytes: int) -> "TaskSink":
    with TASKS_LOCK:
        task["progress"] = {
            "phase": label, "done_files": 0, "total_files": files,
            "done_bytes": 0, "total_bytes": total_bytes,
        }
    return TaskSink(task)


class TaskSink:
    """下载进度 -> task 字典（供前端轮询）。"""

    def __init__(self, task: dict):
        self.task = task

    def add(self, nbytes: int) -> None:
        with TASKS_LOCK:
            progress = self.task.get("progress") or {}
            progress["done_bytes"] = progress.get("done_bytes", 0) + max(0, nbytes)
            self.task["progress"] = progress

    def tick(self) -> None:
        with TASKS_LOCK:
            progress = self.task.get("progress") or {}
            progress["done_files"] = progress.get("done_files", 0) + 1
            self.task["progress"] = progress


def _new_task(kind: str) -> dict:
    task = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "state": "running",
        "progress": {},
        "log": [],
        "error": None,
        "result": None,
    }
    with TASKS_LOCK:
        TASKS[task["id"]] = task
    return task


def _manifest(cfg: Config) -> Manifest:
    key = cfg.source
    if key not in MANIFEST_CACHE:
        MANIFEST_CACHE[key] = Manifest.load(cfg.source)
    return MANIFEST_CACHE[key]


def _config_dict(cfg: Config) -> dict:
    return {
        "game_dir": str(cfg.root()),
        "java_path": cfg.java_path or "",
        "memory_mb": cfg.memory_mb,
        "username": cfg.username,
        "isolate_versions": cfg.isolate_versions,
        "jobs": cfg.jobs,
        "download_source": cfg.download_source,
        "mirror_url": cfg.mirror_url,
        "custom_skin": cfg.custom_skin,
        "skin_model": cfg.skin_model,
        "skin_preview": skin.preview(cfg),
        "theme": getattr(cfg, "theme", "light"),
        "ms_client_id": cfg.ms_client_id,
        "curseforge_configured": bool(cfg.curseforge_api_key),
        "last_version": cfg.last_version or "",
        "config_path": str(config_path()),
    }


def _versions() -> list[dict]:
    cfg = _ACTIVE_CFG
    result = []
    for version in scan(cfg.root()):
        mods_dir = cfg.mods_path(version.id)
        mods = len(list(mods_dir.glob("*.jar"))) + len(list(mods_dir.glob("*.jar.disabled"))) if mods_dir.exists() else 0
        has_jar = version.has_jar
        if not has_jar:
            try:
                has_jar = resolve(cfg.root(), version.id).client_jar.exists()
            except Exception:  # noqa: BLE001
                has_jar = False
        result.append({
            "id": version.id,
            "loader": version.loader,
            "java": version.java_major,
            "mods": mods,
            "has_jar": has_jar,
            "type": version.type,
        })
    return result


_ACTIVE_CFG = Config.load()


# ---------------------------------------------------------------- 任务

def start_install(version_id: str, with_assets: bool) -> dict:
    cfg = _ACTIVE_CFG
    task = _new_task("install")

    def run() -> None:
        try:
            manifest = _manifest(cfg)
            version_json = manifest.version_json(manifest.resolve(version_id))
            plan = build_plan(version_json, cfg.root(), with_assets=with_assets,
                              source=cfg.source)
            _log(task, f"计划：{plan.total_files} 个文件，{round(plan.total_bytes / 1048576, 1)} MB")
            result = execute(plan, jobs=cfg.jobs, on_phase=lambda label, files, size: _progress(task, label, files, size),
                             on_note=lambda message: _log(task, message))
            if result.errors:
                raise RuntimeError(result.errors[0])
            task["result"] = {"version": version_id, "files": plan.total_files}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return task


def start_loader(version_id: str, loader: str) -> dict:
    cfg = _ACTIVE_CFG
    task = _new_task("loader")

    def run() -> None:
        try:
            resolved = resolve(cfg.root(), version_id)
            game = resolved.chain[0]
            java = ensure_java(cfg, resolved.java_major,
                               on_phase=lambda label, files, size: _progress(task, label, files, size),
                               note=lambda message: _log(task, message))
            created = loaders.install(loader, game, cfg.root(), source=cfg.source,
                                      java=java.path, on_log=lambda message: _log(task, message))
            task["result"] = {"version": created}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return task


def start_mod_install(version_id: str, slug: str) -> dict:
    cfg = _ACTIVE_CFG
    task = _new_task("mod")

    def run() -> None:
        try:
            resolved = resolve(cfg.root(), version_id)
            loader = detect_loader(version_id, resolved.data)
            game = resolved.chain[0]
            project = modrinth.get_project(slug, cfg.source)
            version = modrinth.latest_version(project.get("id", slug), loader, game, cfg.source)
            if version is None:
                raise RuntimeError(f"没有适配 {game} / {loader} 的版本")
            path = modrinth.download_version(version, cfg.mods_dir(version_id), cfg.source)
            _log(task, f"已安装 {path.name}")
            for dependency in modrinth.required_dependencies(version):
                dep = (modrinth.get_version(dependency["version_id"], cfg.source)
                       if dependency.get("version_id")
                       else modrinth.latest_version(dependency.get("project_id", ""), loader, game, cfg.source))
                if not dep:
                    continue
                dep_path = modrinth.download_version(dep, cfg.mods_dir(version_id), cfg.source)
                _log(task, f"前置 {dep_path.name}")
            task["result"] = {"file": path.name}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return task


def start_login(client_id: str) -> dict:
    if not auth.MICROSOFT_LOGIN_ENABLED:
        raise RuntimeError(auth.LOGIN_DISABLED_MESSAGE)
    cfg = _ACTIVE_CFG
    client_id = (client_id or cfg.ms_client_id or auth.DEFAULT_CLIENT_ID).strip()
    cfg.ms_client_id = client_id
    cfg.save()
    task = _new_task("login")

    def run() -> None:
        def on_code(device: dict) -> None:
            with TASKS_LOCK:
                task["result"] = {
                    "user_code": device.get("user_code", ""),
                    "verification_uri": device.get("verification_uri", ""),
                }
            _log(task, f"打开 {task['result']['verification_uri']}，输入 {task['result']['user_code']}")

        try:
            account = auth.login(client_id, on_code=on_code, on_status=lambda message: _log(task, message))
            with TASKS_LOCK:
                task["result"] = {"account": account.public()}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return task


def start_modpack(data: bytes, filename: str, name: str = "") -> dict:
    cfg = _ACTIVE_CFG
    suffix = Path(filename).suffix or ".mrpack"
    handle, path_text = tempfile.mkstemp(prefix="mcl-pack-", suffix=suffix)
    with os.fdopen(handle, "wb") as handle_file:
        handle_file.write(data)
    path = Path(path_text)
    task = _new_task("modpack")

    def run() -> None:
        try:
            version_id = modpacks.install(
                path, cfg, name=name or None,
                on_log=lambda message: _log(task, message),
                on_phase=lambda label, files, size: _progress(task, label, files, size),
            )
            task["result"] = {"version": version_id}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"
        finally:
            try:
                path.unlink()
            except OSError:
                pass

    threading.Thread(target=run, daemon=True).start()
    return task


def start_resource_install(kind: str, version_id: str, slug: str) -> dict:
    cfg = _ACTIVE_CFG
    task = _new_task("resource")

    def run() -> None:
        try:
            path = resources.install(kind, version_id, slug, cfg)
            _log(task, f"已安装 {path.name}")
            task["result"] = {"file": path.name}
            task["state"] = "done"
        except Exception as exc:  # noqa: BLE001
            task["error"] = str(exc)
            task["state"] = "error"

    threading.Thread(target=run, daemon=True).start()
    return task


def launch_version(version_id: str) -> dict:
    cfg = _ACTIVE_CFG
    resolved = resolve(cfg.root(), version_id)
    java = ensure_java(cfg, resolved.java_major, note=lambda message: None)
    ensure_libraries(resolved, cfg.root(), jobs=cfg.jobs, source=cfg.source)
    prepare_natives(resolved, cfg.root())
    account = auth.ensure_account(cfg)
    command = build_command(resolved, cfg, java, account=account)
    if command.missing:
        raise RuntimeError(f"缺少 {len(command.missing)} 个文件")
    try:
        skin.apply(cfg, resolved.id, resolved.chain[0])
    except skin.SkinError as exc:
        raise RuntimeError(f"自定义皮肤不可用：{exc}") from exc
    process = spawn(command)
    cfg.last_version = resolved.id
    cfg.save()
    return {"pid": process.pid, "version": resolved.id}


# ---------------------------------------------------------------- HTTP

def _static_dir() -> Optional[Path]:
    env = os.environ.get("MCL_WEB_DIR")
    candidates = [Path(env) if env else None,
                  Path(__file__).parent.parent / "gui" / "dist",
                  Path(__file__).parent / "webui_dist"]
    for candidate in candidates:
        if candidate and (candidate / "index.html").exists():
            return candidate
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = f"mcl/{__version__}"

    def log_message(self, *_args) -> None:  # 安静点
        pass

    # ------------------------------------------------------------ 工具
    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        if length > 512 * 1024 * 1024:
            raise RuntimeError("整合包太大了（上限 512 MB）")
        return self.rfile.read(length)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    # ------------------------------------------------------------ GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/state":
                account = auth.load_account() if auth.MICROSOFT_LOGIN_ENABLED else None
                return self._json({
                    "version": __version__,
                    "config": _config_dict(_ACTIVE_CFG),
                    "versions": _versions(),
                    "account": account.public() if account else None,
                    "default_client_id": auth.DEFAULT_CLIENT_ID,
                    "platform": os_name(),
                })
            if parsed.path == "/api/remote":
                manifest = _manifest(_ACTIVE_CFG)
                needle = (query.get("q", [""])[0] or "").lower()
                versions = [{"id": v.id, "type": v.type, "release": v.release_time[:10]}
                            for v in manifest.versions if not needle or needle in v.id.lower()]
                return self._json({
                    "latest": {"release": manifest.latest_release,
                               "snapshot": manifest.latest_snapshot},
                    "versions": versions[:400],
                })
            if parsed.path == "/api/mods":
                version_id = query.get("version", [""])[0]
                text = query.get("q", [""])[0]
                if not version_id or not text:
                    return self._error("缺少 version 或 q")
                resolved = resolve(_ACTIVE_CFG.root(), version_id)
                loader = detect_loader(version_id, resolved.data)
                game = resolved.chain[0]
                if loader == "vanilla":
                    return self._error("这个版本没有加载器，先装 Fabric/Forge")
                hits = modrinth.search(text, loader=loader, game_version=game, limit=20,
                                       source=_ACTIVE_CFG.source)
                return self._json({
                    "loader": loader, "game": game,
                    "hits": [{"slug": hit.slug, "title": hit.title,
                              "description": hit.description, "downloads": hit.downloads,
                              "author": hit.author} for hit in hits],
                })
            if parsed.path == "/api/resources":
                kind = query.get("kind", ["shader"])[0]
                version_id = query.get("version", [""])[0]
                text = query.get("q", [""])[0]
                if not version_id:
                    return self._error("缺少 version")
                if text:
                    return self._json({"hits": resources.search(
                        kind, text, version_id, _ACTIVE_CFG.source)})
                return self._json({"files": resources.local(
                    kind, _ACTIVE_CFG, version_id)})
            if parsed.path == "/api/crash":
                version_id = query.get("version", [""])[0] or None
                return self._json(crash.analyze_version(_ACTIVE_CFG, version_id))
            if parsed.path == "/api/mods/local":
                version_id = query.get("version", [""])[0]
                if not version_id:
                    return self._error("缺少 version")
                items = list_mods(_ACTIVE_CFG.mods_path(version_id))
                return self._json({"mods": [{
                    "name": mod.name, "enabled": mod.enabled, "size": mod.size,
                    "title": mod.title or mod.name, "version": mod.version or "",
                } for mod in items]})
            if parsed.path.startswith("/api/task/"):
                task_id = parsed.path.rsplit("/", 1)[-1]
                with TASKS_LOCK:
                    task = TASKS.get(task_id)
                    if task is None:
                        return self._error("任务不存在", 404)
                    return self._json(task)
            if parsed.path.startswith("/api/"):
                return self._error("未知接口", 404)
            return self._static(parsed.path)
        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc), 500)

    # ------------------------------------------------------------ POST
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/modpack/install":
                filename = unquote(self.headers.get("X-Filename", "pack.mrpack"))
                name = unquote(self.headers.get("X-Pack-Name", ""))
                return self._json(start_modpack(self._raw_body(), filename, name))
            if parsed.path == "/api/skin":
                model = unquote(self.headers.get("X-Skin-Model", "classic"))
                try:
                    skin.save(self._raw_body(), model)
                except skin.SkinError as exc:
                    return self._error(str(exc), 400)
                _ACTIVE_CFG.custom_skin = True
                _ACTIVE_CFG.skin_model = model if model in ("classic", "slim") else "classic"
                _ACTIVE_CFG.save()
                return self._json({"config": _config_dict(_ACTIVE_CFG)})
            if parsed.path == "/api/skin/remove":
                skin.clear()
                _ACTIVE_CFG.custom_skin = False
                _ACTIVE_CFG.save()
                return self._json({"config": _config_dict(_ACTIVE_CFG)})
            body = self._body()
            if parsed.path == "/api/install":
                return self._json(start_install(body.get("id", ""), bool(body.get("assets", True))))
            if parsed.path == "/api/loader":
                return self._json(start_loader(body.get("id", ""), body.get("loader", "fabric")))
            if parsed.path == "/api/mods/install":
                return self._json(start_mod_install(body.get("version", ""), body.get("slug", "")))
            if parsed.path == "/api/login/start":
                if not auth.MICROSOFT_LOGIN_ENABLED:
                    return self._error(auth.LOGIN_DISABLED_MESSAGE, 403)
                return self._json(start_login(body.get("client_id", "")))
            if parsed.path == "/api/logout":
                auth.clear_account()
                return self._json({"ok": True})
            if parsed.path == "/api/launch":
                return self._json(launch_version(body.get("id", "")))
            if parsed.path == "/api/versions/remove":
                version_id = str(body.get("id", "")).strip()
                try:
                    remove_version(_ACTIVE_CFG.root(), version_id)
                except VersionError as exc:
                    return self._error(str(exc), 404)
                if _ACTIVE_CFG.last_version == version_id:
                    _ACTIVE_CFG.last_version = None
                    _ACTIVE_CFG.save()
                return self._json({"ok": True, "versions": _versions()})
            if parsed.path == "/api/cancel":
                with TASKS_LOCK:
                    task = TASKS.get(body.get("id", ""))
                    if task and task["state"] == "running":
                        task["state"] = "cancelled"
                return self._json({"ok": True})
            if parsed.path == "/api/resources/install":
                return self._json(start_resource_install(
                    body.get("kind", "shader"), body.get("version", ""),
                    body.get("slug", "")))
            if parsed.path == "/api/resources/delete":
                ok = resources.remove(body.get("kind", "shader"), _ACTIVE_CFG,
                                      body.get("version", ""), body.get("name", ""))
                return self._json({"ok": ok})
            if parsed.path == "/api/mods/local/toggle":
                version_id = body.get("version", "")
                matches = find_mods(_ACTIVE_CFG.mods_path(version_id), body.get("name", ""))
                if not matches:
                    return self._error("找不到模组", 404)
                set_enabled(matches[0], not matches[0].enabled)
                return self._json({"ok": True})
            if parsed.path == "/api/mods/local/remove":
                version_id = body.get("version", "")
                matches = find_mods(_ACTIVE_CFG.mods_path(version_id), body.get("name", ""))
                if not matches:
                    return self._error("找不到模组", 404)
                remove_mod(matches[0])
                return self._json({"ok": True})
            if parsed.path == "/api/config":
                cfg = _ACTIVE_CFG
                if "mirror_url" in body:
                    mirror = str(body["mirror_url"]).strip().rstrip("/")
                    if mirror and not mirror.startswith(("http://", "https://")):
                        return self._error("镜像 URL 要以 https:// 或 http:// 开头")
                    body["mirror_url"] = mirror
                if body.get("skin_model") not in (None, "classic", "slim"):
                    return self._error("皮肤模型只能是 classic 或 slim")
                for key in ("game_dir", "java_path", "memory_mb", "username",
                            "isolate_versions", "jobs", "download_source", "mirror_url",
                            "custom_skin", "skin_model"):
                    if key in body:
                        setattr(cfg, key, body[key])
                if body.get("theme") in ("light", "dark", "system"):
                    cfg.theme = body["theme"]
                if "ms_client_id" in body:
                    cfg.ms_client_id = str(body["ms_client_id"]).strip()
                cfg.save()
                return self._json({"config": _config_dict(cfg), "versions": _versions()})
            return self._error("未知接口", 404)
        except Exception as exc:  # noqa: BLE001
            return self._error(str(exc), 500)

    # ------------------------------------------------------------ static
    def _static(self, path: str) -> None:
        root = _static_dir()
        if root is None:
            return self._error("界面还没构建：cd gui && npm install && npm run build", 503)
        relative = unquote(path.lstrip("/")) or "index.html"
        target = (root / relative).resolve()
        if not str(target).startswith(str(root.resolve())) or not target.exists():
            target = root / "index.html"
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def serve(config: Config, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    global _ACTIVE_CFG
    _ACTIVE_CFG = config
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    return httpd, url


def open_browser(url: str) -> None:
    webbrowser.open(url)
