#!/bin/sh
# Build a pure-Python Debian 13 package; dependencies are resolved by APT.
set -eu
src=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
version=0.2.0~beta10
target=${1:-"$src/dist"}
mkdir -p "$target"
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT HUP INT TERM
install -d "$stage/DEBIAN" "$stage/usr/bin" "$stage/usr/lib/streamer-linux-bot" \
  "$stage/usr/share/applications" "$stage/usr/share/doc/streamer-linux-bot" \
  "$stage/usr/share/icons/hicolor/scalable/apps"
cp -R "$src/slbot" "$stage/usr/lib/streamer-linux-bot/"
find "$stage/usr/lib" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$stage/usr/lib" -type f -name '*.py[co]' -delete
install -m 0755 "$src/packaging/debian/launcher" "$stage/usr/bin/streamer-linux-bot"
install -m 0644 "$src/packaging/debian/streamer-linux-bot.desktop" "$stage/usr/share/applications/"
install -m 0644 "$src/packaging/debian/streamer-linux-bot.svg" "$stage/usr/share/icons/hicolor/scalable/apps/"
install -m 0644 "$src/README.md" "$stage/usr/share/doc/streamer-linux-bot/README.md"
cat > "$stage/DEBIAN/control" <<EOF
Package: streamer-linux-bot
Version: $version
Architecture: all
Section: video
Priority: optional
Maintainer: Streamer Linux Bot project <GaryQuinn08@users.noreply.github.com>
Depends: python3 (>= 3.12), python3-pyside6.qtwidgets, python3-aiohttp, libxcb-cursor0, qt6-qpa-plugins, qt6-svg-plugins
Recommends: qt6-wayland, pulseaudio-utils | pipewire-bin, espeak-ng, mpv
Homepage: https://github.com/GaryQuinn08/Streamer-Linux-Bot
Description: Desktop stream automation with local overlays
 Native Qt desktop app for OBS overlays, configurable gift alerts,
 and simulated events. Includes experimental TikTok LIVE inputs.
EOF
dpkg-deb --root-owner-group --build "$stage" "$target/streamer-linux-bot_${version}_all.deb"
