#!/usr/bin/env python3
"""
Generic live ISO builder for Debian-based distributions.

This script builds a bootable live ISO image from a JSON configuration file.
It supports GRUB BIOS/UEFI boot and optional Debian Installer launcher and
preseed generation. Distribution-specific customization belongs in manifests.
"""

import argparse
import contextlib
import copy
import shlex
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
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
    "live-config-systemd",
    "live-boot-initramfs-tools",
    "initramfs-tools",
    "tzdata",
    "systemd-sysv",
    "sudo",
    "locales",
]

HOST_BUILD_TOOLS = [
    "dpkg",
    "debootstrap",
    "mksquashfs",
    "xorriso",
    "mmd",
    "mcopy",
    "mount",
    "umount",
    "chroot",
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
    try:
        result = subprocess.run(cmd, **kwargs)
    except OSError as exc:
        raise BuildError(f"Cannot execute {cmd[0]}: {exc}") from exc
    if result.returncode != 0:
        detail = ""
        if getattr(result, "stderr", None):
            detail = f"\n{result.stderr.strip()}"
        raise BuildError(
            f"Command failed (exit {result.returncode}): {shlex.join(str(c) for c in cmd[:2])}{detail}"
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
    except BuildError as exc:
        raise BuildError(f"{name}: {exc}") from exc
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
    available = {p.stem for p in grub_dir.glob("*.mod")}
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

REQUIRED_KEYS = ["distro_name", "version", "suite", "apt_mirror", "packages"]

DEFAULTS = {
    "locale": "en_US.UTF-8", "timezone": "UTC",
    "squashfs_compression": "xz", "live_username": "user",
    "live_user_password": None, "root_password": None,
    "apt_components": ["main"], "pre_chroot_scripts": [],
    "post_install_scripts": [], "architecture": "amd64",
    "installer_enabled": False, "installer_preseed_options": {},
    "installer_netboot": True,
    "exclude_packages": [], "install_recommends": False,
    "live_packages": LIVE_PACKAGES, "boot_append": "quiet",
    "services": {"enable": [], "disable": [], "mask": []},
    "os_release": {},
    "user_groups": ["sudo", "audio", "video", "plugdev", "netdev"],
}


def single_line(value, *, empty=False):
    """Whether a value can be safely represented on one configuration line."""
    return (
        isinstance(value, str)
        and (empty or bool(value))
        and not any(char in value for char in "\n\r\0")
    )


def matches(pattern, value):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def name_list(value, pattern=r"[a-z0-9][a-z0-9+.:_-]*"):
    return isinstance(value, list) and all(matches(pattern, item) for item in value)


def load_config(path: str) -> dict:
    """Normalize legacy names and reject invalid input before privileged work."""
    config_path = Path(path).resolve()
    try:
        cfg = json.loads(config_path.read_text())
    except (OSError, ValueError) as exc:
        raise BuildError(f"Cannot read configuration {path}: {exc}") from exc
    if not isinstance(cfg, dict):
        raise BuildError("Configuration must be a JSON object")
    for old, new in (("arch", "architecture"), ("debian_distro", "suite")):
        if old in cfg:
            if new in cfg and cfg[new] != cfg[old]:
                raise BuildError(f"Conflicting {old} and {new}")
            cfg[new] = cfg.pop(old)
    allowed = set(DEFAULTS) | set(REQUIRED_KEYS) | {
        "hostname", "iso_filename", "iso_volume_id", "kernel_package",
        "apt_sources", "debootstrap_variant", "grub_background",
        "debootstrap_script", "debootstrap_keyring", "os_release",
    }
    unknown = set(cfg) - allowed
    if unknown:
        raise BuildError(f"Unknown configuration keys: {', '.join(sorted(unknown))}")
    missing = [key for key in REQUIRED_KEYS if key not in cfg]
    if missing:
        raise BuildError(f"Missing required keys: {', '.join(missing)}")
    cfg = {**copy.deepcopy(DEFAULTS), **cfg}
    for key in REQUIRED_KEYS[:-1] + ["locale", "timezone"]:
        if not single_line(cfg[key]):
            raise BuildError(f"{key} must be a nonempty single-line string")
    if not single_line(cfg["boot_append"], empty=True):
        raise BuildError("boot_append must be a single-line string")
    for key in ("distro_name", "version", "boot_append"):
        if any(c in cfg[key] for c in '\"\\$`;{}'):
            raise BuildError(f"{key} contains unsupported boot configuration characters")
    if cfg["architecture"] not in tuple(KERNEL_PACKAGES):
        raise BuildError("architecture must be amd64, arm64 or armhf")
    cfg.setdefault("kernel_package", KERNEL_PACKAGES[cfg["architecture"]])
    for key in ("packages", "exclude_packages", "live_packages", "apt_components", "user_groups"):
        value = cfg[key]
        if not name_list(value):
            raise BuildError(f"{key} must be a list of valid names")
    if not cfg["apt_components"] or not matches(r"[a-z0-9][a-z0-9+.-]*", cfg["kernel_package"]):
        raise BuildError("apt_components and kernel_package must be valid and nonempty")
    for key in ("installer_enabled", "install_recommends"):
        if not isinstance(cfg[key], bool):
            raise BuildError(f"{key} must be boolean")
    for key in ("root_password", "live_user_password"):
        if cfg[key] is not None and not single_line(cfg[key], empty=True):
            raise BuildError(f"{key} must be null or a single-line string")
    username = cfg["live_username"]
    if username is not None and (
        not matches(r"[a-z_][a-z0-9_-]{0,31}", username) or username == "root"
    ):
        raise BuildError("live_username must be a valid non-root account name or null")
    slug = re.sub(r"[^a-z0-9]+", "-", cfg["distro_name"].lower()).strip("-") or "live"
    cfg.setdefault("hostname", slug[:63])
    if not matches(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", cfg["hostname"]):
        raise BuildError("hostname must be a valid single DNS label")
    if Path(cfg["timezone"]).is_absolute() or ".." in Path(cfg["timezone"]).parts:
        raise BuildError("timezone must be relative to the zoneinfo directory")
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", cfg["locale"]):
        raise BuildError("Invalid locale")
    if cfg["squashfs_compression"] not in ("xz", "zstd", "gzip", "lzo", "lz4"):
        raise BuildError("Unsupported squashfs_compression")
    volume_id = re.sub(r"[^A-Za-z0-9_]", "_", cfg["distro_name"]).upper()[:32]
    cfg.setdefault("iso_volume_id", volume_id)
    if not matches(r"[A-Za-z0-9_]{1,32}", cfg["iso_volume_id"]):
        raise BuildError("iso_volume_id must contain 1–32 letters, digits or underscores")
    cfg.setdefault("iso_filename", f"{slug}-{cfg['version']}-{cfg['architecture']}.iso")
    name = cfg["iso_filename"]
    if not matches(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.iso", name):
        raise BuildError("iso_filename must be a plain .iso filename")
    # No implicit Debian security/updates repositories for derivatives or rolling suites.
    components = " ".join(cfg["apt_components"])
    base_source = f"deb {cfg['apt_mirror']} {cfg['suite']} {components}"
    cfg.setdefault("apt_sources", [base_source])
    sources = cfg["apt_sources"]
    if not isinstance(sources, list) or not sources or not all(
        single_line(source) and source.startswith(("deb ", "deb-src "))
        for source in sources
    ):
        raise BuildError("apt_sources must be a nonempty list of one-line APT sources")
    for key in ("pre_chroot_scripts", "post_install_scripts"):
        if not isinstance(cfg[key], list) or not all(isinstance(x, str) and x for x in cfg[key]):
            raise BuildError(f"{key} must be a list of scripts")
        for script in cfg[key]:
            inline = "\n" in script or script.startswith("#!")
            if not inline and not (config_path.parent / script).is_file():
                raise BuildError(f"Script does not exist: {script}")
    if "grub_background" in cfg:
        bg = cfg["grub_background"]
        if not isinstance(bg, str) or not matches(r"[A-Za-z0-9][A-Za-z0-9_.\-/]*", bg) or ".." in Path(bg).parts:
            raise BuildError("grub_background must be a relative path to an image")
        bg_path = config_path.parent / bg
        if not bg_path.is_file() or bg_path.suffix.lower() not in (".png", ".jpg", ".jpeg", ".tga"):
            raise BuildError(f"grub_background image does not exist or is unsupported: {bg}")
        cfg["grub_background"] = str(bg_path.resolve())
    for key in ("debootstrap_keyring", "debootstrap_script"):
        if key in cfg:
            if not isinstance(cfg[key], str) or not (config_path.parent / cfg[key]).is_file():
                raise BuildError(f"{key} must name an existing file")
            cfg[key] = str((config_path.parent / cfg[key]).resolve())
    services = cfg["services"]
    if not isinstance(services, dict) or set(services) - {"enable", "disable", "mask"}:
        raise BuildError("services supports enable, disable and mask lists")
    for action, units in services.items():
        if not name_list(units, r"[A-Za-z0-9_][A-Za-z0-9@_.-]*"):
            raise BuildError(f"services.{action} must contain unit names")
    if not isinstance(cfg["installer_preseed_options"], dict):
        raise BuildError("installer_preseed_options must be an object")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cfg["suite"]):
        raise BuildError("suite must be a release name")
    if not re.fullmatch(r"(?:https?|file)://[^\s]+", cfg["apt_mirror"]):
        raise BuildError("apt_mirror must be an HTTP(S) or file URL")
    if "debootstrap_variant" in cfg and cfg["debootstrap_variant"] not in ("minbase", "buildd", "fakechroot"):
        raise BuildError("Unsupported debootstrap_variant")
    for key, value in cfg["installer_preseed_options"].items():
        if key not in ("partition_method", "tasks", "include_packages") or not single_line(value):
            raise BuildError("Invalid installer_preseed_options")
    identity = cfg["os_release"]
    if not isinstance(identity, dict) or not all(
        matches(r"[A-Z][A-Z0-9_]*", k) and single_line(v, empty=True)
        for k, v in identity.items()
    ):
        raise BuildError("os_release must map uppercase field names to single-line strings")
    requested = set(cfg["packages"] + cfg["live_packages"] + [cfg["kernel_package"]])
    if requested.intersection(cfg["exclude_packages"]):
        raise BuildError("An explicitly requested package is also excluded")
    cfg["_config_dir"] = str(config_path.parent)
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
        self.workdir = Path(workdir).resolve()
        self.outdir = Path(outdir).resolve()
        self.keep_workdir = keep_workdir
        self.arch = config["architecture"]

        self.chroot = self.workdir / "chroot"
        self.iso_root = self.workdir / "iso"
        self._mounts = []
        self._owns_workdir = False

    # -------------------------------------------------------------------------
    # Directory Setup
    # -------------------------------------------------------------------------

    def prepare_dirs(self):
        """Create necessary directory structures."""
        with build_step("Preparing directories"):
            if (
                self.workdir == self.outdir
                or self.workdir in self.outdir.parents
                or self.outdir in self.workdir.parents
            ):
                raise BuildError("Work and output directories must not overlap")
            if self.workdir.exists() and any(self.workdir.iterdir()):
                raise BuildError(f"Working directory must be empty: {self.workdir}")
            self._owns_workdir = True
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
            cmd.append("--components=" + ",".join(self.cfg["apt_components"]))
            if self.cfg.get("debootstrap_keyring"):
                cmd.append("--keyring=" + self.cfg["debootstrap_keyring"])
            cmd += [
                self.cfg["suite"],
                str(self.chroot),
                self.cfg["apt_mirror"],
            ]
            if self.cfg.get("debootstrap_script"):
                cmd.append(self.cfg["debootstrap_script"])
            run(cmd)
            policy = self.chroot / "usr/sbin/policy-rc.d"
            policy.write_text("#!/bin/sh\nexit 101\n")
            policy.chmod(0o755)

    def _mount_pseudo_filesystems(self):
        """Mount /proc, /sys, /dev into the chroot."""
        with build_step("Mounting pseudo filesystems"):
            for sub, args in (
                ("proc", ["-t", "proc", "proc"]),
                ("sys", ["-t", "sysfs", "sys"]),
                ("dev", ["--bind", "/dev"]),
                ("dev/pts", ["--bind", "/dev/pts"]),
            ):
                target = self.chroot / sub
                target.mkdir(parents=True, exist_ok=True)
                run(["mount", *args, str(target)])
                self._mounts.append(target)

    @staticmethod
    def _unmount_target(target):
        """Unmount a target, tolerating transient busy states.

        Processes spawned inside the chroot (for example initramfs hooks)
        can still hold the mount open for a moment after their parent exits.
        Retry with backoff, then detach lazily so cleanup never wedges the
        build on a mount that is on its way out anyway.
        """
        delay = 0.2
        for _ in range(4):
            try:
                run(["umount", str(target)])
                return
            except BuildError:
                time.sleep(delay)
                delay *= 2
        run(["umount", "-l", str(target)])

    def _unmount_pseudo_filesystems(self):
        """Never delete a tree while it still contains a host mount."""
        failed = []
        for target in reversed(self._mounts[:]):
            try:
                self._unmount_target(target)
                self._mounts.remove(target)
            except BuildError:
                failed.append(str(target))
        if failed:
            raise BuildError("Unable to unmount; work directory retained: " + ", ".join(failed))

    # -------------------------------------------------------------------------
    # APT Configuration
    # -------------------------------------------------------------------------

    def configure_apt(self):
        """Configure APT sources and update package lists."""
        with build_step("Configuring APT"):
            sources = "\n".join(self.cfg["apt_sources"]) + "\n"
            (self.chroot / "etc/apt/sources.list").write_text(sources)
            apt_conf = self.chroot / "etc/apt/apt.conf.d/99-live-builder"
            recommends = str(self.cfg["install_recommends"]).lower()
            apt_conf.write_text(
                f'APT::Install-Recommends "{recommends}";\n'
                'APT::Install-Suggests "false";\n'
                'Acquire::Retries "3";\n'
            )
            if self.cfg["exclude_packages"]:
                (self.chroot / "etc/apt/preferences.d/live-builder").write_text(
                    "Package: " + " ".join(self.cfg["exclude_packages"]) + "\nPin: version *\nPin-Priority: -1\n")
            self._chroot(["apt-get", "update"])

    # -------------------------------------------------------------------------
    # Script Execution
    # -------------------------------------------------------------------------

    def pre_chroot_scripts(self):
        """Execute pre-chroot scripts."""
        for index, script in enumerate(self.cfg.get("pre_chroot_scripts", []), 1):
            with build_step(f"Host hook {index}"):
                self._run_script(script, rootfs_env=True)

    def post_install_scripts(self):
        """Execute post-install scripts inside chroot."""
        for index, script in enumerate(self.cfg.get("post_install_scripts", []), 1):
            with build_step(f"Chroot hook {index}"):
                self._run_script(script)

    def _run_script(self, script, rootfs_env=False):
        """Run either an inline shell script or a path from the config."""
        script = str(script)
        if "\n" in script or script.lstrip().startswith("#!"):
            if rootfs_env:
                env = {**os.environ, "ROOTFS": str(self.chroot)}
                run(["bash", "-eu", "-c", script], env=env, cwd=self.cfg["_config_dir"])
            else:
                self._chroot(["bash", "-eu", "-c", script])
            return
        path = Path(self.cfg["_config_dir"]) / script
        if not path.is_file():
            raise BuildError(f"Configured script not found: {script}")
        if rootfs_env:
            env = {**os.environ, "ROOTFS": str(self.chroot)}
            run(["bash", "-eu", str(path)], env=env, cwd=self.cfg["_config_dir"])
        else:
            with tempfile.NamedTemporaryFile(dir=self.chroot / "tmp", prefix="build-hook-", suffix=".sh") as hook:
                shutil.copyfile(path, hook.name)
                self._chroot(["bash", "-eu", "/tmp/" + Path(hook.name).name])

    # -------------------------------------------------------------------------
    # Package Installation
    # -------------------------------------------------------------------------

    def install_packages(self):
        """Install required packages into the chroot."""
        with build_step("Installing packages"):
            pkgs = list(
                dict.fromkeys(
                    list(self.cfg["packages"])
                    + self.cfg["live_packages"]
                    + [self.cfg["kernel_package"]]
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
                ["apt-get", "--no-remove", "install", "-y"] + pkgs,
                extra_env=env,
            )

    # -------------------------------------------------------------------------
    # Debian Installer Integration
    # -------------------------------------------------------------------------

    def setup_debian_installer(self):
        """Set up Debian Installer with preseed configuration."""
        if not self.cfg.get("installer_enabled", False):
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
            distro_lower = self.cfg["hostname"]
            preseed_filename = f"{distro_lower}.preseed"
            self._generate_preseed_file(preseed_dir / preseed_filename)

            # Copy preseed to ISO root for early access
            iso_preseed = self.iso_root / "preseed"
            iso_preseed.mkdir(parents=True, exist_ok=True)
            shutil.copy2(preseed_dir / preseed_filename, iso_preseed / preseed_filename)

            # Fetch Debian Installer netboot images onto the ISO so the
            # bootloader can offer a real "Install <distro>" boot option.
            if self.cfg.get("installer_netboot", True):
                with build_step("Fetching Debian Installer netboot images"):
                    self._fetch_netboot_installer()

            # Create installer launcher desktop file
            self._create_installer_desktop()

    def _fetch_netboot_installer(self):
        """Download d-i netboot kernel/initrd into iso_root/install/."""
        arch = self.cfg["architecture"]
        suite = self.cfg["suite"]
        base = (
            f"{self.cfg['apt_mirror'].rstrip('/')}"
            f"/dists/{suite}/main/installer-{arch}/current/images/netboot/debian-installer/{arch}"
        )
        targets = [
            ("linux", "install/vmlinuz"),
            ("initrd.gz", "install/initrd.gz"),
            ("gtk/linux", "install/gtk/vmlinuz"),
            ("gtk/initrd.gz", "install/gtk/initrd.gz"),
        ]
        fetched = 0
        for src, dst in targets:
            out = self.iso_root / dst
            out.parent.mkdir(parents=True, exist_ok=True)
            url = f"{base}/{src}"
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "builder"})
                with urllib.request.urlopen(request, timeout=120) as resp, open(out, "wb") as fh:
                    shutil.copyfileobj(resp, fh)
                fetched += 1
                print(f"  Downloaded {dst}")
            except Exception as exc:
                print(f"  Warning: could not fetch {url}: {exc}")
                out.unlink(missing_ok=True)
        if fetched == 0:
            print("  Warning: no installer images fetched; boot menu will only offer the live session")

    def _generate_preseed_file(self, preseed_path: Path):
        """Generate a preseed configuration file for automated installation."""
        hostname = self.cfg.get("hostname") or self.cfg["distro_name"].lower().replace(' ', '-')
        locale = self.cfg["locale"]
        timezone = self.cfg["timezone"]
        username = self.cfg.get("live_username") or "user"
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
        icon_name = self.cfg['hostname']
        desktop_content = f'''[Desktop Entry]
Type=Application
Name=Install {distro_name}
GenericName=System Installer
Comment=Install {distro_name} on this computer
TryExec=debian-installer-launcher
Exec=debian-installer-launcher
Icon={icon_name}
Terminal=false
StartupNotify=true
Categories=Qt;System;
Keywords=install;installer;system;{distro_name.lower()};
'''
        # Create in chroot for installed system
        apps_dir = self.chroot / "usr" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_filename = f"install-{self.cfg['hostname']}.desktop"
        (apps_dir / desktop_filename).write_text(desktop_content)

        # Also create in skel for new users
        skel_apps = self.chroot / "etc" / "skel" / "Desktop"
        skel_apps.mkdir(parents=True, exist_ok=True)
        installer_desktop = skel_apps / desktop_filename
        installer_desktop.write_text(desktop_content)
        installer_desktop.chmod(0o755)

        print("  Created installer desktop launcher")

    # -------------------------------------------------------------------------
    # User Accounts
    # -------------------------------------------------------------------------

    def configure_users(self):
        """Create live user and set passwords."""
        self._set_password("root", self.cfg.get("root_password"))
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

            desktop_groups = self.cfg["user_groups"]
            for group in desktop_groups:
                self._chroot(["groupadd", "--force", group])
            if desktop_groups:
                self._chroot(["usermod", "--append", "--groups", ",".join(desktop_groups), username])

            self._set_password(username, self.cfg.get("live_user_password"))


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
            if self.cfg["os_release"]:
                release = self.chroot / "usr/lib/os-release"
                original = release.read_text() if release.exists() else ""
                fields = self.cfg["os_release"]
                lines = [line for line in original.splitlines() if line.partition("=")[0] not in fields]
                for key, value in fields.items():
                    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
                    lines.append(f'{key}="{escaped}"')
                release.parent.mkdir(parents=True, exist_ok=True)
                release.write_text("\n".join(lines) + "\n")
                etc_release = self.chroot / "etc/os-release"
                etc_release.unlink(missing_ok=True)
                etc_release.symlink_to("../usr/lib/os-release")
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

            (self.chroot / "etc/default/locale").write_text(f"LANG={locale}\n")

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
            (self.chroot / "usr/sbin/policy-rc.d").unlink(missing_ok=True)
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
            machine_id.unlink(missing_ok=True)
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
            def kernel_version(path):
                return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", path.name)]

            vmlinuz_list = sorted((self.chroot / "boot").glob("vmlinuz-*"), key=kernel_version)
            initrd_list = [self.chroot / "boot" / ("initrd.img-" + k.name.removeprefix("vmlinuz-")) for k in vmlinuz_list]
            if any(not p.is_file() for p in initrd_list):
                raise BuildError("Kernel is missing its matching initramfs")
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
                    "-noappend",
                    "-e",
                    "boot",
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
            boot_append = self.cfg.get("boot_append", "quiet").strip()
            username = self.cfg.get("live_username")
            if username:
                boot_append += f" username={username}"
            else:
                boot_append += " live-config.nocomponents=user-setup"

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
    linux  /live/vmlinuz boot=live components {boot_append} debug
    initrd /live/initrd
}}
'''

            # Branded installer boot entries, using the d-i netboot images
            # shipped on the ISO (when they were fetched successfully).
            install_dir = self.iso_root / "install"
            preseed_path = f"/preseed/{self.cfg['hostname']}.preseed"
            preseed_arg = f"file={preseed_path}" if (self.iso_root / "preseed").is_dir() else ""
            if preseed_arg:
                preseed_arg = f"{preseed_arg} auto=true priority=high"
            installer_entries = ""
            if (install_dir / "gtk" / "vmlinuz").is_file() and (install_dir / "gtk" / "initrd.gz").is_file():
                installer_entries += f'''\
menuentry "Install {distro} {version}" {{
    linux  /install/gtk/vmlinuz {preseed_arg} quiet
    initrd /install/gtk/initrd.gz
}}

'''
            if (install_dir / "vmlinuz").is_file() and (install_dir / "initrd.gz").is_file():
                installer_entries += f'''\
menuentry "Install {distro} {version} (text mode)" {{
    linux  /install/vmlinuz {preseed_arg}
    initrd /install/initrd.gz
}}

'''
            grub_cfg += installer_entries

            # Brand the boot menu with the distribution background image.
            background = self.cfg.get("grub_background")
            if background:
                try:
                    shutil.copy2(background, self.iso_root / "boot" / "grub" / "background.png")
                    grub_cfg += (
                        "if background_image /boot/grub/background.png ; then\n"
                        "    set color_normal=white/black\n"
                        "    set color_highlight=black/light-gray\n"
                        "fi\n"
                    )
                except OSError as exc:
                    print(f"  Warning: could not install GRUB background: {exc}")

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

    def _make_grub_image(self, platform, output, early_config, requested_modules):
        """Copy loadable modules and create a core image for one GRUB platform."""
        library = self._find_grub_lib(platform)
        destination = self.iso_root / "boot/grub" / platform
        destination.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.mod", "*.lst"):
            for source in library.glob(pattern):
                shutil.copy2(source, destination / source.name)
        modules = available_grub_modules(library, requested_modules)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg") as config:
            config.write(early_config)
            config.flush()
            run([
                "grub-mkimage", "--format", platform,
                "--output", str(output), "--prefix", "/boot/grub",
                "--config", config.name, "--directory", str(library), *modules,
            ])
        return library

    def _bios_boot_arguments(self, early_config):
        """Preserve GRUB's complete El Torito loader, followed by its core image."""
        grub_dir = self.iso_root / "boot/grub"
        core = grub_dir / "core_bios.img"
        library = self._make_grub_image(
            "i386-pc", core, early_config, GRUB_BIOS_MODULES
        )
        loader = library / "cdboot.img"
        (grub_dir / "bios.img").write_bytes(loader.read_bytes() + core.read_bytes())
        core.unlink()
        hybrid_mbr = library / "boot_hybrid.img"
        if not hybrid_mbr.is_file():
            raise BuildError("boot_hybrid.img not found; install grub-pc-bin")
        return [
            "-eltorito-boot", "boot/grub/bios.img", "-no-emul-boot",
            "-boot-load-size", "4", "-boot-info-table", "--grub2-boot-info",
            "--grub2-mbr", str(hybrid_mbr),
        ]

    def _efi_boot_arguments(self, early_config):
        """Create the removable EFI binary and its FAT boot partition."""
        grub_dir = self.iso_root / "boot/grub"
        binary_name = GRUB_EFI_BINARY[self.arch]
        binary = grub_dir / binary_name
        self._make_grub_image(
            GRUB_EFI_FORMAT[self.arch], binary, early_config, GRUB_EFI_MODULES
        )
        removable = self.iso_root / "EFI/BOOT"
        removable.mkdir(parents=True, exist_ok=True)
        shutil.copy2(binary, removable / binary_name)

        esp = grub_dir / "efi.img"
        with esp.open("wb") as image:
            image.truncate(16 * 1024 * 1024)
        run(["mkfs.vfat", "-F", "16", "-n", "GRUB_EFI", str(esp)])
        run(["mmd", "-i", str(esp), "::/EFI", "::/EFI/BOOT"])
        run(["mcopy", "-i", str(esp), str(binary), f"::/EFI/BOOT/{binary_name}"])
        # Only start a second El Torito entry when a BIOS entry precedes it.
        arguments = ["-eltorito-alt-boot"] if self.arch == "amd64" else []
        return arguments + [
            "-e", "boot/grub/efi.img", "-no-emul-boot", "-isohybrid-gpt-basdat",
        ]

    def build_iso(self):
        """Assemble the image and publish it only after xorriso succeeds."""
        with build_step("Building ISO image"):
            volume = self.cfg["iso_volume_id"]
            early_config = (
                f'search --no-floppy --set=root --label "{volume}"\n'
                'if [ -z "$root" ]; then\n'
                '    search --no-floppy --set=root --file /live/filesystem.squashfs\n'
                'fi\n'
                'set prefix=($root)/boot/grub\n'
            )
            arguments = [
                "xorriso", "-as", "mkisofs", "-iso-level", "3", "-volid", volume,
                "-full-iso9660-filenames", "-rational-rock", "-joliet",
            ]
            if self.arch == "amd64":
                arguments += self._bios_boot_arguments(early_config)
            arguments += self._efi_boot_arguments(early_config)
            iso_name = self.cfg.get("iso_filename") or (
                f"{self.cfg['distro_name']}-{self.cfg['version']}-{self.arch}.iso"
            )
            output = self.outdir / iso_name
            if output.exists():
                raise BuildError(f"Output already exists: {output}")
            with tempfile.NamedTemporaryFile(
                dir=self.outdir, prefix=f".{iso_name}.", suffix=".partial"
            ) as temporary:
                partial = Path(temporary.name)
                run([*arguments, "-output", str(partial), str(self.iso_root)])
                digest = hashlib.sha256()
                with partial.open("rb") as image:
                    for chunk in iter(lambda: image.read(1024 * 1024), b""):
                        digest.update(chunk)
                partial.chmod(0o644)
                # A hard link publishes atomically and refuses a concurrent overwrite.
                os.link(partial, output)
                checksum = output.with_suffix(".iso.sha256")
                checksum.write_text(f"{digest.hexdigest()}  {output.name}\n")
            print(f"\n  ISO written to: {output}")

    # -------------------------------------------------------------------------
    # Helper Methods
    # -------------------------------------------------------------------------

    def assert_unmounted(self):
        """Catch mounts created by hooks as well as the ones tracked by this builder."""
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            mountpoint = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[4])
            path = Path(mountpoint)
            if path == self.workdir or self.workdir in path.parents:
                raise BuildError(f"Mount remains in work directory: {path}; files retained")

    def _chroot(self, cmd, extra_env=None, **kwargs):
        """Execute a command inside the chroot."""
        env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C", **(extra_env or {})}
        run(["chroot", str(self.chroot)] + cmd, env=env, **kwargs)

    # -------------------------------------------------------------------------
    # Main Build Pipeline
    # -------------------------------------------------------------------------

    def build(self):
        """Execute the full build pipeline."""
        succeeded = False
        try:
            self.prepare_dirs()
            self.run_debootstrap()
            try:
                self._mount_pseudo_filesystems()
                self.pre_chroot_scripts()
                self.configure_apt()
                self.install_packages()
                self.setup_debian_installer()
                self.configure_users()
                self.configure_system()
                self.post_install_scripts()
                for action, units in self.cfg["services"].items():
                    if units:
                        self._chroot(["systemctl", action, *units])
                self._chroot(["update-initramfs", "-u", "-k", "all"])
                self.cleanup_chroot()
            finally:
                self._unmount_pseudo_filesystems()
            self.export_kernel_and_initrd()
            self.assert_unmounted()
            self.build_squashfs()
            self.write_boot_configs()
            self.build_iso()
            succeeded = True
            print("\n✓ Build complete.")
        finally:
            if succeeded and self._owns_workdir and not self._mounts and not self.keep_workdir:
                self.assert_unmounted()
                shutil.rmtree(self.workdir)
            elif self._owns_workdir:
                print(f"Working files retained: {self.workdir}", file=sys.stderr)


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
    parser.add_argument("--validate", action="store_true", help="Validate config without root or build tools")
    args = parser.parse_args()
    cfg = load_config(args.config)
    if args.validate:
        print(f"Configuration valid: {args.config}")
        return
    require_root()
    for tool in HOST_BUILD_TOOLS:
        require_tool(tool)
    native_arch = run(["dpkg", "--print-architecture"], capture_output=True).stdout.strip()
    if native_arch != cfg["architecture"]:
        raise BuildError(f"Use a native {cfg['architecture']} host/container; detected {native_arch}")
    workdir = args.workdir or tempfile.mkdtemp(prefix="live_iso_build_")
    LiveBuilder(cfg, workdir, args.outdir, keep_workdir=args.keep_workdir).build()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBuild interrupted; working files retained.", file=sys.stderr)
        sys.exit(130)
    except (BuildError, OSError) as e:
        print(f"\n✗ Build failed: {e}", file=sys.stderr)
        sys.exit(1)
