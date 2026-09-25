#!/bin/bash
set -eu
mkdir -p "$ROOTFS/.temp_assets/calamares"
cp -a ./assets/calamares/. "$ROOTFS/.temp_assets/calamares/"
mkdir -p "$ROOTFS/.temp_assets/server"
cp -a ./assets/server/. "$ROOTFS/.temp_assets/server/"
