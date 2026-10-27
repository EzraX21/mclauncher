"""微软正版登录：设备代码流 -> Xbox Live -> XSTS -> Minecraft。

只依赖标准库；token 缓存在 ~/.config/mcl/accounts.json。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuidlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .platforms import config_dir

DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
USER_AGENT = "MCL/1.0"
DEFAULT_CLIENT_ID = "7808d7d9-1895-4b8c-b915-b5fb1a600dd7"


def client_id_for(cfg) -> str:
    """用户自己填的优先，否则用内置的 MCL Azure 应用。"""
    return (getattr(cfg, "ms_client_id", "") or DEFAULT_CLIENT_ID).strip()


class AuthError(RuntimeError):
    """登录失败，message 直接给用户看。"""


def friendly(message: str) -> str:
    if "AADSTS700016" in message:
        return "client id 不对，或者 Azure 应用的账户类型不是「个人 Microsoft 账户」"
    if "AADSTS7000218" in message:
        return "Azure 应用没开「允许公共客户端流」：身份验证 → 允许公共客户端流 → 是"
    if "AADSTS65001" in message:
        return "这个 Azure 应用没有获得授权，检查 API 权限或重新登录"
    return message


@dataclass
class Account:
    name: str
    uuid: str
    access_token: str
    refresh_token: str
    expires_at: float
    client_id: str = ""

    @property
    def expires_in(self) -> int:
        return max(0, int(self.expires_at - time.time()))

    def public(self) -> dict:
        return {"name": self.name, "uuid": self.uuid, "expires_in": self.expires_in}


def accounts_path() -> Path:
    return config_dir() / "accounts.json"


def _post_json(url: str, payload: dict, token: Optional[str] = None) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}
        message = data.get("error_description") or data.get("Message") or body[:300]
        raise AuthError(friendly(message)) from exc
    except urllib.error.URLError as exc:
        raise AuthError(f"连不上微软登录服务：{exc.reason}") from exc


def _post_form(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        error = data.get("error", "")
        if error in ("authorization_pending", "slow_down", "expired_token",
                     "authorization_declined", "bad_verification_code"):
            return {"error": error, **data}
        raise AuthError(friendly(data.get("error_description") or raw[:300])) from exc
    except urllib.error.URLError as exc:
        raise AuthError(f"连不上微软登录服务：{exc.reason}") from exc


def start_device_code(client_id: str) -> dict:
    if not client_id:
        raise AuthError("还没配置微软 client id")
    data = _post_form(DEVICE_CODE_URL, {"client_id": client_id, "scope": SCOPE})
    if "device_code" not in data:
        raise AuthError(friendly(data.get("error_description") or "微软没有返回设备代码"))
    return data


def poll_device_code(client_id: str, device: dict,
                     cancel=None,
                     on_status: Optional[Callable[[str], None]] = None) -> dict:
    interval = max(1, int(device.get("interval", 5)))
    deadline = time.time() + int(device.get("expires_in", 900))
    while time.time() < deadline:
        if cancel is not None and cancel.is_set():
            raise AuthError("已取消登录")
        time.sleep(interval)
        result = _post_form(TOKEN_URL, {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device["device_code"],
        })
        error = result.get("error")
        if error == "authorization_pending":
            if on_status:
                on_status("等待浏览器里完成登录 …")
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise AuthError("设备代码过期了，重新登录一次")
        if error == "authorization_declined":
            raise AuthError("登录被拒绝")
        if error:
            raise AuthError(result.get("error_description") or error)
        return result
    raise AuthError("登录超时，重新登录一次")


def _xbl(ms_access_token: str) -> tuple[str, str]:
    data = _post_json(XBL_URL, {
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={ms_access_token}",
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    })
    token = data.get("Token")
    claims = data.get("DisplayClaims", {}).get("xui") or [{}]
    uhs = claims[0].get("uhs")
    if not token or not uhs:
        raise AuthError("Xbox Live 认证失败")
    return token, uhs


def _xsts(xbl_token: str) -> tuple[str, str]:
    try:
        data = _post_json(XSTS_URL, {
            "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl_token]},
            "RelyingParty": "rp://api.minecraftservices.com/",
            "TokenType": "JWT",
        })
    except AuthError as exc:
        text = str(exc)
        if "2148916233" in text:
            raise AuthError("这个微软账号还没有 Xbox 档案：先打开 https://www.xbox.com 登录一次创建档案") from exc
        if "2148916238" in text:
            raise AuthError("这是儿童账号：需要家长在 https://family.microsoft.com 把你加入家庭并批准 Xbox Live") from exc
        if "2148916235" in text:
            raise AuthError("这个账号所在地区不支持 Xbox Live") from exc
        raise
    token = data.get("Token")
    claims = data.get("DisplayClaims", {}).get("xui") or [{}]
    uhs = claims[0].get("uhs")
    if not token or not uhs:
        raise AuthError("XSTS 授权失败")
    return token, uhs


def _minecraft(xsts_token: str, uhs: str) -> dict:
    data = _post_json(MC_LOGIN_URL, {"identityToken": f"XBL3.0 x={uhs};{xsts_token}"})
    if "access_token" not in data:
        raise AuthError("Minecraft 登录失败")
    return data


def _profile(mc_token: str) -> dict:
    request = urllib.request.Request(MC_PROFILE_URL, headers={
        "Authorization": f"Bearer {mc_token}", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise AuthError("这个账号没有 Minecraft: Java Edition") from exc
        raise AuthError(f"读取 Minecraft 档案失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise AuthError(f"连不上 Minecraft 服务：{exc.reason}") from exc


def _chain(ms_access_token: str, refresh_token: str, client_id: str) -> Account:
    xbl_token, uhs = _xbl(ms_access_token)
    xsts_token, _ = _xsts(xbl_token)
    mc = _minecraft(xsts_token, uhs)
    profile = _profile(mc["access_token"])
    raw_uuid = profile.get("id", "")
    try:
        pretty_uuid = str(uuidlib.UUID(raw_uuid))
    except ValueError:
        pretty_uuid = raw_uuid
    return Account(
        name=profile.get("name", "Player"),
        uuid=pretty_uuid,
        access_token=mc["access_token"],
        refresh_token=refresh_token,
        expires_at=time.time() + int(mc.get("expires_in", 86400)) - 60,
        client_id=client_id,
    )


def login(client_id: str, on_code: Optional[Callable[[dict], None]] = None,
          on_status: Optional[Callable[[str], None]] = None,
          cancel=None) -> Account:
    device = start_device_code(client_id)
    if on_code:
        on_code(device)
    token = poll_device_code(client_id, device, cancel=cancel, on_status=on_status)
    account = _chain(token["access_token"], token.get("refresh_token", ""), client_id)
    save_account(account)
    return account


def refresh_account(account: Account, client_id: Optional[str] = None) -> Account:
    client = client_id or account.client_id
    if not client:
        raise AuthError("缺少 client id，无法刷新登录")
    if not account.refresh_token:
        raise AuthError("没有 refresh token，需要重新登录")
    data = _post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": client,
        "refresh_token": account.refresh_token,
        "scope": SCOPE,
    })
    if "access_token" not in data:
        raise AuthError(data.get("error_description") or "刷新登录失败")
    refreshed = _chain(data["access_token"], data.get("refresh_token", account.refresh_token), client)
    save_account(refreshed)
    return refreshed


def ensure_account(cfg) -> Optional[Account]:
    """返回可用的正版账号；过期就刷新，失败返回 None（调用方退回离线）。"""
    account = load_account()
    if account is None:
        return None
    if account.expires_at > time.time() + 120:
        return account
    try:
        return refresh_account(account, client_id_for(cfg) if not account.client_id else account.client_id)
    except AuthError:
        return None


def save_account(account: Account) -> None:
    path = accounts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(account), ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_account() -> Optional[Account]:
    path = accounts_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return Account(**{k: raw[k] for k in Account.__dataclass_fields__ if k in raw})
    except (OSError, json.JSONDecodeError, TypeError, KeyError):
        return None


def clear_account() -> None:
    try:
        accounts_path().unlink()
    except OSError:
        pass
