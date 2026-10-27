name: mcl-launcher
arch: amd64
platform: linux
version: @VERSION@
section: games
priority: optional
maintainer: mcl contributors
vendor: mcl
homepage: https://github.com/ezrax21/mclauncher
license: GPL-3.0-or-later
description: |
  Minecraft launcher with a full-screen TUI.
  Download vanilla versions, install Fabric/Quilt/Forge/NeoForge,
  manage mods from Modrinth, and launch the game.
contents:
  - src: build/vendor
    dst: /usr/lib/mcl
  - src: packaging/mcl.sh
    dst: /usr/bin/mcl
    file_info:
      mode: 0755
  - src: packaging/mcl.desktop
    dst: /usr/share/applications/mcl.desktop
  - src: gui/assets/mcl.png
    dst: /usr/share/icons/hicolor/256x256/apps/mcl.png
  - src: LICENSE
    dst: /usr/share/licenses/mcl-launcher/LICENSE
overrides:
  deb:
    depends:
      - python3 (>= 3.10)
      - python3-gi
      - gir1.2-webkit2-4.1
  rpm:
    depends:
      - python3 >= 3.10
      - python3-gobject
      - webkit2gtk4.1
  archlinux:
    depends:
      - python>=3.10
      - python-gobject
      - webkit2gtk-4.1
