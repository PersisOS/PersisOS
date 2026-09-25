#!/bin/bash
set -eu
mkdir -p "$ROOTFS/.temp_assets/server"
cp -a ./assets/server/. "$ROOTFS/.temp_assets/server/"
