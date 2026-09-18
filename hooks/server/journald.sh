#!/bin/bash
set -e
echo 'Configuring persistent system logs'
mkdir -p /var/log/journal /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/99-persisos-server.conf << 'EOF'
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=512M
EOF
