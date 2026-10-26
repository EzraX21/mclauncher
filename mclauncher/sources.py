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
MODES = ("auto", "official")


def normalize_mode(mode: Optional[str]) -> str:
    mode = (mode or "auto").lower()
    return mode if mode in MODES else "auto"


def _swap_host(url: str, base: str, prefix: str = "") -> str:
    parts = urlsplit(url)
    return urlunsplit(("https", urlsplit(base).netloc, prefix + parts.path, parts.query, ""))


def _rank(official: str, mirrors: list[str], mode: str) -> list[str]:
    if normalize_mode(mode) == "official":
        return [official]
    ordered = [url for url in mirrors if url] + [official]
    return list(dict.fromkeys(ordered))


def manifest_candidates(mode: str = "auto") -> list[str]:
    return _rank(OFFICIAL_MANIFEST, [f"{MIRROR_BASE}/mc/game/version_manifest_v2.json"], mode)


def meta_candidates(url: str, mode: str = "auto") -> list[str]:
    """版本 JSON、client jar、日志配置：换域名即可。"""
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    return _rank(url, [_swap_host(url, MIRROR_BASE)], mode)


def library_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    return _rank(url, [
        _swap_host(url, MIRROR_BASE, "/maven"),
        _swap_host(url, MIRROR_BASE, "/libraries"),
    ], mode)


def asset_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    return _rank(url, [_swap_host(url, MIRROR_BASE, "/assets")], mode)


def java_index_candidates(mode: str = "auto") -> list[str]:
    official = ("https://launchermeta.mojang.com/v1/products/java-runtime/"
                "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json")
    return _rank(official, [f"{MIRROR_BASE}/v1/products/java-runtime/"
                            "2ec0cc96c44e5a76b9c8b7c39df7210883d12871/all.json"], mode)


def java_file_candidates(url: str, mode: str = "auto") -> list[str]:
    if urlsplit(url).netloc not in OFFICIAL_HOSTS:
        return [url]
    return _rank(url, [_swap_host(url, MIRROR_BASE)], mode)


def fabric_meta_candidates(url: str, mode: str = "auto") -> list[str]:
    if "meta.fabricmc.net" not in url:
        return [url]
    mirrored = url.replace("https://meta.fabricmc.net", f"{MIRROR_BASE}/fabric-meta", 1)
    return _rank(url, [mirrored], mode)


def modrinth_candidates(url: str, mode: str = "auto") -> list[str]:
    if "modrinth.com" not in url:
        return [url]
    mirrored = url.replace("https://api.modrinth.com", f"{MOD_MIRROR}/modrinth", 1) \
                  .replace("https://cdn.modrinth.com", MOD_MIRROR, 1) \
                  .replace("https://staging-api.modrinth.com", f"{MOD_MIRROR}/modrinth", 1)
    return _rank(url, [mirrored], mode)


def describe(mode: str) -> str:
    return {
        "official": "官方源",
        "auto": "BMCLAPI 镜像优先，失败回退官方",
    }[normalize_mode(mode)]
