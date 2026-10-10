# Developed with ChatGPT / Codex AI assistance, directed by dadtrick.
# See AI_DISCLOSURE.md at the repository root for attribution and test limits.
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def test_symlinked_child_destination_cannot_overwrite_vita3k_data(self):
        for filename in ('psvita_launcher.py', 'config.ini', 'HELP.txt', '.psvita-launcher-manager'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                userdata = root / 'userdata'
                app = userdata / 'system/psvita_launcher'
                app.mkdir(parents=True)
                marker = app / '.psvita-launcher-manager'
                marker.write_text('Vita Launcher Manager\n')
                protected = userdata / 'saves/psvita/game-data'
                protected.parent.mkdir(parents=True)
                protected.write_text('Vita data must stay unchanged')
                child = app / filename
                if child.exists():
                    child.unlink()
                child.symlink_to(protected)
                dispatcher = root / 'dispatcher'
                dispatcher.write_text('#!/bin/sh\nexit 0\n')
                dispatcher.chmod(0o755)
                script = (SOURCE / 'install.sh').read_text()
                script = script.replace('/userdata', str(userdata)).replace(
                    '/usr/bin/batocera-preupdate-gamelists-hook', str(dispatcher))
                installer = root / 'install.sh'
                installer.write_text(script)
                mockbin = root / 'commands'
                mockbin.mkdir()
                for name, body in {'id': 'echo 0', 'batocera-services': 'exit 0'}.items():
                    command = mockbin / name
                    command.write_text('#!/bin/sh\n' + body + '\n')
                    command.chmod(0o755)
                env = dict(os.environ, PATH=str(mockbin) + os.pathsep + os.environ['PATH'])
                result = subprocess.run(['bash', str(installer), '--cli-only'], env=env,
                                        capture_output=True, text=True, timeout=15)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('symlinked install destination', result.stderr)
                self.assertEqual(protected.read_text(), 'Vita data must stay unchanged')


if __name__ == '__main__':
    unittest.main()
