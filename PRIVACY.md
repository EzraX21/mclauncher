# MCL 隐私政策 / Privacy Policy

MCL（mclauncher）是一个开源的 Minecraft: Java Edition 启动器。

## 收集什么

- **不收集**任何个人数据，没有遥测、广告或统计上报。
- 登录微软账号时，MCL 只在本机完成 OAuth 2.0 设备代码流程，并调用 Xbox Live、XSTS 和 Minecraft Services 获取玩家档案（游戏名、UUID、皮肤）用于启动游戏。
- 密码不会经过 MCL；登录在微软自己的页面完成。

## 本地保存什么

- `~/.config/mcl/config.json`：启动器设置（游戏目录、内存、下载源等）。
- `~/.config/mcl/accounts.json`：微软登录 token（权限 0600），仅用于本机启动游戏。
- 游戏版本、模组、日志保存在你选择的游戏目录。

## 第三方服务

- Microsoft 登录：https://login.microsoftonline.com
- Xbox Live / XSTS：https://xboxlive.com
- Minecraft Services：https://api.minecraftservices.com
- Modrinth / CurseForge / BMCLAPI：仅在下载模组或资源时访问

## 删除数据

退出登录会删除 `accounts.json`；删除配置目录 `~/.config/mcl` 即可清除全部启动器数据。

## 联系

问题请开 issue：https://github.com/EzraX21/mclauncher/issues

---

MCL is an open-source Minecraft: Java Edition launcher. It collects no personal
data and has no telemetry. Account tokens are stored locally with 0600
permissions and are only used to launch the game. Authentication happens on
Microsoft's own pages; MCL never sees your password.
