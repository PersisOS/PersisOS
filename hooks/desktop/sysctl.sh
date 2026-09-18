#!/bin/bash
set -e
echo 'Applying kernel/network hardening sysctls'
cat > /etc/sysctl.d/99-persisos-hardening.conf << 'EOF'
kernel.kptr_restrict=2
kernel.dmesg_restrict=1
kernel.yama.ptrace_scope=1
net.ipv4.conf.all.rp_filter=1
net.ipv4.conf.default.rp_filter=1
net.ipv4.icmp_echo_ignore_broadcasts=1
net.ipv4.conf.all.accept_redirects=0
net.ipv6.conf.all.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
fs.protected_hardlinks=1
fs.protected_symlinks=1
EOF
