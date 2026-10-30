<p align="center">
  <img src="gui/assets/mcl.png" width="96" alt="MCL"/>
</p>

<h1 align="center">MCL · mclauncher</h1>

<p align="center">A Minecraft: Java Edition launcher with a GUI-first interface and a TUI mode. Vanilla installs, loaders, mods/modpacks, shaders, and launching.</p>

<p align="center">
  <a href="https://github.com/EzraX21/mclauncher/releases"><img src="https://img.shields.io/github/v/release/EzraX21/mclauncher?style=flat-square" alt="Release"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue?style=flat-square" alt="License"/></a>
  <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey?style=flat-square" alt="Platform"/>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square" alt="Python"/>
</p>

<p align="center">
  <strong>English</strong> | <a href="./README.md">简体中文</a>
</p>

---

## Table of Contents

- [Status](#status)
- [Features](#features)
- [Screenshots](#screenshots)
- [Installation](#installation)
- [Running](#running)
- [GUI](#gui)
- [TUI](#tui)
- [Microsoft login](#microsoft-login)
- [Modpacks](#modpacks)
- [Resources](#resources)
- [Crash analysis](#crash-analysis)
- [CLI](#cli)
- [Configuration](#configuration)
- [Download sources](#download-sources)
- [CurseForge (optional)](#curseforge-optional)
- [Naming and releases](#naming-and-releases)
- [Packaging](#packaging)
- [Project layout](#project-layout)
- [Tests](#tests)
- [Known limitations](#known-limitations)
- [Privacy](#privacy)
- [License](#license)

## Status

Current version: **v3.7.0**

| Status | Area |
| --- | --- |
| ✅ Done | Vanilla downloads, version management, Fabric/Quilt/Forge/NeoForge, mod search/install, modpacks, shaders/resource packs, crash analysis, Java runtimes, GUI (default), TUI (feature), themes, native windows, Linux/Windows packaging |
| 🚧 External | **Microsoft login**: fully implemented; the built-in Azure app is waiting for Mojang's allowlist. Until approved, Minecraft returns `Invalid app registration` |
| 🚧 Unverified | **CurseForge modpacks**: download path implemented, requires an API key; no real-pack regression yet |
| 🚧 Not published | **AUR**: PKGBUILD for `mcl-launcher` is ready, first submission pending; the AUR CI step stays red until secrets are configured (`continue-on-error`) |
| 📋 Planned | Server list / quick join, launcher auto-update, Java management UI, maps/datapacks |

## Features

| Module | What it does |
| --- | --- |
| Versions | Installed versions (loader, Java, mod count), launch / add loader / open folder / delete |
| Install | Mojang version manifest, live filter, optional assets, progress + log + cancel |
| Mods | Modrinth / CurseForge search and install with required dependencies; local mods enable/disable/delete |
| Modpacks | Modrinth `.mrpack` and CurseForge zips; installs vanilla + loader, copies overrides, creates an isolated instance |
| Resources | Shaders and resource packs into `shaderpacks/` / `resourcepacks/` |
| Crash analysis | Reads crash reports / latest.log and explains Java, memory, missing deps, Mixin conflicts, etc. |
| Accounts | Offline + Microsoft device-code login, local token cache with refresh |
| Java | Picks the exact major version; downloads the matching Mojang runtime instead of using a newer Java |
| GUI | **Default entry point**: native window (WebKitGTK on Linux / WebView2 on Windows), light/dark/system themes |
| TUI | **Feature entry point**: full-screen terminal UI for terminal/keyboard workflows; launching still needs a graphical environment |

## Screenshots

| Light | Dark |
| --- | --- |
| ![Versions](docs/gui-versions.png) | ![Dark theme](docs/gui-dark.png) |

| Install | Mods / modpacks |
| --- | --- |
| ![Install](docs/gui-install.png) | ![Mods](docs/gui-mods.png) |

| Resources | Settings / Microsoft account |
| --- | --- |
| ![Resources](docs/gui-resources.png) | ![Settings](docs/gui-settings.png) |

## Installation

### Download a release

Grab the right file from [Releases](https://github.com/EzraX21/mclauncher/releases):

| Platform | File |
| --- | --- |
| Windows | `mcl-<ver>-windows-x64-setup.exe` (installer) or `mcl-<ver>-windows-x64-portable.zip` (extract and run) |
| Debian / Ubuntu | `mcl-<ver>-linux-x64.deb` |
| Fedora / RHEL | `mcl-<ver>-linux-x64.rpm` |
| Arch | `mcl-<ver>-linux-x64.pkg.tar.zst` |
| Linux portable | `mcl-<ver>-linux-x64-portable.tar.gz` (bundled deps, run `./mcl.sh`) |

Each release ships `SHA256SUMS.txt`. The package name is `mcl-launcher`; the installed command is `mcl`.

```bash
# Debian / Ubuntu
sudo dpkg -i mcl-<ver>-linux-x64.deb
# Fedora / RHEL
sudo rpm -i mcl-<ver>-linux-x64.rpm
# Arch
sudo pacman -U mcl-<ver>-linux-x64.pkg.tar.zst
```

The Windows installer includes `mclw.exe` (native window, no console) and `mcl.exe` (CLI/TUI).
The installer is unsigned; on SmartScreen choose "More info → Run anyway".

### Desktop entry

Linux packages (deb/rpm/Arch) install the menu entry and icon automatically. For pip/uv
or the portable build, the first `mcl` launch adds it; you can also do it manually:

```bash
mcl desktop          # install ~/.local/share/applications/mcl.desktop
mcl desktop remove   # remove it
```

If your launcher still cannot find MCL, log out/in or restart the launcher to refresh its cache.

### From source

```bash
git clone https://github.com/EzraX21/mclauncher
cd mclauncher
pipx install ".[cli,gui]"     # or: uv tool install ".[cli,gui]"
mcl
```

`[gui]` pulls pywebview (native window); `[cli]` pulls questionary for `mcl --cli`.
For TUI only, install `.[cli]` and run `mcl tui`; the default `mcl` command needs `[gui]`. For development, `./run.sh` creates a `.venv` for you.

## Running

```bash
mcl            # default: GUI
mcl tui        # full-screen TUI (manage from a terminal; GUI still required to play)
mcl gui        # explicitly open the GUI
mcl --cli      # questionary text menu
```

## GUI

The GUI is the default: running `mcl` opens a **desktop window** (same as `mcl gui`),
not a browser tab:

- Linux: GTK + WebKitGTK (`webkit2gtk-4.1`, `python-gobject`)
- Windows: WebView2 (bundled with Windows 10/11); `mclw.exe` in the installer opens it directly
- The Linux desktop entry runs `mcl gui`

```bash
# Arch
sudo pacman -S webkit2gtk-4.1 python-gobject
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-webkit2-4.1

mcl gui              # native window (default)
mcl gui --web        # browser
mcl gui --electron   # Electron during development
mcl gui --web --no-browser --port 8765   # local server only
```

Themes: **light / dark / follow system**, applied instantly and persisted. The backend is
`mcl/webui.py`, bound to `127.0.0.1` only; the frontend lives in `gui/` (TypeScript, esbuild).

**Development**

```bash
cd gui
npm install --include=dev    # needed if npm is configured with omit=dev
npm run build
cd ..
mcl gui --web
```

Electron window:

```bash
mcl gui --web --no-browser --port 8765 &
MCL_GUI_URL=http://127.0.0.1:8765/ npm --prefix gui start
```

## TUI

The TUI is a first-class alternative, not the default: run `mcl tui` explicitly. It is for
terminal/keyboard-oriented workflows and can install versions, loaders and mods, but
**launching the game still requires a graphical environment**. `mcl` does not fall back
silently; it reports why the window could not open. Four tabs: Versions, Install, Mods, Settings.

- `Tab` switches tabs, `q` quits, `ctrl+r` refreshes, `ctrl+s` saves settings
- Logs are collapsed by default and expand when an install or launch starts
- Mods tab: Modrinth or CurseForge source, local mods enable/disable/delete

## Microsoft login

Implemented in both CLI and GUI. **The built-in Azure app is used by default; users do not
need to register one:**

```bash
mcl login       # prints microsoft.com/link and a device code
mcl account
mcl logout
```

In the GUI: Settings → Microsoft account → sign in; the device code is shown in a dialog.

> Status: since 2026 Mojang requires third-party launcher client IDs to be on an allowlist.
> The built-in app has been submitted. Until it is approved, `login_with_xbox` returns
> `Invalid app registration`; MCL shows a clear message and offline mode keeps working.

Using your own Azure app (also subject to Mojang's allowlist):

1. Azure Portal → Microsoft Entra ID → App registrations → New registration
2. Account type: personal Microsoft accounts only; leave redirect URI empty
3. Authentication → Allow public client flows → Yes
4. Copy the Application (client) ID and run `mcl config set ms_client_id <id>`

No client secret or API permissions are required. Tokens are stored in
`~/.config/mcl/accounts.json` (0600), refreshed automatically, with offline fallback.

## Modpacks

Supports Modrinth `.mrpack` and CurseForge zips:

```bash
mcl modpack info Fabulously.Optimized.mrpack
mcl modpack install Fabulously.Optimized.mrpack --name "FO 1.20.1"
mcl launch "FO 1.20.1"
```

The installer adds vanilla if needed, installs the matching loader, downloads mods
(sha1-verified), copies `overrides/` and `client-overrides/`, and creates an isolated
instance. In the GUI, use Mods → Import modpack to upload a file.

CurseForge modpacks need an API key (see below).

## Resources

```bash
mcl resources search shader complementary --version 1.20.1
mcl resources install shader complementary-reimagined --version 1.20.1
mcl resources list shader --version 1.20.1
mcl resources remove shader ComplementaryReimagined_r5.9.3.zip --version 1.20.1
```

Shaders go to `shaderpacks/`, resource packs to `resourcepacks/`. The GUI has a Resources tab.

## Crash analysis

```bash
mcl crash 1.20.1
```

Reads the newest `crash-reports/crash-*.txt` (or `logs/latest.log`) and matches Java
version errors, OOM, missing dependencies, duplicate mods, Mixin conflicts, OpenGL and
permission problems, with suggested fixes. The GUI exposes it per version.

## CLI

```bash
mcl install 1.20.1                  # install vanilla
mcl install latest --no-assets -y
mcl versions                        # installed versions
mcl loaders fabric 1.20.1           # install Fabric
mcl loaders forge 1.20.1            # install Forge (official installer)
mcl loaders neoforge 1.21.1         # install NeoForge
mcl launch 1.20.1                   # launch
mcl launch 1.20.1 --dry-run         # print the command only
mcl launch 1.20.1 --offline         # force offline mode
mcl mods search sodium --version 1.20.1
mcl mods install sodium --version fabric-loader-0.20.1-1.20.1 -y
mcl modpack install pack.mrpack --name "My Pack"
mcl resources search shader complementary --version 1.20.1
mcl crash 1.20.1                    # analyze a crash
mcl java install 21                 # download a Java runtime
mcl login / mcl account / mcl logout
mcl desktop                         # install the Linux menu entry
mcl config                          # show config
mcl doctor --network                # environment check
```

Run `mcl <command> --help` for all options.

## Configuration

Paths:

- Linux: `$XDG_CONFIG_HOME/mcl` (default `~/.config/mcl`)
- Windows: `%APPDATA%\mcl`
- macOS: `~/Library/Application Support/mcl`

`config.json` can be edited with `mcl config set <key> <value>`:

| Key | Meaning |
| --- | --- |
| `game_dir` | Game directory, default `~/.minecraft` |
| `java_path` | Explicit Java; empty means auto-detect |
| `memory_mb` | Heap in MB, default 4096 |
| `username` | Offline username |
| `isolate_versions` | Per-version isolation, default on |
| `jobs` | Download concurrency, default 8 |
| `download_source` | `official` (default) / `auto` (BMCLAPI first) / `custom` |
| `mirror_url` | Custom BMCLAPI-compatible mirror base URL |
| `theme` | GUI theme: `light` / `dark` / `system` |
| `ms_client_id` | Override the built-in Azure client ID (optional) |
| `curseforge_api_key` | CurseForge API key (optional) |

Environment: `MCL_CONFIG` (config path override), `CURSEFORGE_API_KEY` (takes precedence).

## Download sources

Default `official` connects only to Mojang's CDN. Switch to `auto` for BMCLAPI-first with
official fallback:

```bash
mcl install 1.20.1 --source auto
mcl config set download_source auto
```

Mirrored: version manifest/JSON/client jar, libraries, asset objects, Java runtimes,
Fabric meta. Modrinth API/CDN uses `mod.mcimirror.top`. Quilt always uses the official source.

### Custom mirror

If you have a **BMCLAPI-compatible** mirror (same path layout), point MCL at its base URL:

```bash
mcl config set download_source custom
mcl config set mirror_url https://mirror.example.com

# or for a single command
mcl install 1.20.1 --mirror https://mirror.example.com
```

Only Mojang resources (manifest/JSON/jars/libraries/assets/Java/Fabric meta) are rewritten;
Modrinth still uses the official API/CDN. Failed mirror requests fall back to Mojang.
The GUI and TUI settings also expose a custom mirror option and URL field.

## CurseForge (optional)

Modrinth is the default. CurseForge requires your own API key (application reviewed by
Overwolf); MCL does not ship or apply for one.

1. Sign in to CurseForge (Overwolf)
2. Submit the official form: <https://support.curseforge.com/support/solutions/articles/9000208346-about-the-curseforge-api-and-how-to-apply-for-a-key>
3. The key arrives by email after approval

```bash
export CURSEFORGE_API_KEY=your-key
mcl config set curseforge_api_key your-key
```

You can also paste it in the TUI under Settings → CurseForge key. `mcl doctor` reports it.
Some authors disable third-party downloads; those files cannot be fetched and MCL says so.

## Naming and releases

| Layer | Name |
| --- | --- |
| Product / full name | MCL / mclauncher |
| Commands | `mcl` / `mcl-tui` |
| Python package / distribution | `mcl` / `mcl-launcher` |
| Config directory | `~/.config/mcl` |

- Versions: `v3.7.0`, `v3.7.0-beta.1`, `v3.7.0-rc.1` (PEP 440 in code: `3.7.0b1`)
- Artifacts: `mcl-<ver>-<platform>-<arch>[-variant].<ext>`; deb/rpm/Arch filenames follow
  the same pattern; wheels keep PEP 427
- Every release includes `SHA256SUMS.txt`
- beta/rc tags become GitHub Pre-releases and skip AUR

```bash
python3 packaging/release.py          # interactive version prompt
python3 packaging/release.py --version 3.7.0 --commit
```

## Packaging

```bash
./packaging/build_linux.sh             # deb / rpm / Arch / wheel / source / portable tar.gz
powershell -File packaging/build_windows.ps1   # setup.exe + portable.zip
```

CI (`.github/workflows/release.yml`) builds Linux + Windows on `v*` tags and publishes the
release. AUR updates automatically once secrets are configured; the first `mcl-launcher`
submission still has to be created on the AUR website.

### R2 direct downloads (optional)

After a Release is published, an extra `r2` job syncs every asset to Cloudflare R2 so the
website can serve downloads from your own domain:

```
releases/<tag>/<file>     # versioned, immutable cache
latest/<file>             # copy of the latest release
latest.json               # tag + name/size/sha256
```

Configure repository secrets:

| Secret | Value |
| --- | --- |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API token Access Key ID |
| `R2_SECRET_ACCESS_KEY` | R2 API token Secret Access Key |
| `R2_BUCKET` | bucket name |

Create the token under R2 → Manage R2 API Tokens with Object Read & Write scoped to the
bucket, then attach a custom domain to it. Without secrets the job is skipped and the
Release is unaffected. Set `downloadBase` in `MCL-web/public/config.js` on the site side.

## Project layout

```
mclauncher/
├── mcl/                  Python package
│   ├── cli.py            subcommands; no args -> GUI, TUI fallback
│   ├── tui/              Textual TUI
│   ├── gui_cmd.py        GUI launcher (pywebview / Electron / browser)
│   ├── webui.py          local HTTP + JSON API for the GUI
│   ├── auth.py           Microsoft device-code login
│   ├── modpacks.py       modpack import
│   ├── resources.py      shaders / resource packs
│   ├── crash.py          crash log analysis
│   ├── versions.py       inheritsFrom merging / version scan
│   ├── launch.py         launch args / classpath / natives
│   ├── installer.py      download plan and execution
│   ├── net.py            concurrent downloads / checksums / resume
│   ├── java.py           Java detection and Mojang runtimes
│   ├── modrinth.py       Modrinth API
│   ├── curseforge.py     CurseForge API
│   └── ...
├── gui/                  TypeScript frontend (esbuild)
├── docs/                 README screenshots
├── tests/                105 tests
├── packaging/            deb/rpm/Arch, Windows, macOS, AUR, release helper
└── pyproject.toml
```

## Tests

```bash
python -m unittest discover -s tests -v
```

105 tests covering rules, download plans, version merging, launch arguments, Java, mods,
modpacks, resources, crash analysis, Microsoft auth, TUI and GUI API; no network needed.

## Known limitations

- Microsoft login waits for Mojang's allowlist; until then `Invalid app registration`
- CurseForge modpacks need a key and have not been regression-tested on a real pack
- The Windows installer is unsigned, so SmartScreen warns
- macOS only has a manual build script; releases do not ship a dmg, and the GUI falls back to a browser
- AUR has not been submitted yet
- Resources cover shaders/resource packs only; maps and datapacks are not implemented
- Server list, auto-update and a Java management UI are not implemented

## Privacy

No telemetry, no data collection. Login happens on Microsoft's pages; MCL never sees your
password. Account tokens stay local (0600). See [PRIVACY.md](PRIVACY.md).

## License

GNU General Public License v3.0 **or later** (GPL-3.0-or-later). Full text in [LICENSE](LICENSE).
Copyright (C) 2026 mcl contributors.
