#!/usr/bin/env python3
"""
Generic live ISO builder for Debian-based distributions.

This script builds a bootable live ISO image from a JSON configuration file.
It supports both BIOS and UEFI boot, Ventoy compatibility, and automated
installation via Debian Installer preseed.
"""

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# =============================================================================
# Architecture and Package Mappings
# =============================================================================

KERNEL_PACKAGES = {
    "amd64": "linux-image-amd64",
    "arm64": "linux-image-arm64",
    "armhf": "linux-image-armmp",
}

GRUB_EFI_PACKAGES = {
    "amd64": "grub-efi-amd64-bin",
    "arm64": "grub-efi-arm64-bin",
    "armhf": "grub-efi-arm-bin",
}

GRUB_EFI_FORMAT = {
    "amd64": "x86_64-efi",
    "arm64": "arm64-efi",
    "armhf": "arm-efi",
}

GRUB_EFI_BINARY = {
    "amd64": "bootx64.efi",
    "arm64": "bootaa64.efi",
    "armhf": "bootarm.efi",
}

LIVE_PACKAGES = [
    "live-boot",
    "live-config",
    "systemd-sysv",
    "sudo",
    "locales",
]

HOST_BUILD_TOOLS = [
    "debootstrap",
    "mksquashfs",
    "xorriso",
    "mtools",
    "grub-mkimage",
    "mkfs.vfat",
]

GRUB_BIOS_MODULES = [
    "biosdisk",
    "part_gpt",
    "part_msdos",
    "fat",
    "iso9660",
    "udf",
    "linux",
    "initrd",
    "normal",
    "configfile",
    "search",
    "search_fs_uuid",
    "search_fs_file",
    "search_label",
    "loopback",
    "gfxterm",
    "all_video",
    "test",
    "true",
    "echo",
    "help",
    "ls",
    "reboot",
    "halt",
]

GRUB_EFI_MODULES = [
    "part_gpt",
    "part_msdos",
    "fat",
    "iso9660",
    "udf",
    "linux",
    "initrd",
    "normal",
    "configfile",
    "search",
    "search_fs_uuid",
    "search_fs_file",
    "search_label",
    "loopback",
    "gfxterm",
    "all_video",
    "test",
    "true",
    "echo",
    "help",
    "ls",
    "reboot",
    "halt",
]


# =============================================================================
# Error Handling
# =============================================================================


class BuildError(Exception):
    """Exception raised when a build step fails."""
    pass


def run(cmd, **kwargs):
    """Run a command, raising BuildError on failure."""
    kwargs.setdefault("text", True)
    kwargs.setdefault("capture_output", False)
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        detail = ""
        if getattr(result, "stderr", None):
            detail = f"\n{result.stderr.strip()}"
        raise BuildError(
            f"Command failed (exit {result.returncode}): {' '.join(str(c) for c in cmd)}{detail}"
        )
    return result


@contextlib.contextmanager
def build_step(name):
    """Context manager that prints step banners."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    try:
        yield
    except BuildError:
        raise
    except Exception as exc:
        raise BuildError(f"Step '{name}' failed: {exc}") from exc


def require_root():
    """Ensure the script is running as root."""
    if os.geteuid() != 0:
        raise BuildError("This script must be run as root.")


def require_tool(name):
    """Ensure a required tool is available."""
    if shutil.which(name) is None:
        raise BuildError(f"Required tool not found: {name}")


def available_grub_modules(grub_dir: Path, requested):
    """Return requested GRUB modules that are actually shipped by Debian."""
    available = {p.stem for p in grub_dir.glob(".mod")}
    missing = [name for name in requested if name not in available]
    tolerated = {"initrd"}
    unexpected = [name for name in missing if name not in tolerated]
    if unexpected:
        raise BuildError(
            f"GRUB modules missing for {grub_dir.name}: {', '.join(unexpected)}"
        )
    return [name for name in requested if name in available]


# =============================================================================
# Configuration Loading
# =============================================================================

REQUIRED_KEYS = ["distro_name", "version", "debian_distro", "apt_mirror", "packages"]

DEFAULTS = {
    "locale": "en_US.UTF-8",
    "timezone": "UTC",
    "squashfs_compression": "xz",
    "splash": "",
    "live_username": None,
    "live_user_password": None,
    "root_password": None,
    "apt_components": ["main", "contrib", "non-free", "non-free-firmware"],
    "security_mirror": "http://deb.debian.org/debian-security",
    "pre_chroot_scripts": [],
    "post_install_scripts": [],
    "architecture": "amd64",
    "installer_enabled": True,
    "installer_preseed_options": {},
}


def load_config(path: str) -> dict:
    """Load and validate the build configuration from a JSON file."""
    with open(path) as f:
        cfg = json.load(f)

    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise BuildError(f"Config missing required keys: {', '.join(missing)}")

    # Support legacy 'arch' key
    if "architecture" not in cfg and "arch" in cfg:
        cfg["architecture"] = cfg["arch"]

    # Apply defaults
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    # Validate architecture
    if cfg["architecture"] not in KERNEL_PACKAGES:
        raise BuildError(
            f"Unsupported architecture {cfg['architecture']!r}; "
            f"choose one of: {', '.join(sorted(KERNEL_PACKAGES))}"
        )

    # Validate APT components
    components = cfg["apt_components"]
    if (
        not isinstance(components, list)
        or not components
        or not all(
            isinstance(component, str)
            and re.fullmatch(r"[a-z0-9][a-z0-9-]*", component)
            for component in components
        )
    ):
        raise BuildError("apt_components must be a non-empty list of APT components")

    # Derive iso_volume_id from distro name if not set
    if "iso_volume_id" not in cfg:
        vol = re.sub(r"[^A-Za-z0-9_]", "_", cfg["distro_name"])[:32]
        cfg["iso_volume_id"] = vol.upper()

    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", cfg["iso_volume_id"]):
        raise BuildError(
            f"iso_volume_id must match [A-Za-z0-9_]{{1,32}}, got: {cfg['iso_volume_id']!r}"
        )

    # Validate iso_filename if provided
    iso_filename = cfg.get("iso_filename")
    if iso_filename is not None:
        if (
            not isinstance(iso_filename, str)
            or Path(iso_filename).name != iso_filename
            or not iso_filename.endswith(".iso")
        ):
            raise BuildError("iso_filename must be a plain filename ending in .iso")

    return cfg


# =============================================================================
# LiveBuilder Class
# =============================================================================


class LiveBuilder:
    """Builds a live ISO image from configuration."""

    def __init__(
        self, config: dict, workdir: str, outdir: str, keep_workdir: bool = False
    ):
        self.cfg = config
        self.workdir = Path(workdir)
        self.outdir = Path(outdir)
        self.keep_workdir = keep_workdir
        self.arch = config["architecture"]

        self.chroot = self.workdir / "chroot"
        self.iso_root = self.workdir / "iso"
        self._pseudo_mounted = False

    # -------------------------------------------------------------------------
    # Directory Setup
    # -------------------------------------------------------------------------

    def prepare_dirs(self):
        """Create necessary directory structures."""
        with build_step("Preparing directories"):
            for d in [
                self.chroot,
                self.iso_root / "live",
                self.iso_root / "boot" / "grub",
                self.iso_root / ".disk",
            ]:
                d.mkdir(parents=True, exist_ok=True)
            self.outdir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # Debootstrap
    # -------------------------------------------------------------------------

    def run_debootstrap(self):
        """Bootstrap a minimal Debian system."""
        with build_step("Running debootstrap"):
            cmd = ["debootstrap", "--arch", self.arch]
            if self.cfg.get("debootstrap_variant"):
                cmd.append(f"--variant={self.cfg['debootstrap_variant']}")
            cmd += [
                self.cfg["debian_distro"],
                str(self.chroot),
                self.cfg["apt_mirror"],
            ]
            run(cmd)

    def _mount_pseudo_filesystems(self):
        """Mount /proc, /sys, /dev into the chroot."""
        with build_step("Mounting pseudo filesystems"):
            self._pseudo_mounted = True
            (self.chroot / "dev" / "pts").mkdir(parents=True, exist_ok=True)
            run(["mount", "-t", "proc", "proc", str(self.chroot / "proc")])
            run(["mount", "-t", "sysfs", "sys", str(self.chroot / "sys")])
            run(["mount", "--bind", "/dev", str(self.chroot / "dev")])
            run(["mount", "--bind", "/dev/pts", str(self.chroot / "dev" / "pts")])

    def _unmount_pseudo_filesystems(self):
        """Unmount pseudo filesystems from the chroot."""
        if not self._pseudo_mounted:
            return
        with build_step("Unmounting pseudo filesystems"):
            for sub in ("dev/pts", "dev", "sys", "proc"):
                path = self.chroot / sub
                if not path.is_dir():
                    continue
                result = subprocess.run(
                    ["umount", str(path)], capture_output=True, text=True
                )
                if result.returncode != 0:
                    subprocess.run(
                        ["umount", "-l", str(path)], capture_output=True, text=True
                    )
            self._pseudo_mounted = False

    # -------------------------------------------------------------------------
    # APT Configuration
    # -------------------------------------------------------------------------

    def configure_apt(self):
        """Configure APT sources and update package lists."""
        with build_step("Configuring APT"):
            suite = self.cfg["debian_distro"]
            components = " ".join(self.cfg["apt_components"])
            sources = "\n".join(
                [
                    f"deb {self.cfg['apt_mirror']} {suite} {components}",
                    f"deb {self.cfg['apt_mirror']} {suite}-updates {components}",
                    f"deb {self.cfg['security_mirror']} {suite}-security {components}",
                    "",
                ]
            )
            (self.chroot / "etc" / "apt" / "sources.list").write_text(sources)
            self._chroot(["apt-get", "update"])

    # -------------------------------------------------------------------------
    # Script Execution
    # -------------------------------------------------------------------------

    def pre_chroot_scripts(self):
        """Execute pre-chroot scripts."""
        for script in self.cfg.get("pre_chroot_scripts", []):
            with build_step(f"Pre-chroot script: {script}"):
                self._run_script(script, rootfs_env=True)

    def post_install_scripts(self):
        """Execute post-install scripts inside chroot."""
        for script in self.cfg.get("post_install_scripts", []):
            with build_step(f"Post-install script: {script}"):
                self._run_script(script)

    def _run_script(self, script, rootfs_env=False):
        """Run either an inline shell script or a path from the config."""
        script = str(script)
        if "\n" in script or script.lstrip().startswith("#!"):
            if rootfs_env:
                env = {**os.environ, "ROOTFS": str(self.chroot)}
                run(["bash", "-c", script], env=env)
            else:
                self._chroot(["bash", "-c", script])
            return
        path = Path(script)
        if not path.is_file():
            raise BuildError(f"Configured script not found: {script}")
        if rootfs_env:
            env = {**os.environ, "ROOTFS": str(self.chroot)}
            run(["bash", str(path)], env=env)
        else:
            dest = self.chroot / "tmp" / path.name
            shutil.copy2(path, dest)
            dest.chmod(0o755)
            self._chroot(["bash", f"/tmp/{path.name}"])
            dest.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # Package Installation
    # -------------------------------------------------------------------------

    def install_packages(self):
        """Install required packages into the chroot."""
        with build_step("Installing packages"):
            pkgs = list(
                dict.fromkeys(
                    list(self.cfg["packages"])
                    + LIVE_PACKAGES
                    + [KERNEL_PACKAGES[self.arch]]
                )
            )
            if self.arch in GRUB_EFI_PACKAGES:
                pkgs.append(GRUB_EFI_PACKAGES[self.arch])
            if self.arch == "amd64":
                pkgs += ["grub-pc-bin", "grub2-common"]

            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            try:
                self._chroot(
                    ["apt-get", "-s", "--no-remove", "install", "-y"] + pkgs,
                    extra_env=env,
                )
            except BuildError as exc:
                raise BuildError(
                    "Package preflight failed. Check the "
                    "configured package names and enabled APT components.\n" + str(exc)
                ) from exc
            self._chroot(
                ["apt-get", "install", "-y"] + pkgs,
                extra_env=env,
            )

    # -------------------------------------------------------------------------
    # Debian Installer Integration
    # -------------------------------------------------------------------------

    def setup_debian_installer(self):
        """Set up Debian Installer with preseed configuration."""
        if not self.cfg.get("installer_enabled", True):
            return

        with build_step("Setting up Debian Installer"):
            di_packages = ["debian-installer-launcher"]
            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            self._chroot(
                ["apt-get", "install", "-y"] + di_packages,
                extra_env=env,
            )

            # Create preseed directory structure
            preseed_dir = self.chroot / "preseed"
            preseed_dir.mkdir(parents=True, exist_ok=True)

            # Generate preseed file with distro-specific name
            distro_lower = self.cfg["distro_name"].lower().replace(' ', '-')
            preseed_filename = f"{distro_lower}.preseed"
            self._generate_preseed_file(preseed_dir / preseed_filename)

            # Copy preseed to ISO root for early access
            iso_preseed = self.iso_root / "preseed"
            iso_preseed.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preseed_dir / preseed_filename, iso_preseed / preseed_filename)

            # Create installer launcher desktop file
            self._create_installer_desktop()

    def _generate_preseed_file(self, preseed_path: Path):
        """Generate a preseed configuration file for automated installation."""
        hostname = self.cfg.get("hostname") or self.cfg["distro_name"].lower().replace(' ', '-')
        locale = self.cfg["locale"]
        timezone = self.cfg["timezone"]
        username = self.cfg.get("live_username", "user")
        distro_name = self.cfg["distro_name"]
        
        # Get installer-specific options from config
        installer_opts = self.cfg.get("installer_preseed_options", {})
        partition_method = installer_opts.get("partition_method", "lvm")
        install_tasks = installer_opts.get("tasks", "standard, ssh-server")
        extra_packages = installer_opts.get("include_packages", "firmware-linux firmware-linux-nonfree network-manager sudo")
        
        preseed_content = f'''# Preseed configuration for {distro_name}
# Generated automatically by build.py

### Locale and Keyboard
d-i debian-installer/locale string {locale}
d-i console-setup/ask_detect boolean false
d-i keyboard-configuration/xkb-keymap select us

### Network Configuration
d-i netcfg/choose_interface select auto
d-i netcfg/get_hostname string {hostname}
d-i netcfg/get_domain string local

### Clock and Timezone
d-i clock-setup/utc boolean true
d-i time/zone string {timezone}
d-i clock-setup/ntp boolean true

### Partitioning
d-i partman-auto/method string {partition_method}
d-i partman-lvm/device_remove_lvm boolean true
d-i partman-md/device_remove_md boolean true
d-i partman-partitioning/confirm_write_new_label boolean true
d-i partman/choose_partition select finish
d-i partman/confirm boolean true
d-i partman/confirm_nooverwrite boolean true

### Package Selection
tasksel tasksel/first multiselect {install_tasks}
d-i pkgsel/include string {extra_packages}
d-i pkgsel/install-language-support boolean false
d-i pkgsel/update-policy select none

### User Setup
d-i passwd/user-fullname string {distro_name} User
d-i passwd/username string {username}
d-i passwd/root-login boolean false

### GRUB Bootloader
d-i grub-installer/only_debian boolean true
d-i grub-installer/with_other_os boolean true
d-i grub-installer/bootdev string default
d-i grub-installer/force-efi-extra-removable boolean true

### Finish Installation
d-i finish-install/reboot_in_progress note
'''
        preseed_path.write_text(preseed_content)
        print(f"  Generated preseed file: {preseed_path}")

    def _create_installer_desktop(self):
        """Create a desktop file to launch the Debian Installer."""
        distro_name = self.cfg["distro_name"]
        desktop_content = f'''[Desktop Entry]
Type=Application
Name=Install {distro_name}
Comment=Launch the Debian Installer to install {distro_name} to your hard drive
Exec=/usr/lib/debian-installer-launcher/launcher
Icon=system-install
Terminal=false
Categories=System;
'''
        # Create in chroot for installed system
        apps_dir = self.chroot / "usr" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_filename = f"install-{distro_name.lower().replace(' ', '-')}.desktop"
        (apps_dir / desktop_filename).write_text(desktop_content)

        # Also create in skel for new users
        skel_apps = self.chroot / "etc" / "skel" / "Desktop"
        skel_apps.mkdir(parents=True, exist_ok=True)
        installer_desktop = skel_apps / f"Install {distro_name}.desktop"
        installer_desktop.write_text(desktop_content)
        installer_desktop.chmod(0o755)

        print("  Created installer desktop launcher")

    # -------------------------------------------------------------------------
    # User Accounts
    # -------------------------------------------------------------------------

    def configure_users(self):
        """Create live user and set passwords."""
        username = self.cfg.get("live_username")
        if not username:
            return

        with build_step(f"Creating live user: {username}"):
            if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
                raise BuildError(
                    "live_username must start with a lowercase letter or underscore "
                    "and contain only lowercase letters, digits, underscores, or hyphens"
                )

            passwd_file = self.chroot / "etc" / "passwd"
            existing_users = {
                line.split(":", 1)[0]
                for line in passwd_file.read_text().splitlines()
                if ":" in line
            }
            if username in existing_users:
                raise BuildError(f"Live user already exists: {username}")

            self._chroot(
                [
                    "useradd",
                    "--create-home",
                    "--user-group",
                    "--shell",
                    "/bin/bash",
                    username,
                ]
            )

            desktop_groups = [
                "sudo",
                "audio",
                "video",
                "plugdev",
                "netdev",
                "bluetooth",
            ]
            for group in desktop_groups:
                self._chroot(["groupadd", "--force", group])
            self._chroot(
                ["usermod", "--append", "--groups", ",".join(desktop_groups), username]
            )

            self._set_password(username, self.cfg.get("live_user_password"))

            root_password = self.cfg.get("root_password")
            if root_password is not None:
                self._set_password("root", root_password)

    def _set_password(self, username, password):
        """Set an account password without exposing it in the process list."""
        if password is None:
            self._chroot(["passwd", "--lock", username])
            return
        password = str(password)
        if "\n" in password or "\r" in password:
            raise BuildError(f"Password for {username} must not contain a newline")
        if password == "":
            self._chroot(["passwd", "--delete", username])
            return
        self._chroot(["chpasswd"], input=f"{username}:{password}\n")

    # -------------------------------------------------------------------------
    # System Configuration
    # -------------------------------------------------------------------------

    def configure_system(self):
        """Configure locale, timezone, hostname, etc."""
        with build_step("Configuring system"):
            # Locale
            locale = self.cfg["locale"]
            locale_gen = self.chroot / "etc" / "locale.gen"
            lines = locale_gen.read_text() if locale_gen.exists() else ""
            if f"# {locale}" in lines:
                lines = lines.replace(f"# {locale}", locale)
            else:
                lines += f"\n{locale} UTF-8\n"
            locale_gen.write_text(lines)
            self._chroot(["locale-gen"])
            (self.chroot / "etc" / "locale.conf").write_text(f"LANG={locale}\n")

            # Timezone
            tz = self.cfg["timezone"]
            tz_file = self.chroot / "usr" / "share" / "zoneinfo" / tz
            if not tz_file.is_file():
                raise BuildError(f"Unknown timezone: {tz}")
            localtime = self.chroot / "etc" / "localtime"
            if localtime.exists() or localtime.is_symlink():
                localtime.unlink()
            localtime.symlink_to(f"/usr/share/zoneinfo/{tz}")
            (self.chroot / "etc" / "timezone").write_text(tz + "\n")

            # Hostname
            hostname = self.cfg.get("hostname") or self.cfg["distro_name"].lower().replace(' ', '-')
            (self.chroot / "etc" / "hostname").write_text(hostname + "\n")
            (self.chroot / "etc" / "hosts").write_text(
                "127.0.0.1\tlocalhost\n"
                f"127.0.1.1\t{hostname}\n"
                "::1\tlocalhost ip6-localhost ip6-loopback\n"
                "ff02::1\tip6-allnodes\n"
                "ff02::2\tip6-allrouters\n"
            )

    # -------------------------------------------------------------------------
    # Chroot Cleanup
    # -------------------------------------------------------------------------

    def cleanup_chroot(self):
        """Clean up the chroot environment."""
        with build_step("Cleaning chroot"):
            env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
            self._chroot(["apt-get", "clean"], extra_env=env)
            for p in (self.chroot / "var" / "cache" / "apt" / "archives").glob("*.deb"):
                p.unlink(missing_ok=True)
            apt_lists = self.chroot / "var" / "lib" / "apt" / "lists"
            if apt_lists.is_dir():
                for p in apt_lists.iterdir():
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink(missing_ok=True)
                (apt_lists / "partial").mkdir()
            for p in (self.chroot / "tmp").glob("*"):
                if p.is_file():
                    p.unlink(missing_ok=True)

            # Clear machine-id for unique generation on first boot
            machine_id = self.chroot / "etc" / "machine-id"
            machine_id.parent.mkdir(parents=True, exist_ok=True)
            machine_id.write_text("")
            (self.chroot / "var" / "lib" / "dbus" / "machine-id").unlink(
                missing_ok=True
            )

    # -------------------------------------------------------------------------
    # Kernel and Initrd Export
    # -------------------------------------------------------------------------

    def export_kernel_and_initrd(self):
        """Copy kernel and initrd from chroot to ISO."""
        with build_step("Exporting kernel and initrd"):
            vmlinuz_list = sorted((self.chroot / "boot").glob("vmlinuz-*"))
            initrd_list = sorted((self.chroot / "boot").glob("initrd.img-*"))
            if not vmlinuz_list:
                raise BuildError("No kernel found in chroot/boot/")
            if not initrd_list:
                raise BuildError("No initrd found in chroot/boot/")
            shutil.copy2(vmlinuz_list[-1], self.iso_root / "live" / "vmlinuz")
            shutil.copy2(initrd_list[-1], self.iso_root / "live" / "initrd")
            print(f"  Kernel : {vmlinuz_list[-1].name}")
            print(f"  Initrd : {initrd_list[-1].name}")

    # -------------------------------------------------------------------------
    # SquashFS Build
    # -------------------------------------------------------------------------

    def build_squashfs(self):
        """Build the SquashFS filesystem."""
        with build_step("Building squashfs"):
            squashfs_path = self.iso_root / "live" / "filesystem.squashfs"
            squashfs_path.unlink(missing_ok=True)
            run(
                [
                    "mksquashfs",
                    str(self.chroot),
                    str(squashfs_path),
                    "-comp",
                    self.cfg["squashfs_compression"],
                    "-e",
                    "boot",
                    "-noappend",
                ]
            )

    # -------------------------------------------------------------------------
    # GRUB Configuration
    # -------------------------------------------------------------------------

    def write_boot_configs(self):
        """Write GRUB configuration files."""
        with build_step("Writing GRUB configuration"):
            vol_id = self.cfg["iso_volume_id"]
            distro = self.cfg["distro_name"]
            version = self.cfg["version"]
            boot_append = self.cfg.get("boot_append", "quiet splash").strip()

            grub_cfg = f'''\
set default=0
set timeout=5
set gfxpayload=keep

# Locate the ISO root — works under Ventoy, direct boot, and QEMU.
if search --no-floppy --set=root --label "{vol_id}" ; then
    echo "Found ISO root by volume label: {vol_id}"
elif search --no-floppy --set=root --file /live/filesystem.squashfs ; then
    echo "Found ISO root by filesystem marker"
else
    echo "WARNING: could not locate ISO root; boot may fail"
fi

menuentry "{distro} {version} (live)" {{
    linux  /live/vmlinuz boot=live components {boot_append}
    initrd /live/initrd
}}

menuentry "{distro} {version} (live, nomodeset)" {{
    linux  /live/vmlinuz boot=live components {boot_append} nomodeset
    initrd /live/initrd
}}

menuentry "{distro} {version} (live, debug)" {{
    linux  /live/vmlinuz boot=live components
    initrd /live/initrd
}}
'''
            (self.iso_root / "boot" / "grub" / "grub.cfg").write_text(grub_cfg)
            (self.iso_root / ".disk" / "info").write_text(
                f"{distro} {version} - Live\n"
            )

    # -------------------------------------------------------------------------
    # ISO Assembly
    # -------------------------------------------------------------------------

    def _find_grub_lib(self, grub_arch: str) -> Path:
        """Return the path to pre-built GRUB modules for grub_arch."""
        for base in ("/usr/lib/grub", "/usr/share/grub"):
            p = Path(base) / grub_arch
            if p.is_dir():
                return p
        for base in (Path("/usr/lib"), Path("/usr/share")):
            matches = list(base.glob(f"**/grub/{grub_arch}"))
            if matches:
                return matches[0]
        raise BuildError(f"GRUB module directory not found for arch '{grub_arch}'")

    def build_iso(self):
        """Build the final ISO image."""
        with build_step("Building ISO image"):
            vol_id = self.cfg["iso_volume_id"]
            distro = self.cfg["distro_name"]
            version = self.cfg["version"]
            grub_dir = self.iso_root / "boot" / "grub"

            # Early config embedded into GRUB core image
            early_cfg = (
                f'search --no-floppy --set=root --label "{vol_id}"\n'
                f'if [ -z "$root" ]; then\n'
                f'    search --no-floppy --set=root --file /live/filesystem.squashfs\n'
                f'fi\n'
                f'set prefix=($root)/boot/grub\n'
            )

            xorriso_args = [
                "xorriso",
                "-as",
                "mkisofs",
                "-iso-level",
                "3",
                "-volid",
                vol_id,
                "-full-iso9660-filenames",
                "-rational-rock",
                "-joliet",
            ]

            # BIOS boot (i386-pc) — amd64 only
            if self.arch == "amd64":
                grub_bios_arch = "i386-pc"
                grub_bios_lib = self._find_grub_lib(grub_bios_arch)

                # Copy BIOS modules into the ISO tree
                bios_mod_dst = grub_dir / grub_bios_arch
                bios_mod_dst.mkdir(parents=True, exist_ok=True)
                for mod in Path(grub_bios_lib).glob("*.mod"):
                    shutil.copy2(mod, bios_mod_dst / mod.name)
                for lst in Path(grub_bios_lib).glob("*.lst"):
                    shutil.copy2(lst, bios_mod_dst / lst.name)

                # Build standalone BIOS core image with early config baked in
                modules = available_grub_modules(grub_bios_lib, GRUB_BIOS_MODULES)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".cfg", delete=False
                ) as ecfg:
                    ecfg.write(early_cfg)
                    early_cfg_path = ecfg.name

                bios_core = grub_dir / "bios.img"
                cdboot = Path(grub_bios_lib) / "cdboot.img"
                bios_core_raw = grub_dir / "core_bios.img"

                try:
                    run(
                        [
                            "grub-mkimage",
                            "--format",
                            grub_bios_arch,
                            "--output",
                            str(bios_core_raw),
                            "--prefix",
                            "/boot/grub",
                            "--config",
                            early_cfg_path,
                            "--directory",
                            str(grub_bios_lib),
                        ]
                        + modules
                    )
                finally:
                    Path(early_cfg_path).unlink(missing_ok=True)

                # Concatenate cdboot.img + core.img → bios.img
                # Ensure the boot signature (0x55AA) is at offset 0x1FE (510)
                with open(bios_core, "wb") as out_f:
                    cdboot_data = cdboot.read_bytes()
                    # Pad cdboot.img to exactly 512 bytes if needed
                    if len(cdboot_data) < 512:
                        cdboot_data = cdboot_data.ljust(512, b'\x00')
                    out_f.write(cdboot_data[:512])
                    out_f.write(bios_core_raw.read_bytes())

                # Verify and fix boot signature at offset 0x1FE
                with open(bios_core, "r+b") as f:
                    f.seek(510)
                    sig = f.read(2)
                    if sig != b'\x55\xaa':
                        f.seek(510)
                        f.write(b'\x55\xaa')

                bios_core_raw.unlink(missing_ok=True)

                # Locate boot_hybrid.img for MBR
                boot_hybrid = Path(grub_bios_lib) / "boot_hybrid.img"
                if not boot_hybrid.exists():
                    boot_hybrid = Path("/usr/lib/grub/i386-pc/boot_hybrid.img")
                if not boot_hybrid.exists():
                    raise BuildError("boot_hybrid.img not found — install grub-pc-bin")

                xorriso_args += [
                    "-eltorito-boot",
                    "boot/grub/bios.img",
                    "-no-emul-boot",
                    "-boot-load-size",
                    "4",
                    "-boot-info-table",
                    "--grub2-boot-info",
                    "--grub2-mbr",
                    str(boot_hybrid),
                ]

            # EFI boot
            if self.arch in GRUB_EFI_FORMAT:
                efi_arch = GRUB_EFI_FORMAT[self.arch]
                efi_binary = GRUB_EFI_BINARY[self.arch]
                grub_efi_lib = self._find_grub_lib(efi_arch)

                # Copy EFI modules into the ISO tree
                efi_mod_dst = grub_dir / efi_arch
                efi_mod_dst.mkdir(parents=True, exist_ok=True)
                for mod in Path(grub_efi_lib).glob("*.mod"):
                    shutil.copy2(mod, efi_mod_dst / mod.name)
                for lst in Path(grub_efi_lib).glob("*.lst"):
                    shutil.copy2(lst, efi_mod_dst / lst.name)

                modules = available_grub_modules(grub_efi_lib, GRUB_EFI_MODULES)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".cfg", delete=False
                ) as ecfg:
                    ecfg.write(early_cfg)
                    early_cfg_path = ecfg.name

                efi_out = grub_dir / efi_binary
                try:
                    run(
                        [
                            "grub-mkimage",
                            "--format",
                            efi_arch,
                            "--output",
                            str(efi_out),
                            "--prefix",
                            "/boot/grub",
                            "--config",
                            early_cfg_path,
                            "--directory",
                            str(grub_efi_lib),
                        ]
                        + modules
                    )
                finally:
                    Path(early_cfg_path).unlink(missing_ok=True)

                # Build a FAT12 ESP image and put the EFI binary inside it
                efi_img = grub_dir / "efi.img"
                efi_img.unlink(missing_ok=True)
                run(["dd", "if=/dev/zero", f"of={efi_img}", "bs=1k", "count=1440"])
                run(["mkfs.vfat", "-F", "12", "-n", "GRUB_EFI", str(efi_img)])
                run(["mmd", "-i", str(efi_img), "::/EFI", "::/EFI/BOOT"])
                run(
                    [
                        "mcopy",
                        "-i",
                        str(efi_img),
                        str(efi_out),
                        f"::/EFI/BOOT/{efi_binary}",
                    ]
                )

                xorriso_args += [
                    "-eltorito-alt-boot",
                    "-e",
                    "boot/grub/efi.img",
                    "-no-emul-boot",
                    "-isohybrid-gpt-basdat",
                ]

            # Final xorriso invocation
            iso_name = self.cfg.get("iso_filename") or (
                f"{distro}-{version}-{self.arch}.iso"
            )
            iso_out = self.outdir / iso_name
            xorriso_args += ["-output", str(iso_out), str(self.iso_root)]
            run(xorriso_args)
            print(f"\n  ISO written to: {iso_out}")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def _chroot(self, cmd, extra_env=None, **kwargs):
        """Execute a command inside the chroot."""
        env = extra_env or os.environ.copy()
        run(["chroot", str(self.chroot)] + cmd, env=env, **kwargs)

    # -------------------------------------------------------------------------
    # Main Build Pipeline
    # -------------------------------------------------------------------------

    def build(self):
        """Execute the full build pipeline."""
        try:
            self.prepare_dirs()
            self.run_debootstrap()
            try:
                self._mount_pseudo_filesystems()
                self.configure_apt()
                self.pre_chroot_scripts()
                self.install_packages()
                self.setup_debian_installer()
                self.configure_users()
                self.configure_system()
                self.post_install_scripts()
                self.cleanup_chroot()
            finally:
                self._unmount_pseudo_filesystems()
            self.export_kernel_and_initrd()
            self.build_squashfs()
            self.write_boot_configs()
            self.build_iso()
            print("\n✓ Build complete.")
        finally:
            if not self.keep_workdir:
                shutil.rmtree(self.workdir, ignore_errors=True)


# =============================================================================
# Command Line Interface
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generic live ISO builder for Debian-based distributions"
    )
    parser.add_argument("config", help="Path to JSON build config")
    parser.add_argument(
        "--workdir", default=None, help="Working directory (default: temp dir)"
    )
    parser.add_argument(
        "--outdir", default="./output", help="Output directory for the ISO"
    )
    parser.add_argument(
        "--keep-workdir", action="store_true", help="Do not delete workdir after build"
    )
    args = parser.parse_args()

    require_root()
    for tool in HOST_BUILD_TOOLS:
        require_tool(tool)

    cfg = load_config(args.config)

    if args.workdir:
        workdir = args.workdir
        Path(workdir).mkdir(parents=True, exist_ok=True)
        builder = LiveBuilder(cfg, workdir, args.outdir, keep_workdir=args.keep_workdir)
        builder.build()
    else:
        with tempfile.TemporaryDirectory(prefix="live_iso_build_") as tmpdir:
            builder = LiveBuilder(
                cfg, tmpdir, args.outdir, keep_workdir=args.keep_workdir
            )
            builder.build()


if __name__ == "__main__":
    try:
        main()
    except BuildError as e:
        print(f"\n✗ Build failed: {e}", file=sys.stderr)
        sys.exit(1)
