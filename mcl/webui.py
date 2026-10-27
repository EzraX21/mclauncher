"""给 GUI 用的本地 HTTP + JSON 服务（只监听 127.0.0.1）。"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__, loaders, modrinth
from .mods import find as find_mods, list_mods, remove as remove_mod, set_enabled
from .config import Config, config_path
from .installer import build_plan, execute
from .java import ensure_java
from .launch import build_command, ensure_libraries, prepare_natives, spawn
from .manifest import Manifest
from .rules import os_name
from .versions import detect_loader, resolve, scan

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
    key = cfg.download_source
    if key not in MANIFEST_CACHE:
        MANIFEST_CACHE[key] = Manifest.load(cfg.download_source)
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
        "theme": getattr(cfg, "theme", "light"),
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
                              source=cfg.download_source)
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
            created = loaders.install(loader, game, cfg.root(), source=cfg.download_source,
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
            project = modrinth.get_project(slug, cfg.download_source)
            version = modrinth.latest_version(project.get("id", slug), loader, game, cfg.download_source)
            if version is None:
                raise RuntimeError(f"没有适配 {game} / {loader} 的版本")
            path = modrinth.download_version(version, cfg.mods_dir(version_id), cfg.download_source)
            _log(task, f"已安装 {path.name}")
            for dependency in modrinth.required_dependencies(version):
                dep = (modrinth.get_version(dependency["version_id"], cfg.download_source)
                       if dependency.get("version_id")
                       else modrinth.latest_version(dependency.get("project_id", ""), loader, game, cfg.download_source))
                if not dep:
                    continue
                dep_path = modrinth.download_version(dep, cfg.mods_dir(version_id), cfg.download_source)
                _log(task, f"前置 {dep_path.name}")
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
    ensure_libraries(resolved, cfg.root(), jobs=cfg.jobs, source=cfg.download_source)
    prepare_natives(resolved, cfg.root())
    command = build_command(resolved, cfg, java)
    if command.missing:
        raise RuntimeError(f"缺少 {len(command.missing)} 个文件")
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
                return self._json({
                    "version": __version__,
                    "config": _config_dict(_ACTIVE_CFG),
                    "versions": _versions(),
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
                                       source=_ACTIVE_CFG.download_source)
                return self._json({
                    "loader": loader, "game": game,
                    "hits": [{"slug": hit.slug, "title": hit.title,
                              "description": hit.description, "downloads": hit.downloads,
                              "author": hit.author} for hit in hits],
                })
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
            body = self._body()
            if parsed.path == "/api/install":
                return self._json(start_install(body.get("id", ""), bool(body.get("assets", True))))
            if parsed.path == "/api/loader":
                return self._json(start_loader(body.get("id", ""), body.get("loader", "fabric")))
            if parsed.path == "/api/mods/install":
                return self._json(start_mod_install(body.get("version", ""), body.get("slug", "")))
            if parsed.path == "/api/launch":
                return self._json(launch_version(body.get("id", "")))
            if parsed.path == "/api/cancel":
                with TASKS_LOCK:
                    task = TASKS.get(body.get("id", ""))
                    if task and task["state"] == "running":
                        task["state"] = "cancelled"
                return self._json({"ok": True})
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
                for key in ("game_dir", "java_path", "memory_mb", "username",
                            "isolate_versions", "jobs", "download_source"):
                    if key in body:
                        setattr(cfg, key, body[key])
                if body.get("theme") in ("light", "dark", "system"):
                    cfg.theme = body["theme"]
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
