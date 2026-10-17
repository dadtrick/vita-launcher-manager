# Developed with ChatGPT / Codex AI assistance, directed by dadtrick.
# See AI_DISCLOSURE.md at the repository root for attribution and test limits.
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def make_source(self, root):
        (root / "tools").mkdir()
        shutil.copy2(SOURCE / "tools/build-release.sh", root / "tools/build-release.sh")
        (root / "VERSION").write_text("1.7.3\n", encoding="utf-8")
        (root / "psvita_launcher.py").write_text(
            'import sys\n'
            'if sys.argv[1:] != ["--version"]:\n'
            '    raise SystemExit("Only the --version API should be called")\n'
            'print("1.7.3")\n',
            encoding="utf-8",
        )
        (root / "install.sh").write_text(
            '#!/bin/bash\nVERSION="1.7.3"\nexit 99\n', encoding="utf-8"
        )
        (root / "dist").mkdir()
        (root / "dist/previous-release.zip").write_bytes(b"keep this release")

    def run_builder(self, root):
        result = subprocess.run(
            ["bash", str(root / "tools/build-release.sh"), "--check-metadata"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(
            (root / "dist/previous-release.zip").read_bytes(), b"keep this release"
        )
        return result

    def test_matching_versions_can_be_checked_through_cli_without_building(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_source(root)
            result = self.run_builder(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Release metadata OK: 1.7.3", result.stdout)
            self.assertEqual(len(list((root / "dist").iterdir())), 1)

    def test_each_version_mismatch_stops_before_replacing_existing_release(self):
        for filename in ("VERSION", "psvita_launcher.py", "install.sh"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.make_source(root)
                path = root / filename
                path.write_text(path.read_text().replace("1.7.3", "1.7.4"))
                result = self.run_builder(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("versions do not match", result.stderr)

    def test_malformed_metadata_stops_before_replacing_existing_release(self):
        cases = (
            ("VERSION", "not-a-version\n"),
            ("psvita_launcher.py", 'print("invalid-version")\n'),
            ("install.sh", 'VERSION=1.7.3\n'),
            ("install.sh", 'VERSION="1.7.3"\nVERSION="1.7.4"\n'),
            ("install.sh", 'VERSION="$(exit 99)"\n'),
        )
        for filename, contents in cases:
            with self.subTest(filename=filename, contents=contents), \
                    tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.make_source(root)
                (root / filename).write_text(contents, encoding="utf-8")
                result = self.run_builder(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("must use X.Y.Z", result.stderr)

    def test_missing_metadata_stops_before_replacing_existing_release(self):
        for filename in ("VERSION", "psvita_launcher.py", "install.sh"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                self.make_source(root)
                (root / filename).unlink()
                result = self.run_builder(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertTrue(result.stderr)


if __name__ == "__main__":
    unittest.main()
