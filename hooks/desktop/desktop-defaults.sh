#!/bin/bash
set -e
echo 'Applying desktop, xdg and SDDM config'
cp -a /.temp_assets/persisos-plasma-theme/etc/xdg/. /etc/xdg/
mkdir -p /etc/sddm.conf.d /etc/skel/Desktop
cp -a /.temp_assets/persisos-plasma-theme/etc/sddm.conf.d/. /etc/sddm.conf.d/
cp -a /.temp_assets/persisos-plasma-theme/etc/skel/Desktop/. /etc/skel/Desktop/
chmod 0755 /etc/skel/Desktop/*.desktop
live_home=$(getent passwd user | cut -d: -f6)
if [ -n "$live_home" ]; then
    install -d -m 0755 -o user -g user "$live_home/Desktop"
    cp -a /etc/skel/Desktop/. "$live_home/Desktop/"
    install -m 0755 -o user -g user /.temp_assets/persisos-plasma-theme/usr/share/applications/install-persisos.desktop "$live_home/Desktop/Install PersisOS.desktop"
    chown -R user:user "$live_home/Desktop"
fi
