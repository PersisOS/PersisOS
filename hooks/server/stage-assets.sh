#!/bin/bash
set -eu
mkdir -p "$ROOTFS/.temp_assets/server"
cp -a ./assets/server/. "$ROOTFS/.temp_assets/server/"
cp -a ./assets/fastfetch "$ROOTFS/.temp_assets/"
