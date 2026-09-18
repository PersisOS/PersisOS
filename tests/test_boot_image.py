"""Guard against corrupting the El Torito loader during ISO assembly."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build import LiveBuilder


class BiosImageTest(unittest.TestCase):
    def test_preserves_complete_cd_loader_and_core(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            modules = root / 'modules'
            modules.mkdir()
            # Distinct bytes at 510 and beyond 512 catch MBR-style corruption.
            loader = bytes(range(256)) * 8
            core = b'GRUB core payload' * 256
            (modules / 'cdboot.img').write_bytes(loader)
            (modules / 'boot_hybrid.img').write_bytes(b'MBR')
            builder = LiveBuilder({
                'architecture': 'amd64', 'iso_volume_id': 'TEST',
                'distro_name': 'Test', 'version': '1',
            }, str(root / 'work'), str(root / 'out'))
            builder.prepare_dirs()

            def fake_run(cmd, **kwargs):
                if cmd[0] == 'xorriso':
                    Path(cmd[cmd.index('-output') + 1]).write_bytes(b'ISO')
                if cmd[0] == 'grub-mkimage':
                    Path(cmd[cmd.index('--output') + 1]).write_bytes(core)

            with patch.object(builder, '_find_grub_lib', return_value=modules), \
                 patch('build.available_grub_modules', return_value=[]), \
                 patch('build.run', side_effect=fake_run):
                builder.build_iso()
            actual = (builder.iso_root / 'boot/grub/bios.img').read_bytes()
            self.assertEqual(actual, loader + core)


if __name__ == '__main__':
    unittest.main()
