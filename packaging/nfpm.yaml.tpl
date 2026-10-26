name: mclauncher
arch: amd64
platform: linux
version: @VERSION@
section: games
priority: optional
maintainer: mclauncher contributors
vendor: mclauncher
homepage: https://github.com/ezrax21/mclauncher
license: GPL-3.0-or-later
description: |
  Minecraft launcher with a full-screen TUI.
  Download vanilla versions, install Fabric/Quilt/Forge/NeoForge,
  manage mods from Modrinth, and launch the game.
contents:
  - src: build/vendor
    dst: /usr/lib/mclauncher
  - src: packaging/mclauncher.sh
    dst: /usr/bin/mclauncher
    file_info:
      mode: 0755
  - src: packaging/mclauncher.desktop
    dst: /usr/share/applications/mclauncher.desktop
  - src: LICENSE
    dst: /usr/share/licenses/mclauncher/LICENSE
overrides:
  deb:
    depends:
      - python3 (>= 3.10)
  rpm:
    depends:
      - python3 >= 3.10
  archlinux:
    depends:
      - python>=3.10
