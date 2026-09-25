#!/bin/bash
set -eu
install -D -o root -g root -m 0755 /.temp_assets/server/usr/local/bin/install-persisos /usr/local/bin/install-persisos
install -D -o root -g root -m 0440 /.temp_assets/server/etc/sudoers.d/90-persisos-installer /etc/sudoers.d/90-persisos-installer
