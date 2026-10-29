"""Exercise installer progress without touching disks or requiring root."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


INSTALLER = (Path(__file__).resolve().parents[1] /
             'assets/server/usr/local/bin/install-persisos').read_text()
PROGRESS = INSTALLER[INSTALLER.index('step() {'):INSTALLER.index('run_logged() {')]
COPY = INSTALLER[INSTALLER.index('rsync -aHAX'):INSTALLER.index("\nstep 80")]


class ServerInstallerProgressTests(unittest.TestCase):
    def run_shell(self, body):
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                ['bash', '-c', 'set -Eeuo pipefail\n'
                 'PROGRESS_DIR=$TEST_DIR; LOG=$TEST_DIR/log; TARGET=$TEST_DIR\n'
                 'DISK=/dev/example; HOSTNAME=example\n' + PROGRESS + body],
                env={**os.environ, 'TEST_DIR': directory},
                text=True, capture_output=True, timeout=10)

    def test_quiet_stage_keeps_updating(self):
        result = self.run_shell('''
step 7 'Formatting partitions...'
count=0
sleep() { count=$((count + 1)); if ((count == 2)); then touch "$PROGRESS_DIR/stop"; fi; }
progress_stream
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('Formatting partitions...'), 2)
        self.assertIn('Working.', result.stdout)
        self.assertIn('Working..', result.stdout)

    def test_copy_percentage_and_empty_update(self):
        result = self.run_shell('''
step 15 'Copying...'
printf '50\\n' > "$PROGRESS_DIR/copy"
count=0
sleep() {
    count=$((count + 1))
    : > "$PROGRESS_DIR/copy"
    if ((count == 2)); then touch "$PROGRESS_DIR/stop"; fi
}
progress_stream
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count('50% of file data copied'), 2)
        self.assertIn('XXX\n47\n', result.stdout)

    def test_rsync_progress_and_failure_propagation(self):
        for status in (0, 23):
            with self.subTest(status=status):
                result = self.run_shell('''
rsync() { printf '\\r 1,024  50%%%%  1MB/s\\r 2,048  100%%%%  1MB/s\\n'; return %s; }
fail() { echo "$*" >&2; exit 1; }
''' % status + COPY + '\ncat "$PROGRESS_DIR/copy" "$LOG"\n')
                self.assertEqual(result.returncode, 0 if status == 0 else 1,
                                 result.stderr)
                if status == 0:
                    self.assertTrue(result.stdout.startswith('100\n'))
                    self.assertIn('1,024', result.stdout)
                else:
                    self.assertIn('Could not copy', result.stderr)


if __name__ == '__main__':
    unittest.main()
