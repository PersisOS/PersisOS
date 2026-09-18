#!/bin/bash
set -eu
printf '%s\n' 'PersisOS Server 2.0 \n \l' > /etc/issue
printf 'PersisOS Server 2.0\n' > /etc/issue.net
mkdir -p /etc/default/grub.d
printf 'GRUB_DISTRIBUTOR="PersisOS Server 2.0"\n' > /etc/default/grub.d/50-persisos-server.cfg
cat > /etc/motd << 'EOF'
Welcome to PersisOS Server 2.0

Live account: admin
SSH is installed but disabled on live media. After changing the password, run:
  sudo passwd admin
  sudo systemctl enable --now ssh

Use nmcli for network configuration and nft for firewall management.
EOF
