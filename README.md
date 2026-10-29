
# PersisOS

[![Build](https://github.com/PersisOS/PersisOS/actions/workflows/build.yml/badge.svg)](https://github.com/PersisOS/PersisOS/actions/workflows/build.yml)
![Debian](https://img.shields.io/badge/base-Debian%20Forky-A81D33?logo=debian&logoColor=white)
![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20arm64-4B6CB7)

PersisOS is a Debian Forky-based operating system available as a KDE
Plasma desktop and a headless server edition. The desktop ships with a focused
set of everyday applications and a branded Plasma experience. The server image
provides administration, diagnostics, storage, networking, security, container,
and virtualization tools, with a guided command-line installer.

## Design goals

- **Debian Forky:** PersisOS 2.0 tracks the Forky suite and its matching
  security archive. Review upgrades before applying package transitions.
- **User-friendly:** The live session provides a complete Plasma desktop,
  both Wayland and X11 sessions, modern web browsing, common file formats,
  screenshots, networking, audio, Bluetooth, power and firmware management,
  disk-health monitoring, and a branded graphical installer.
- **Lean:** Packages are installed without automatic recommendations. The
  image includes a deliberately small application set instead of multiple
  programs for the same task.

Package additions should solve a common desktop need, hardware requirement,
security issue, or accessibility problem. Optional specialist applications
belong in the repositories rather than the base image.

## Build

The builder supports configurable Debian-family live images. See [the builder guide](docs/builder.md) for dependencies, configuration, examples, and supported boot targets. Full builds require root; configuration validation does not.

```bash
python3 build.py PersisOS-2.0-amd64.json --validate
```

```bash
sudo python3 build.py PersisOS-2.0-amd64.json --workdir build --outdir output
```

Use the arm64 configuration for ARM images. Generated files are written to `output/`; temporary build state is kept in `build/` and ignored by Git.

Desktop images include Flatpak, Flathub, and KDE Discover integration. Install Flatpak applications from Discover or with `flatpak install flathub APP_ID`. Forky does not provide the FUSE 2 library required by some AppImages; for type 2 AppImages that support it, run `./app.AppImage --appimage-extract-and-run` as a fallback.

Discover also manages Debian packages through PackageKit. Open downloaded `.flatpakref` files in Discover to install applications from other Flatpak repositories. Application binaries must match the machine's architecture; ARM64 images do not emulate amd64 applications.
The default panel pins Discover for quick access to software installation and updates.

PersisOS 2.0 tracks Debian Forky. Automatic upgrades select the Debian Forky security archive and never reboot automatically. Review regular Forky updates in Discover or run `sudo apt update` followed by `sudo apt full-upgrade`; a testing release can require package removals during transitions.

### Test in QEMU

For an amd64 desktop ISO, run from the project directory:

```bash
qemu-system-x86_64 -m 4096 -smp 2 -boot d \
  -cdrom output/PersisOS-2.0-amd64.iso
```

The GRUB menu should appear, then start the live session automatically. Select
the `live, debug` entry to show boot messages or `live, nomodeset` when
troubleshooting a blank graphical display. Use QEMU's graphical window for this
command; the default boot entries do not configure a serial console.

If an older amd64 image stalls at `Booting from DVD/CD...` before GRUB appears,
rebuild it with the corrected builder. Earlier builds truncated GRUB's CD loader
to 512 bytes, producing an ISO that built successfully but could not boot via
BIOS. ARM64 images require an ARM64 virtual machine and matching UEFI firmware.

Run the boot-image assembly regression test with:

```bash
python3 -m unittest discover -s tests -v
```

Server images use architecture-specific manifests and CI builds:

```bash
sudo python3 build.py PersisOS-Server-2.0-amd64.json \
  --workdir build-server --outdir output-server

sudo python3 build.py PersisOS-Server-2.0-arm64.json \
  --workdir build-server-arm64 --outdir output-server-arm64
```

Fastfetch is installed in the desktop and server images. It runs when an
interactive Bash terminal opens and displays the PersisOS logo.

The server live account is `admin` with password `persisos`. The text-interface
installer starts automatically on the first console when booting live media;
it lists unused disks with capacity and model, asks for an installed hostname,
time zone, and new admin password, and requires explicit confirmation before
erasing the selected disk. It configures the installed system and bootloader. During installation, a persistent
progress screen shows the current stage, elapsed time, and file-copy percentage.
Overall progress is approximate; detailed output is logged under `/tmp` and the
log is retained if installation fails.
You can also run `sudo install-persisos` from a local console. SSH is installed
but intentionally disabled on live media until the administrator changes that
password and enables the service.
The ARM64 server installer requires booting the live image in UEFI mode.

## Project layout

- `build.py` — configurable Debian-family live ISO builder
- `PersisOS-2.0-*.json` — desktop image definitions
- `PersisOS-Server-2.0-amd64.json` and `PersisOS-Server-2.0-arm64.json` — headless server image definitions
- `hooks/` — readable PersisOS customization scripts
- `examples/` — minimal Debian and Ubuntu manifests
- `assets/` — Plasma, SDDM, icon, and wallpaper branding
- `.github/workflows/` — pull request, branch, and release builds
