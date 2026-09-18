# Building Debian-family live images

`build.py` consumes a JSON manifest and assembles a live ISO. PersisOS branding,
packages and hooks live in its manifests and `hooks/`, not in the builder.
Python 3.9 or newer is required; no third-party Python modules are needed.

## Start with another distribution

Copy `examples/debian-minimal.json` or `examples/ubuntu-minimal.json`. Set the
upstream suite, bootstrap mirror, APT components and sources, kernel package,
and your additional packages. The Ubuntu example uses Debian's `live-boot`
implementation available in Ubuntu's universe repository, not Casper.
The examples are starting points, not fully tested distribution releases.

```sh
python3 build.py examples/debian-minimal.json --validate
sudo python3 build.py examples/debian-minimal.json --workdir build-debian --outdir output-debian
```

Validation does not require root, build tools, or network access. It checks
configuration types, names, paths and contradictions; it does not check remote
package availability. Actual builds run APT's dependency simulation before
installing packages. Repository and package errors include the failing phase.

The host must be Linux with working mounts and chroots, running as root. Use a
native amd64, arm64 or armhf host/container matching the manifest. amd64 images
include BIOS and UEFI; ARM images target machines supporting GRUB UEFI and the
selected kernel, not board-specific boot firmware. Cross-architecture bootstrap
and Secure Boot signing are not implemented. Other architectures need additional
kernel and GRUB mappings and boot assembly support.

On a Debian amd64 host, install:

```sh
sudo apt-get install debootstrap debian-archive-keyring ca-certificates \
  squashfs-tools grub2-common grub-pc-bin grub-efi-amd64-bin \
  xorriso mtools dosfstools python3
```

For ARM use the matching `grub-efi-arm64-bin` or `grub-efi-arm-bin` package instead
of the amd64/BIOS GRUB packages. Include `/usr/sbin` in root's PATH. A derivative
needs a debootstrap suite script and archive signing key available on the host;
for Ubuntu use a suitable Ubuntu build host or install its archive keyring.
`debootstrap_script` and `debootstrap_keyring` can explicitly select these files.
No signature verification bypass is provided.

This builds systems using the Debian live-boot/initramfs-tools layout. A derivative
with another init system can replace `live_packages` and leave `services` empty,
then configure its init system in hooks. Changing a distribution name alone does
not make an incompatible bootstrap suite, kernel or live boot stack compatible.

## Manifest reference

Required values:

| Key | Meaning |
| --- | --- |
| `distro_name`, `version` | Display name and release version, both strings |
| `suite` | Upstream debootstrap release, such as `trixie` or `noble` |
| `apt_mirror` | Bootstrap mirror URL |
| `packages` | Additional package names; may be empty |

Optional values:

| Key | Default and behavior |
| --- | --- |
| `architecture` | `amd64`; also `arm64`, `armhf` |
| `apt_components` | `["main"]`; also passed to debootstrap |
| `apt_sources` | One base repository using mirror/suite/components; supply every desired updates/security/third-party source explicitly |
| `kernel_package` | Debian kernel metapackage for the architecture; override for derivatives |
| `live_packages` | Replaces the entire default list: live-boot, live-config, live-config-systemd, live-boot-initramfs-tools, initramfs-tools, tzdata, systemd-sysv, sudo, locales |
| `exclude_packages` | Negative APT pins preventing package selection; cannot overlap explicitly requested packages |
| `install_recommends` | `false`; applies to both simulation and installation |
| `debootstrap_variant` | Omitted by default; normally `minbase` or `buildd` |
| `debootstrap_script`, `debootstrap_keyring` | Existing host file paths, relative to the manifest or absolute |
| `hostname` | A DNS-safe name derived from the display name |
| `locale`, `timezone` | `en_US.UTF-8`, `UTC` |
| `live_username` | `user`; null disables live user creation |
| `live_user_password`, `root_password` | Null locks the account password; empty string deletes it; otherwise sets the supplied password |
| `user_groups` | sudo, audio, video, plugdev, netdev |
| `services` | Object with `enable`, `disable`, `mask` lists of systemd units; failures stop the build |
| `os_release` | Uppercase field/value overrides in `/usr/lib/os-release`; unspecified upstream fields remain intact |
| `pre_chroot_scripts` | Host hooks after bootstrap, before APT update; `ROOTFS` is an absolute path |
| `post_install_scripts` | Chroot hooks after packages, users and system configuration |
| `boot_append` | `quiet`; kernel arguments for live entries |
| `squashfs_compression` | `xz`; also zstd, gzip, lzo, lz4 when supported by host tools and target kernel |
| `iso_volume_id` | Derived label, at most 32 letters/digits/underscores |
| `iso_filename` | Derived safe `.iso` filename |
| `installer_enabled` | `false`; opt into Debian-specific installer launcher and preseed generation |
| `installer_preseed_options` | `partition_method`, `tasks`, `include_packages` string overrides |

Legacy `arch` and `debian_distro` aliases remain supported; conflicting aliases
are rejected. Replace legacy `security_mirror` with explicit `apt_sources`.
Unknown keys are errors, so misspelled settings cannot silently disappear.
The old unused `splash` key should be replaced by `boot_append`.

The preseed file is exported alongside the ISO's live filesystem, but is not
passed automatically to the installer launcher. Review its partitioning settings
before explicitly supplying it to an installer. Installing the launcher alone
does not provide a complete installer for every derivative.

Null passwords lock password authentication; they do not disable live session
autologin or sudo configuration. Set `noautologin` in `boot_append` when needed.
PersisOS manifests retain their existing published live passwords. Never use
these defaults for a production installed system.

## Hooks and system configuration

Hook entries may be paths or inline scripts. Paths resolve relative to the JSON
manifest. Host hooks also run with that directory as their working directory,
so invoking the builder from another directory does not break asset copies.
Chroot scripts are copied into temporary files and removed even on failure.
Hooks execute with Bash and `-eu`; they are trusted code executed as root.
Host hooks can install third-party repository keys before the first APT update.

Prefer `services` and `os_release` settings for common configuration. Use hooks
for distribution-specific files and applications. Chroot services are prevented
from starting during package installation. Initramfs images are regenerated after
hooks, so installed configuration is included. The selected kernel is exported
with its matching initramfs. Package recommendations are disabled by default.

## Workspaces, output and failures

Use an empty dedicated work directory, separate from the output directory. A
nonempty work directory or overlapping paths are rejected. Failed builds retain
the workspace for inspection; there is no automatic resume. Unmount any remaining
mounts before manually removing a failed workspace, and use a fresh work directory
for the next attempt. Unmount failures stop image creation and cleanup.

Successful builds remove working files unless `--keep-workdir` is set, including
when the builder chose a temporary work directory. The final output is an ISO
and an `.iso.sha256` checksum. Failed assembly does not publish a partial ISO.
Existing ISO names are refused; choose a different name/directory for a rebuild.
Repository contents and timestamps are not pinned, so builds are not guaranteed
byte-for-byte reproducible.

CI uses native architecture runners and a shared Debian build script. Unit tests
and manifest validation run before ISO builds. Build logs are uploaded even after
failure; successful image artifacts and releases include checksums.

## Verification

```sh
python3 -m unittest discover -s tests -v
for config in PersisOS*.json examples/*.json; do
  python3 build.py "$config" --validate
done
```

A full build and BIOS/UEFI VM boot should be checked before distributing an image.
Set `RUN_BOOT_SMOKE=1` to also assemble and boot a GRUB fixture in QEMU. This
requires the amd64 GRUB modules, QEMU and ISO tools; OVMF enables the UEFI check.
CI requires both BIOS and UEFI checks for amd64. This fixture contains no OS.

Unit tests validate configuration and assembly behavior, not the availability of
all packages or desktop functionality. The minimal examples lock passwords;
choose a temporary test password or an appropriate autologin setup for VM testing.
