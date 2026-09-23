#!/bin/bash
set -eu
mkdir -p "$ROOTFS/.temp_assets/calamares"
cp -a ./assets/calamares/. "$ROOTFS/.temp_assets/calamares/"
