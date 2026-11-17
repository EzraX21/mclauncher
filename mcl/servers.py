"""服务器列表：读写 `servers.dat`，以及 Server List Ping。

路径跟游戏一致：开了版本隔离时，游戏的工作目录是 `versions/<id>/`，它读的
`servers.dat` 就在那里；关掉隔离才在游戏根目录。写错位置的话游戏里根本看不到。
"""

from __future__ import annotations

import io
import json
import os
import socket
import struct
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Optional

from . import nbt
from .config import Config

DEFAULT_PORT = 25565
MAX_SERVERS = 200
PING_TIMEOUT = 2.0
# 状态查询的协议号；服务器只拿它填返回里的 version 字段，不影响能否连上。
PROTOCOL_VERSION = 767


class ServerError(ValueError):
    """服务器列表读写失败，或者用户输入不合法。"""


# ---------------------------------------------------------------- 地址

def split_address(ip: str) -> tuple[str, int]:
    """把 `host` / `host:port` / `[::1]:port` 拆成 (host, port)。"""
    text = (ip or "").strip()
    if not text:
        return "", DEFAULT_PORT
    if text.startswith("["):
        end = text.find("]")
        if end == -1:
            return text, DEFAULT_PORT
        host = text[1:end]
        rest = text[end + 1:]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, DEFAULT_PORT
    if text.count(":") == 1:
        host, _, port_text = text.partition(":")
        if port_text.isdigit() and host:
            return host, int(port_text)
    return text, DEFAULT_PORT


def join_address(host: str, port: int) -> str:
    """反向拼回去。默认端口不写出来，跟游戏里的显示一致。"""
    if ":" in host:
        host = f"[{host}]"
    return host if port == DEFAULT_PORT else f"{host}:{port}"


def _validate_port(port: int) -> int:
    if not 1 <= port <= 65535:
        raise ServerError(f"端口要在 1 到 65535 之间，收到 {port}")
    return port


# ---------------------------------------------------------------- 路径 / 读写

def servers_path(cfg: Config, version_id: str) -> Path:
    """只算路径，不建目录（列表时用）。"""
    base = cfg.version_dir(version_id) if cfg.isolate_versions else cfg.root()
    return base / "servers.dat"


def _empty_root() -> dict:
    return {"servers": nbt.NbtList([], tag=nbt.TAG_COMPOUND)}


def _read_root(path: Path) -> dict:
    """读 `servers.dat`。文件不存在当空表；文件坏了要报错，绝不能当空表覆盖。"""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return _empty_root()
    except OSError as exc:
        raise ServerError(f"读不了 {path}：{exc}") from exc
    if not raw:
        return _empty_root()
    try:
        root = nbt.loads(raw)
    except nbt.NbtError as exc:
        raise ServerError(f"{path.name} 解析失败（文件可能损坏）：{exc}") from exc
    servers = root.get("servers")
    if servers is None:
        root["servers"] = nbt.NbtList([], tag=nbt.TAG_COMPOUND)
    elif not isinstance(servers, list):
        raise ServerError(f"{path.name} 里的 servers 不是列表")
    return root


def _save_root(path: Path, root: dict) -> None:
    """先写临时文件再原子替换：游戏退出时也会写这个文件，不能写一半。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = nbt.dumps(root)
    handle, tmp_name = tempfile.mkstemp(prefix=".servers-", suffix=".dat", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _view(entry: dict, index: int) -> dict:
    ip = str(entry.get("ip") or "")
    host, port = split_address(ip)
    icon = entry.get("icon")
    return {
        "index": index,
        "name": str(entry.get("name") or host or "未命名服务器"),
        "ip": ip,
        "host": host,
        "port": port,
        "icon": icon if isinstance(icon, str) else "",
        "accept_textures": bool(int(entry.get("acceptTextures") or 0)),
    }


def listing(cfg: Config, version_id: str) -> dict:
    path = servers_path(cfg, version_id)
    root = _read_root(path)
    return {
        "version": version_id,
        "path": str(path),
        "servers": [_view(entry, index) for index, entry in enumerate(root["servers"])],
    }


def _check_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ServerError("服务器名字不能为空")
    if len(cleaned) > 80:
        raise ServerError("服务器名字太长（上限 80 字）")
    return cleaned


def _check_ip(ip: str) -> tuple[str, int]:
    text = (ip or "").strip()
    if not text:
        raise ServerError("服务器地址不能为空")
    host, port = split_address(text)
    if not host:
        raise ServerError("服务器地址不合法")
    _validate_port(port)
    return host, port


def add(cfg: Config, version_id: str, name: str, ip: str) -> dict:
    path = servers_path(cfg, version_id)
    root = _read_root(path)
    servers = root["servers"]
    if len(servers) >= MAX_SERVERS:
        raise ServerError(f"服务器太多了（上限 {MAX_SERVERS} 个）")
    clean_name = _check_name(name)
    host, port = _check_ip(ip)
    servers.append({
        "name": clean_name,
        "ip": join_address(host, port),
        "acceptTextures": nbt.NbtByte(1),
    })
    _save_root(path, root)
    return listing(cfg, version_id)


def update(cfg: Config, version_id: str, index: int, name: Optional[str] = None,
           ip: Optional[str] = None) -> dict:
    path = servers_path(cfg, version_id)
    root = _read_root(path)
    servers = root["servers"]
    if not 0 <= index < len(servers):
        raise ServerError("找不到这个服务器，列表可能刚被游戏改过")
    entry = servers[index]
    if name is not None:
        entry["name"] = _check_name(name)
    if ip is not None:
        host, port = _check_ip(ip)
        entry["ip"] = join_address(host, port)
    _save_root(path, root)
    return listing(cfg, version_id)


def remove(cfg: Config, version_id: str, index: int) -> dict:
    path = servers_path(cfg, version_id)
    root = _read_root(path)
    servers = root["servers"]
    if not 0 <= index < len(servers):
        raise ServerError("找不到这个服务器，列表可能刚被游戏改过")
    del servers[index]
    _save_root(path, root)
    return listing(cfg, version_id)


# ---------------------------------------------------------------- 状态查询

def _varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 32
    out = bytearray()
    while True:
        chunk = value & 0x7F
        value >>= 7
        if value:
            out.append(chunk | 0x80)
        else:
            out.append(chunk)
            return bytes(out)


def _read_varint(stream) -> int:
    result = 0
    for shift in range(0, 35, 7):
        chunk = stream.read(1)
        if not chunk:
            raise ServerError("服务器提前断开了连接")
        byte = chunk[0]
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result
    raise ServerError("VarInt 太长了，不像 Minecraft 的响应")


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return _varint(len(encoded)) + encoded


def _frame(payload: bytes) -> bytes:
    return _varint(len(payload)) + payload


def _handshake(host: str, port: int) -> bytes:
    payload = b"\x00" + _varint(PROTOCOL_VERSION) + _string(host)
    payload += struct.pack(">H", port) + _varint(1)
    return _frame(payload)


def _status_request() -> bytes:
    return _frame(b"\x00")


def flatten_chat(value) -> str:
    """MOTD 可能是字符串，也可能是 chat component，拍平成一行文字。"""
    if isinstance(value, str):
        text = value
    elif isinstance(value, list):
        text = "".join(flatten_chat(item) for item in value)
    elif isinstance(value, dict):
        parts = []
        if isinstance(value.get("text"), str):
            parts.append(value["text"])
        elif isinstance(value.get("translate"), str):
            parts.append(value["translate"])
        extra = value.get("extra")
        if isinstance(extra, list):
            parts.append("".join(flatten_chat(item) for item in extra))
        text = "".join(parts)
    else:
        text = ""
    return _strip_codes(text)


def _strip_codes(text: str) -> str:
    """去掉 §a 这类颜色代码，界面上不显示乱码。"""
    out = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\u00a7" and index + 1 < len(text):
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _empty_status(error: str) -> dict:
    return {"online": False, "error": error, "latency_ms": None,
            "players": {"online": 0, "max": 0}, "version": "", "motd": ""}


def status(host: str, port: int = DEFAULT_PORT, timeout: float = PING_TIMEOUT) -> dict:
    """Server List Ping。失败只返回 online=False，不抛异常——列表里一格挂了不该拖垮整页。"""
    host = (host or "").strip()
    if not host:
        return _empty_status("地址是空的")
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_handshake(host, port) + _status_request())
            stream = sock.makefile("rb")
            length = _read_varint(stream)
            if not 0 < length <= 4 * 1024 * 1024:
                return _empty_status("响应长度不合理")
            body = stream.read(length)
    except (OSError, ServerError) as exc:
        return _empty_status(str(exc) or "连不上")
    latency = int((time.monotonic() - started) * 1000)

    try:
        reader = io.BytesIO(body)
        packet_id = _read_varint(reader)
        if packet_id != 0:
            return _empty_status("不是状态响应")
        size = _read_varint(reader)
        payload = json.loads(reader.read(size).decode("utf-8", "replace"))
    except (ServerError, ValueError) as exc:
        return _empty_status(f"响应解析失败：{exc}")

    players = payload.get("players") or {}
    version = payload.get("version") or {}
    return {
        "online": True,
        "error": "",
        "latency_ms": latency,
        "players": {
            "online": int(players.get("online") or 0),
            "max": int(players.get("max") or 0),
        },
        "version": str(version.get("name") or ""),
        "motd": flatten_chat(payload.get("description")),
    }


def ping_servers(servers: Iterable[dict], timeout: float = PING_TIMEOUT,
                 workers: int = 8) -> list[dict]:
    """并发查一批服务器的状态，顺序跟输入一致。"""
    items = list(servers)
    if not items:
        return []

    def probe(item: dict) -> dict:
        return status(item.get("host", ""), int(item.get("port") or DEFAULT_PORT), timeout)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
        return list(pool.map(probe, items))
