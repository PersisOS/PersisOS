#!/bin/bash
set -e
echo 'Installing Plasma Theme and Wallpapers'
cp -a /.temp_assets/persisos-plasma-theme/usr/share/plasma/. /usr/share/plasma/
mkdir -p /usr/share/wallpapers
cp -a /.temp_assets/persisos-plasma-theme/usr/share/wallpapers/. /usr/share/wallpapers/
