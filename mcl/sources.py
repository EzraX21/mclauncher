"""下载源：官方，或 PCL 同款的 BMCLAPI / mcimirror 镜像。

PCL 的做法（Modules/Minecraft/ModDownload.vb）是把官方 URL 按类型换成镜像：
- 元数据 / client jar：换域名，路径不变        -> https://bmclapi2.bangbang93.com/...
- 库：路径前面加 /maven（或 /libraries）        -> https://bmclapi2.bangbang93.com/maven/...
- 资源对象：路径前面加 /assets                 -> https://bmclapi2.bangbang93.com/assets/ab/abcd...
- Fabric meta：换成 /fabric-meta 前缀
- 模组：api.modrinth.com -> mod.mcimirror.top/modrinth，cdn.modrinth.com -> mod.mcimirror.top

这里按同样的规则生成候选列表，按顺序尝试，失败了就换下一个。
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit, urlunsplit

MIRROR_BASE = "https://bmclapi2.bangbang93.com"
MOD_MIRROR = "https://mod.mcimirror.top"

OFFICIAL_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
OFFICIAL_HOSTS = {
    "piston-meta.mojang.com",
    "piston-data.mojang.com",
    "launcher.mojang.com",
    "launchermeta.mojang.com",
    "libraries.minecraft.net",
    "resources.download.minecraft.net",
}
MODES = ("auto", "official", "custom")


def normalize_mode(mode: Optional[str]) -> str:
    mode = (mode or "auto").lower()
    if mode.startswith("custom:") and len(mode) > 7:
        return "custom"
    return mode if mode in MODES else "auto"


def custom_base(mode: str) -> str:
    if (mode or "").startswith("custom:"):
        return mode[7:].strip().rstrip("/")
    return ""


def _mirror_base(mode: str) -> str:
    if normalize_mode(mode) == "custom":
        return custom_base(mode)
    return MIRROR_BASE


def _swap_host(url: str, base: str, prefix: str = "") -> str:
    parts = urlsplit(url)
    base_parts = urlsplit(base)
    base_path = base_parts.path.rstrip("/")
    return urlunsplit(("https", base_parts.netloc, base_path + prefix + parts.path,
                       parts.query, ""))


def _rank(official: str, mirrors: list[str], mode: str) -> list[str]:
    if normalize_mode(mode) == "official":
        return [official]
    ordered = [url for url in mirrors if url] + [official]
    return list(dict.fromkeys(ordered))


def manifest_candidates(mode: str = "auto") -> list[str]:
    base = _mirror_base(mode)
    if not base:
        return [OFFICIAL_MANIFEST]
    if normalize_mode(mode) == "custom":
        mirrors = [f"{base}/version_manifest_v2.json",
                   f"{base}/mc/game/version_manifest_v2.json"]
    else:
        mirrors = [f"{base}/mc/game/version_manifest_v2.json"]
    return _rank(OFFICIAL_MANIFEST, mirrors, mode)


def meta_candidates(url: str, mode: str = "auto") -> list[str]:
    """版本 JSON、client jar、日志配置：换域名即可。"""
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    base = _mirror_base(mode)
    if not base:
        return [url]
    return _rank(url, [_swap_host(url, base)], mode)


def library_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    base = _mirror_base(mode)
    if not base:
        return [url]
    return _rank(url, [
        _swap_host(url, base, "/maven"),
        _swap_host(url, base, "/libraries"),
    ], mode)


def asset_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    base = _mirror_base(mode)
    if not base:
        return [url]
    return _rank(url, [_swap_host(url, base, "/assets")], mode)


def java_index_candidates(mode: str = "auto") -> list[str]:
    official = ("https://launchermeta.mojang.com/v1/products/java-runtime/"
                "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json")
    base = _mirror_base(mode)
    if not base:
        return [official]
    return _rank(official, [f"{base}/v1/products/java-runtime/"
                            "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"], mode)


def java_file_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    base = _mirror_base(mode)
    if not base:
        return [url]
    return _rank(url, [_swap_host(url, base)], mode)


def fabric_meta_candidates(url: str, mode: str = "auto") -> list[str]:
    if "meta.fabricmc.net" not in url:
        return [url]
    base = _mirror_base(mode)
    if not base:
        return [url]
    mirrored = url.replace("https://meta.fabricmc.net", f"{base}/fabric-meta", 1)
    return _rank(url, [mirrored], mode)


def modrinth_candidates(url: str, mode: str = "auto") -> list[str]:
    if "modrinth.com" not in url:
        return [url]
    if normalize_mode(mode) == "custom":
        return [url]
    mirrored = url.replace("https://api.modrinth.com", f"{MOD_MIRROR}/modrinth", 1) \
                  .replace("https://cdn.modrinth.com", MOD_MIRROR, 1) \
                  .replace("https://staging-api.modrinth.com", f"{MOD_MIRROR}/modrinth", 1)
    return _rank(url, [mirrored], mode)


def describe(mode: str) -> str:
    normal = normalize_mode(mode)
    if normal == "official":
        return "官方源"
    if normal == "custom":
        base = custom_base(mode) or "（未配置 URL）"
        return f"自定义镜像 {base} 优先，失败回退官方"
    return "BMCLAPI 镜像优先，失败回退官方"
