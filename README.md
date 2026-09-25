
# PersisOS

[![Build](https://github.com/PersisOS/PersisOS/actions/workflows/build.yml/badge.svg)](https://github.com/PersisOS/PersisOS/actions/workflows/build.yml)
[![Build PersisOS Server](https://github.com/PersisOS/PersisOS/actions/workflows/server-build.yml/badge.svg)](https://github.com/PersisOS/PersisOS/actions/workflows/server-build.yml)
![Debian](https://img.shields.io/badge/base-Debian%2013-A81D33?logo=debian&logoColor=white)
![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20arm64-4B6CB7)

PersisOS is a Debian 13-based operating system available as a polished KDE
Plasma desktop and a headless server edition. The desktop ships with a focused
set of everyday applications and a branded Plasma experience. The server image
provides administration, diagnostics, storage, networking, security, container,
and virtualization tools, with a guided command-line installer.

## Design goals

- **Stable:** PersisOS 2.0 is pinned to Debian 13 (Trixie) and enables the
  matching security and stable-updates repositories.
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

The amd64 server image uses its own manifest and CI workflow:

```bash
sudo python3 build.py PersisOS-Server-2.0-amd64.json \
  --workdir build-server --outdir output-server
```

The server live account is `admin` with password `persisos`. Run
`install-persisos` from a local console with a display attached to start
Calamares. SSH is installed but intentionally disabled on live media until the
administrator changes that password and enables the service.

## Project layout

- `build.py` — configurable Debian-family live ISO builder
- `PersisOS-2.0-*.json` — desktop image definitions
- `PersisOS-Server-2.0-amd64.json` — headless amd64 server image definition
- `hooks/` — readable PersisOS customization scripts
- `examples/` — minimal Debian and Ubuntu manifests
- `assets/` — Plasma, SDDM, icon, and wallpaper branding
- `.github/workflows/` — pull request, branch, and release builds
