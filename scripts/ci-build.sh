#!/bin/bash
# Run inside a privileged, native-architecture Debian container.
set -euo pipefail
config=${1:?Usage: ci-build.sh CONFIG}
export DEBIAN_FRONTEND=noninteractive
apt-get update
case "$(dpkg --print-architecture)" in
    amd64)
        grub_packages=(grub-pc-bin grub-efi-amd64-bin qemu-system-x86 ovmf)
        export RUN_BOOT_SMOKE=1 REQUIRE_UEFI_SMOKE=1
        ;;
    arm64) grub_packages=(grub-efi-arm64-bin) ;;
    armhf) grub_packages=(grub-efi-arm-bin) ;;
    *) echo 'Unsupported build architecture' >&2; exit 1 ;;
esac
apt-get install -y --no-install-recommends \
    debootstrap debian-archive-keyring ca-certificates squashfs-tools \
    grub2-common "${grub_packages[@]}" xorriso mtools dosfstools python3
python3 -m unittest discover -s tests -v
python3 build.py "$config" --validate
python3 build.py "$config" --workdir build --outdir output
