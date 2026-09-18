#!/bin/bash
set -e
echo 'Applying password quality policy'
if [ -f /etc/pam.d/common-password ] && ! grep -q pam_pwquality /etc/pam.d/common-password; then
    sed -i '/pam_unix.so/i password\trequisite\t\t\tpam_pwquality.so retry=3 minlen=12' /etc/pam.d/common-password
fi
