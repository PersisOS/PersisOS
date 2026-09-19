#!/bin/bash
set -e
# Autologin straight into the live desktop session. The Calamares installer
# copies the live squashfs (not this live-only hook), so this file never
# reaches an installed PersisOS system.
live_user=$(getent passwd user | cut -d: -f1)
if [ -z "$live_user" ]; then
    echo 'No live user found; skipping SDDM autologin'
    exit 0
fi
mkdir -p /etc/sddm.conf.d
cat > /etc/sddm.conf.d/zz-persisos-live-autologin.conf << EOF
[Autologin]
User=$live_user
Session=plasma
Relogin=false
EOF
