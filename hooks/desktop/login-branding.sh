#!/bin/bash
set -eu
printf 'PersisOS 2.0 \\n \\l\n' > /etc/issue
printf 'PersisOS 2.0\n' > /etc/issue.net
mkdir -p /etc/default/grub.d
cat > /etc/default/grub.d/50-persisos.cfg <<'EOF'
GRUB_DISTRIBUTOR="PersisOS 2.0"
GRUB_BACKGROUND="/usr/share/wallpapers/Lake/contents/images/2560x1600.png"
EOF
