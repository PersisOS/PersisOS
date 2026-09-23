#!/bin/bash
set -eu
printf 'PersisOS 2.0 \\n \\l\n' > /etc/issue
printf 'PersisOS 2.0\n' > /etc/issue.net
mkdir -p /etc/default/grub.d
printf 'GRUB_DISTRIBUTOR="PersisOS 2.0"\n' > /etc/default/grub.d/50-persisos.cfg
