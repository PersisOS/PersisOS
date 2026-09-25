#!/bin/bash
set -eu
echo 'Installing Calamares config and branding'
cp -a /.temp_assets/calamares/. /etc/calamares/
if [ -d /.temp_assets/server ]; then
    cp -a /.temp_assets/server/. /
    chown root:root /usr/local/bin/install-persisos /etc/sudoers.d/90-persisos-installer
    chmod 0755 /usr/local/bin/install-persisos
    chmod 0440 /etc/sudoers.d/90-persisos-installer
fi
