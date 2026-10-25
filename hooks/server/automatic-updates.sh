#!/bin/bash
set -e
echo 'Configuring automatic security updates'
cat > /etc/apt/apt.conf.d/20auto-upgrades << 'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52persisos-security << 'EOF'
// PersisOS has its own os-release ID; match the upstream Debian archive.
Unattended-Upgrade::Origins-Pattern {
    "origin=Debian,codename=forky-security,label=Debian-Security";
};
Unattended-Upgrade::Automatic-Reboot "false";
EOF
