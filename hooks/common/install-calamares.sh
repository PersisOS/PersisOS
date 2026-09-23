#!/bin/bash
set -eu
echo 'Installing Calamares config and branding'
cp -a /.temp_assets/calamares/. /etc/calamares/
