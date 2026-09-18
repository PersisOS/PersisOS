#!/bin/bash
set -e
mkdir -p "$ROOTFS/.temp_assets"
cp -r ./assets/persisos-plasma-theme "$ROOTFS/.temp_assets/"
cp -a ./assets/wallpapers "$ROOTFS/.temp_assets/persisos-plasma-theme/usr/share/"
install -Dm 0644 ./persisos.svg "$ROOTFS/.temp_assets/persisos-plasma-theme/usr/share/icons/hicolor/scalable/apps/persisos.svg"
