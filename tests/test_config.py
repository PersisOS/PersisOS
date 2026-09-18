"""Configuration and failure-safety tests requiring no privileged operations."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build import BuildError, LiveBuilder, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / 'image.json'
        self.base = dict(distro_name='Example', version='1', suite='custom',
                         apt_mirror='https://archive.example/distro', packages=[],
                         kernel_package='linux-generic', apt_components=['main', 'universe'])

    def load(self, **overrides):
        self.config.write_text(json.dumps({**self.base, **overrides}))
        return load_config(str(self.config))

    def test_derivative_does_not_inherit_debian_repositories(self):
        cfg = self.load()
        self.assertEqual(cfg['apt_sources'], ['deb https://archive.example/distro custom main universe'])
        self.assertEqual(cfg['kernel_package'], 'linux-generic')
        self.assertFalse(cfg['installer_enabled'])

    def test_rejects_malformed_config(self):
        for overrides in ({'packages': 'curl'}, {'installer_enabled': 'false'},
                          {'live_username': 'root'}, {'timezone': '../../etc'},
                          {'iso_filename': '../x.iso'}, {'typo': True},
                          {'distro_name': 'Bad"; reboot'}, {'root_password': 'x\ny'}):
            with self.subTest(overrides=overrides), self.assertRaises(BuildError):
                self.load(**overrides)

    def test_hooks_resolve_relative_to_manifest(self):
        (self.root / 'hook.sh').write_text('true\n')
        self.load(post_install_scripts=['hook.sh'])
        with self.assertRaises(BuildError):
            self.load(post_install_scripts=['missing.sh'])

    def test_nonempty_directory_is_preserved_on_failure(self):
        work = self.root / 'work'
        work.mkdir()
        sentinel = work / 'important'
        sentinel.write_text('keep')
        builder = LiveBuilder(self.load(), work, self.root / 'out')
        with self.assertRaises(BuildError):
            builder.build()
        self.assertEqual(sentinel.read_text(), 'keep')

    def test_failed_unmount_is_tracked(self):
        builder = LiveBuilder(self.load(), self.root / 'work', self.root / 'out')
        mount = builder.chroot / 'dev'
        builder._mounts = [mount]
        with patch('build.run', side_effect=BuildError('busy')), self.assertRaises(BuildError):
            builder._unmount_pseudo_filesystems()
        self.assertEqual(builder._mounts, [mount])

    def test_partial_mount_failure_unwinds_only_mounted_paths(self):
        builder = LiveBuilder(self.load(), self.root / 'work', self.root / 'out')
        with patch('build.run', side_effect=[None, BuildError('mount failed')]):
            with self.assertRaises(BuildError):
                builder._mount_pseudo_filesystems()
        self.assertEqual(builder._mounts, [builder.chroot / 'proc'])
        with patch('build.run') as command:
            builder._unmount_pseudo_filesystems()
        command.assert_called_once_with(['umount', str(builder.chroot / 'proc')])

    def test_exclusions_are_enforced_by_apt_pin(self):
        builder = LiveBuilder(self.load(exclude_packages=['unwanted']), self.root / 'work', self.root / 'out')
        for sub in ('apt.conf.d', 'preferences.d'):
            (builder.chroot / 'etc/apt' / sub).mkdir(parents=True)
        with patch.object(builder, '_chroot'):
            builder.configure_apt()
        self.assertIn('Pin-Priority: -1', (builder.chroot / 'etc/apt/preferences.d/live-builder').read_text())
        self.assertIn('"false"', (builder.chroot / 'etc/apt/apt.conf.d/99-live-builder').read_text())

    def test_all_manifests_validate(self):
        repo = Path(__file__).resolve().parents[1]
        for path in [*repo.glob('PersisOS*.json'), *repo.glob('examples/*.json')]:
            with self.subTest(path=path.name):
                load_config(str(path))

    def test_invalid_types_produce_build_errors(self):
        for key in ('architecture', 'kernel_package', 'hostname', 'iso_volume_id',
                    'iso_filename', 'services', 'installer_preseed_options', 'os_release'):
            for value in ([], {}, 123, None):
                if key in ('services', 'installer_preseed_options', 'os_release') and value == {}:
                    continue
                with self.subTest(key=key, value=value), self.assertRaises(BuildError):
                    self.load(**{key: value})

    def test_configure_system_escapes_identity_and_preserves_upstream(self):
        cfg = self.load(os_release={'NAME': 'Example "OS" $HOME', 'ID': 'example'})
        builder = LiveBuilder(cfg, self.root / 'work', self.root / 'out')
        for sub in ('etc/default', 'usr/lib', 'usr/share/zoneinfo'):
            (builder.chroot / sub).mkdir(parents=True)
        (builder.chroot / 'usr/share/zoneinfo/UTC').write_bytes(b'zone fixture')
        (builder.chroot / 'usr/lib/os-release').write_text('ID=debian\nVERSION_CODENAME=trixie\n')
        with patch.object(builder, '_chroot'):
            builder.configure_system()
        release = (builder.chroot / 'usr/lib/os-release').read_text()
        self.assertIn('VERSION_CODENAME=trixie', release)
        self.assertIn('NAME="Example \\"OS\\" \\$HOME"', release)
        self.assertNotIn('ID=debian', release)
        self.assertEqual((builder.chroot / 'etc/default/locale').read_text(), 'LANG=en_US.UTF-8\n')

    def test_exports_newest_kernel_with_matching_initramfs(self):
        builder = LiveBuilder(self.load(), self.root / 'work', self.root / 'out')
        builder.prepare_dirs()
        boot = builder.chroot / 'boot'
        boot.mkdir()
        for version in ('6.9.0', '6.12.0'):
            (boot / f'vmlinuz-{version}').write_text(version)
            (boot / f'initrd.img-{version}').write_text('initrd-' + version)
        builder.export_kernel_and_initrd()
        self.assertEqual((builder.iso_root / 'live/vmlinuz').read_text(), '6.12.0')
        self.assertEqual((builder.iso_root / 'live/initrd').read_text(), 'initrd-6.12.0')
        (boot / 'initrd.img-6.12.0').unlink()
        with self.assertRaises(BuildError):
            builder.export_kernel_and_initrd()

    def test_no_live_user_still_locks_root(self):
        builder = LiveBuilder(self.load(live_username=None), self.root / 'work', self.root / 'out')
        with patch.object(builder, '_chroot') as command:
            builder.configure_users()
        command.assert_called_once_with(['passwd', '--lock', 'root'])

    def test_boot_entries_retain_username_and_login_policy(self):
        builder = LiveBuilder(self.load(live_username='admin', boot_append='noautologin'),
                              self.root / 'work', self.root / 'out')
        builder.prepare_dirs()
        builder.write_boot_configs()
        config = (builder.iso_root / 'boot/grub/grub.cfg').read_text()
        self.assertEqual(config.count('username=admin'), 3)
        self.assertEqual(config.count('noautologin'), 3)
