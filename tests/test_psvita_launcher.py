import csv
import contextlib
import io
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("psvita_launcher", ROOT / "psvita_launcher.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def make_sfo(title_id: str, title: str) -> bytes:
    items = [("TITLE_ID", title_id), ("TITLE", title)]
    keys = bytearray()
    data = bytearray()
    entries = []
    for key, value in items:
        key_off = len(keys)
        keys += key.encode() + b"\0"
        value_b = value.encode("utf-8") + b"\0"
        value_off = len(data)
        data += value_b
        entries.append((key_off, 0x0204, len(value_b), len(value_b), value_off))
    key_start = 20 + 16 * len(entries)
    data_start = key_start + len(keys)
    header = b"\0PSF" + struct.pack("<4I", 0x101, key_start, data_start, len(entries))
    body = b"".join(struct.pack("<HHIII", *e) for e in entries)
    return header + body + keys + data


class LauncherTests(unittest.TestCase):
    def test_creation_failure_returns_error_and_tracks_successful_launchers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source"
            for title_id in ("PCSE00001", "PCSE00002"):
                (source / title_id).mkdir(parents=True)
            config = root / "config.ini"
            config.write_text(
                "[paths]\n"
                + "\n".join(f"{key} = {root / value}" for key, value in {
                    "source": "source", "output": "output", "database": "db.tsv",
                    "unknown_log": "unknown.txt", "lock_file": "lock",
                    "managed_state": "managed.tsv", "title_cache": "cache.tsv",
                }.items()) + "\n", encoding="utf-8"
            )
            original_touch = Path.touch

            def fail_one(path, *args, **kwargs):
                if "PCSE00001" in path.name:
                    raise OSError("simulated disk full")
                return original_touch(path, *args, **kwargs)

            stdout, stderr = io.StringIO(), io.StringIO()
            with patch("sys.argv", ["psvita_launcher", "sync", "--config", str(config)]), \
                    patch.object(Path, "touch", fail_one), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                result = app.main()
            self.assertEqual(result, 2)
            self.assertIn("simulated disk full", stderr.getvalue())
            self.assertIn("Sync failed:", stdout.getvalue())
            self.assertNotIn("Sync complete:", stdout.getvalue())
            managed = app.load_managed_state(root / "managed.tsv")
            self.assertEqual(set(managed), {"PCSE00002"})
            self.assertTrue((root / "output" / managed["PCSE00002"]).exists())

    def test_rename_failure_preserves_original_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source, output = root / "source", root / "output"
            (source / "PCSE00001").mkdir(parents=True)
            output.mkdir()
            old = output / "Old [PCSE00001].psvita"
            old.touch()
            state = root / "managed.tsv"
            app.write_managed_state(state, {"PCSE00001": old.name})
            with patch.object(Path, "rename", side_effect=OSError("simulated permission denied")), \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaisesRegex(RuntimeError, "1 launcher operation"):
                app.sync_launchers(source, output, root / "db", root / "unknown", state,
                                   root / "cache", False, True, True, False, False, False)
            self.assertTrue(old.exists())
            self.assertEqual(app.load_managed_state(state), {"PCSE00001": old.name})

    def test_long_unicode_filename_respects_name_max(self):
        name = "長いゲーム名™" * 100
        result = app.canonical_launcher_name("PCSE00001", name, True, 255)
        self.assertLessEqual(len(result.encode("utf-8")), 255)
        self.assertTrue(result.endswith(" (USA) [PCSE00001].psvita"))

    def test_parse_sfo_and_oversize_guard(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "param.sfo"
            p.write_bytes(make_sfo("PCSE00001", "Example Game"))
            meta = app.parse_sfo(p)
            self.assertEqual(meta["TITLE_ID"], "PCSE00001")
            self.assertEqual(meta["TITLE"], "Example Game")
            p.write_bytes(b"X" * (app.MAX_SFO_BYTES + 1))
            self.assertEqual(app.parse_sfo(p), {})

    def test_sync_cache_and_managed_cleanup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "ux0" / "app"
            output = root / "roms" / "psvita"
            state = root / "state.tsv"
            cache = root / "cache.tsv"
            db = root / "db.tsv"
            unknown = root / "unknown.txt"
            for tid, title in (("PCSE00001", "One"), ("PCSE00002", "Two")):
                sfo = source / tid / "sce_sys" / "param.sfo"
                sfo.parent.mkdir(parents=True, exist_ok=True)
                sfo.write_bytes(make_sfo(tid, title))

            result = app.sync_launchers(source, output, db, unknown, state, cache,
                                        False, False, True, True, True, False, False)
            self.assertEqual(result[:2], (2, 2))
            launchers = list(output.glob("*.psvita"))
            self.assertEqual(len(launchers), 2)
            self.assertTrue(all(p.stat().st_size == 0 for p in launchers))

            result2 = app.sync_launchers(source, output, db, unknown, state, cache,
                                         False, False, True, True, True, False, False)
            self.assertEqual(result2[1], 0)

            # Remove one installed title and preview cleanup: no file is deleted.
            import shutil
            shutil.rmtree(source / "PCSE00002")
            before = set(p.name for p in output.glob("*.psvita"))
            app.sync_launchers(source, output, db, unknown, state, cache,
                               False, False, True, True, True, True, True)
            self.assertEqual(before, set(p.name for p in output.glob("*.psvita")))

            # Confirm cleanup removes only the managed stale launcher.
            app.sync_launchers(source, output, db, unknown, state, cache,
                               False, False, True, True, True, True, False)
            remaining = list(output.glob("*.psvita"))
            self.assertEqual(len(remaining), 1)
            self.assertIn("PCSE00001", remaining[0].name)

    def test_cleanup_never_removes_unmanaged_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "out"
            output.mkdir()
            manual = output / "Manual [PCSE99999].psvita"
            manual.touch()
            deleted, state = app.cleanup_stale_managed_launchers(output, set(), {}, False)
            self.assertEqual(deleted, 0)
            self.assertTrue(manual.exists())
            self.assertEqual(state, {})

    def test_readonly_guard_rejects_output_inside_source(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "vita"
            settings = {
                "source": source,
                "output": source / "bad",
                "db_path": Path(td) / "db",
                "unknown_log": Path(td) / "u",
                "lock_path": Path(td) / "l",
                "managed_state": Path(td) / "m",
                "title_cache": Path(td) / "c",
            }
            with self.assertRaises(app.ConfigError):
                app.validate_source_read_only(settings)

    def test_lock_has_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            lock = Path(td) / "lock"
            with app.exclusive_lock(lock):
                with self.assertRaises(RuntimeError):
                    with app.exclusive_lock(lock, timeout_seconds=0):
                        pass

    def test_database_window_pagination(self):
        # Simulate 2,505 open compatibility issues while refusing page > 10.
        issues = []
        base = 1_700_000_000
        import datetime as dt
        for i in range(2505):
            stamp = dt.datetime.fromtimestamp(base + i, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            issues.append({"number": i + 1, "updated_at": stamp,
                           "title": f"Game {i+1} [PCSE{i%100000:05d}]"})

        def fake_request(url, timeout=20):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            page = int(q.get("page", ["1"])[0])
            self.assertLessEqual(page, 10)
            since = q.get("since", [None])[0]
            rows = issues
            if since:
                rows = [r for r in rows if r["updated_at"] >= since]
            start = (page - 1) * 100
            return rows[start:start+100], {}

        old = app.request_json
        app.request_json = fake_request
        try:
            with tempfile.TemporaryDirectory() as td:
                db = Path(td) / "titles.tsv"
                count = app.update_database(db)
                # IDs intentionally repeat modulo 100000 only after 100k rows; all 2505 unique here.
                self.assertEqual(count, 2505)
                self.assertTrue(db.exists())
        finally:
            app.request_json = old


if __name__ == "__main__":
    unittest.main()

