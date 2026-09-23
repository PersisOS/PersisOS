#!/bin/bash
set -e
echo 'Configuring the Flathub Flatpak remote'
if ! flatpak remote-add --if-not-exists --system flathub https://dl.flathub.org/repo/flathub.flatpakrepo; then
    echo 'Warning: Flathub could not be configured during the build.'
    echo 'Add it later with: flatpak remote-add --if-not-exists --system flathub https://dl.flathub.org/repo/flathub.flatpakrepo'
fi
