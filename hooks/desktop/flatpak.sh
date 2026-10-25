#!/bin/bash
set -e
echo 'Configuring the Flathub Flatpak remote'
flatpak remote-add --if-not-exists --system flathub https://dl.flathub.org/repo/flathub.flatpakrepo
