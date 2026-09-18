"""Opt-in GRUB boot smoke test with real host tools; no root or kernel needed."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from build import LiveBuilder


@unittest.skipUnless(os.environ.get('RUN_BOOT_SMOKE') == '1', 'set RUN_BOOT_SMOKE=1 for real ISO/VM checks')
class BootSmokeTest(unittest.TestCase):
    def test_grub_boots_from_iso(self):
        for command in ('grub-mkimage', 'mkfs.vfat', 'mmd', 'mcopy', 'xorriso', 'qemu-system-x86_64'):
            self.assertIsNotNone(shutil.which(command), f'Missing {command}')
        with tempfile.TemporaryDirectory(prefix='live-builder-test-') as temporary:
            root = Path(temporary)
            builder = LiveBuilder({
                'architecture': 'amd64', 'iso_volume_id': 'SMOKE',
                'distro_name': 'Smoke', 'version': '1',
            }, root / 'work', root / 'out')
            builder.prepare_dirs()
            (builder.iso_root / 'live/filesystem.squashfs').write_bytes(b'boot fixture')
            (builder.iso_root / 'boot/grub/grub.cfg').write_text(
                'serial --unit=0 --speed=115200\nterminal_output serial\n'
                'echo LIVE_BUILDER_GRUB_OK\nhalt\n'
            )
            builder.build_iso()
            command = [
                'qemu-system-x86_64', '-machine', 'accel=tcg', '-m', '256',
                '-display', 'none', '-serial', 'stdio', '-monitor', 'none',
                '-no-reboot', '-cdrom', str(root / 'out/Smoke-1-amd64.iso'),
            ]
            self.assert_boot_marker(command)
            # When installed, verify the UEFI entry with matching code/variable images.
            for suffix in ('_4M', ''):
                code = Path(f'/usr/share/OVMF/OVMF_CODE{suffix}.fd')
                variables = Path(f'/usr/share/OVMF/OVMF_VARS{suffix}.fd')
                if code.is_file() and variables.is_file():
                    writable_vars = root / 'vars.fd'
                    shutil.copy2(variables, writable_vars)
                    self.assert_boot_marker(command + [
                        '-drive', f'if=pflash,format=raw,readonly=on,file={code}',
                        '-drive', f'if=pflash,format=raw,file={writable_vars}',
                    ])
                    break
            else:
                if os.environ.get('REQUIRE_UEFI_SMOKE') == '1':
                    self.fail('OVMF firmware is required for this smoke test')

    def assert_boot_marker(self, command):
        try:
            result = subprocess.run(command, capture_output=True, timeout=30)
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b'') + (exc.stderr or b'')
        self.assertIn(b'LIVE_BUILDER_GRUB_OK', output, output.decode(errors='replace'))
