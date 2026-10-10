#!/usr/bin/env python3
# Developed with ChatGPT / Codex AI assistance, directed by dadtrick.
# See AI_DISCLOSURE.md at the repository root for attribution and test limits.
"""Batocera PS Vita .psvita launcher generator.

Designed for Batocera v43 / Vita3K.  The program reads Vita3K's installed-app
directory for TITLE IDs and creates zero-byte .psvita launcher files for
EmulationStation. The Vita3K source tree is treated as strictly read-only.

Name resolution order:
  1. Local Vita3K sce_sys/param.sfo metadata, when available.
  2. A local TSV database built from Vita3K's compatibility repository.
  3. The TITLE ID itself as a safe fallback.

Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import configparser
import csv
import fcntl
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time
from contextlib import contextmanager
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

APP_VERSION = "1.7.3"
DEFAULT_VITA3K_ROOT = Path("/userdata/saves/psvita")
DEFAULT_SOURCE = DEFAULT_VITA3K_ROOT / "ux0" / "app"
DEFAULT_OUTPUT = Path("/userdata/roms/psvita")
DEFAULT_APP_DIR = Path("/userdata/system/psvita_launcher")
DEFAULT_CONFIG = DEFAULT_APP_DIR / "config.ini"
DEFAULT_DB = DEFAULT_APP_DIR / "title_ids.tsv"
DEFAULT_UNKNOWN = DEFAULT_APP_DIR / "unmatched_title_ids.txt"
DEFAULT_LOCK = DEFAULT_APP_DIR / "psvita_launcher.lock"
DEFAULT_MANAGED = DEFAULT_APP_DIR / "managed_launchers.tsv"
DEFAULT_TITLE_CACHE = DEFAULT_APP_DIR / "title_cache.tsv"
DEFAULT_SERVICE = Path("/userdata/system/services/psvita-launcher-manager")
LIVE_HOOK = Path("/usr/share/emulationstation/hooks/preupdate-gamelists-psvita-launcher-manager")
EXPECTED_HOOK = DEFAULT_APP_DIR / "preupdate-gamelists-psvita-launcher-manager"
DEFAULT_LOG = DEFAULT_APP_DIR / "psvita_launcher.log"
DEFAULT_LAST_STATUS = DEFAULT_APP_DIR / "last_sync_status.txt"

GITHUB_ISSUES_API = "https://api.github.com/repos/Vita3K/compatibility/issues"
USER_AGENT = f"Batocera-PSVita-Launcher/{APP_VERSION}"

# Standard Vita application IDs are four ASCII letters followed by five digits.
TITLE_ID_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{4}[0-9]{5})(?![A-Z0-9])", re.I)
ISSUE_TITLE_RE = re.compile(r"^(.*?)\s*\[([A-Z]{4}[0-9]{5})\]\s*$", re.I)
LAUNCHER_ID_RE = re.compile(r"\[([A-Z]{4}[0-9]{5})\]\.psvita$", re.I)

REGION_PREFIXES = {
    "PCSA": "USA",
    "PCSE": "USA",
    "PCSB": "Europe",
    "PCSF": "Europe",
    "PCSC": "Japan",
    "PCSG": "Japan",
    "PCSD": "Asia",
    "PCSH": "Asia",
}

WINDOWS_FORBIDDEN = re.compile(r'[<>:"/\\|?*]')
CONTROL_CHARS = re.compile(r"[\x00-\x1f]")
WHITESPACE = re.compile(r"\s+")
DEFAULT_NAME_MAX = 255
MAX_SFO_BYTES = 4 * 1024 * 1024


class ConfigError(RuntimeError):
    pass


def _resolved(path: Path) -> Path:
    """Resolve a path for containment checks without requiring it to exist."""
    try:
        return path.resolve(strict=False)
    except OSError as exc:
        raise ConfigError(f"Could not resolve path {path}: {exc}") from exc


def _is_within(path: Path, parent: Path) -> bool:
    """Return True when path is parent itself or is located below parent."""
    path_r = _resolved(path)
    parent_r = _resolved(parent)
    try:
        path_r.relative_to(parent_r)
        return True
    except ValueError:
        return False


def validate_source_read_only(settings: dict) -> None:
    """Enforce that Vita3K storage is read-only from this utility.

    Every writable path is rejected if it resolves anywhere under Batocera's
    Vita3K data root (/userdata/saves/psvita). We also protect the configured
    source itself in case an advanced user points source at a different Vita3K
    installation. Existing symlinks are resolved before containment checks.
    """
    source: Path = settings["source"]
    protected_roots = (DEFAULT_VITA3K_ROOT, source)
    writable = {
        "output": settings["output"],
        "database": settings["db_path"],
        "unknown_log": settings["unknown_log"],
        "lock_file": settings["lock_path"],
        "managed_state": settings["managed_state"],
        "title_cache": settings["title_cache"],
    }
    offenders = []
    for label, path in writable.items():
        if any(_is_within(path, root) for root in protected_roots):
            offenders.append((label, path))
    if offenders:
        details = ", ".join(f"{label}={path}" for label, path in offenders)
        raise ConfigError(
            "Vita3K storage is read-only input. Refusing configuration because "
            f"writable path(s) resolve inside protected Vita3K storage: {details}"
        )


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def sanitize_name(name: str) -> str:
    """Make a title safe on Linux and through Batocera's SMB share."""
    name = CONTROL_CHARS.sub(" ", name)
    name = WINDOWS_FORBIDDEN.sub(" - ", name)
    name = WHITESPACE.sub(" ", name).strip(" .")
    return name or "Unknown Game"


def truncate_utf8(text: str, max_bytes: int) -> str:
    """Truncate text to max UTF-8 bytes without splitting a code point."""
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", "ignore").rstrip(" .")


def filesystem_name_max(path: Path) -> int:
    """Return a conservative NAME_MAX for path's filesystem.

    The output directory may not exist yet, so walk upward to the nearest
    existing ancestor. Cap the value at 255 because that is the common Linux
    filename limit and keeps launcher names SMB-friendly as well.
    """
    probe = _resolved(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        value = int(os.pathconf(str(probe), "PC_NAME_MAX"))
    except (OSError, ValueError, KeyError):
        value = DEFAULT_NAME_MAX
    if value < 64:
        raise ConfigError(f"Filesystem NAME_MAX is unexpectedly small ({value}) at {probe}")
    return min(value, DEFAULT_NAME_MAX)


def infer_region(title_id: str) -> str:
    return REGION_PREFIXES.get(title_id[:4].upper(), "Unknown Region")


def load_config(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(
        {
            "paths": {
                "source": str(DEFAULT_SOURCE),
                "output": str(DEFAULT_OUTPUT),
                "database": str(DEFAULT_DB),
                "unknown_log": str(DEFAULT_UNKNOWN),
                "lock_file": str(DEFAULT_LOCK),
                "managed_state": str(DEFAULT_MANAGED),
                "title_cache": str(DEFAULT_TITLE_CACHE),
            },
            "behavior": {
                "recursive": "false",
                # Network access during UPDATE GAMELISTS is disabled by default.
                "auto_update_database": "false",
                "db_max_age_days": "30",
                # Preserve user-created launcher names unless explicitly enabled.
                "rename_existing_launchers": "false",
                "include_region": "true",
                "prefer_local_sfo": "true",
                # Opt-in: remove stale launcher files created by this tool only.
                "cleanup_stale_launchers": "false",
                # Cache local PARAM.SFO titles to minimize disk reads on large libraries.
                "cache_local_sfo": "true",
            },
        }
    )
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as fh:
                cfg.read_file(fh)
        except (OSError, configparser.Error) as exc:
            raise ConfigError(f"Could not read configuration {path}: {exc}") from exc
    return cfg


def cfg_bool(cfg: configparser.ConfigParser, section: str, key: str, fallback: bool) -> bool:
    try:
        return cfg.getboolean(section, key)
    except (ValueError, configparser.Error) as exc:
        raise ConfigError(f"Invalid boolean setting [{section}] {key}: {exc}") from exc
    except KeyError:
        return fallback


def cfg_int(cfg: configparser.ConfigParser, section: str, key: str, fallback: int) -> int:
    try:
        return cfg.getint(section, key)
    except (ValueError, configparser.Error) as exc:
        raise ConfigError(f"Invalid integer setting [{section}] {key}: {exc}") from exc
    except KeyError:
        return fallback


@contextmanager
def exclusive_lock(path: Path, timeout_seconds: float = 5.0) -> Iterator[None]:
    """Prevent concurrent operations without hanging EmulationStation indefinitely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as fh:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "Another Vita Launcher Manager operation is already running. "
                        "Wait for it to finish and try again."
                    )
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _readonly_open_flags(directory: bool = False) -> int:
    """Flags for best-effort read access without changing source atime."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOATIME", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


@contextmanager
def readonly_scandir(path: Path) -> Iterator[Iterator[os.DirEntry]]:
    """Scan a source directory with O_NOATIME when Linux/filesystem permits it."""
    fd: Optional[int] = None
    if getattr(os, "O_NOATIME", 0):
        try:
            fd = os.open(path, _readonly_open_flags(directory=True))
        except OSError:
            fd = None
    if fd is not None:
        try:
            with os.scandir(fd) as entries:
                yield entries
        finally:
            os.close(fd)
    else:
        with os.scandir(path) as entries:
            yield entries


def read_bytes_readonly(path: Path, max_bytes: Optional[int] = None) -> bytes:
    """Read a source file using O_NOATIME where supported.

    max_bytes bounds memory use for untrusted/corrupt metadata files. When set,
    one extra byte is read so callers can detect oversize input.
    """
    if getattr(os, "O_NOATIME", 0):
        fd: Optional[int] = None
        try:
            fd = os.open(path, _readonly_open_flags(directory=False))
            with os.fdopen(fd, "rb", closefd=True) as fh:
                fd = None
                return fh.read(max_bytes + 1) if max_bytes is not None else fh.read()
        except OSError:
            if fd is not None:
                os.close(fd)
    with path.open("rb") as fh:
        return fh.read(max_bytes + 1) if max_bytes is not None else fh.read()


def request_json(url: str, timeout: int = 20) -> Tuple[object, dict]:
    # Keep networking modules out of the normal gamelist-sync path.
    import json
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        headers = dict(response.headers.items())
    return json.loads(body), headers


def update_database(db_path: Path) -> int:
    """Build TITLE_ID -> name TSV from valid/open Vita3K compatibility issues.

    GitHub may reject unauthenticated deep page-number pagination around the
    first 1,000 records with HTTP 422.  To stay within that boundary without
    requiring a token, fetch open issues in ascending updated-time windows,
    never requesting beyond page 10 in any one window.  A one-second overlap
    between windows plus issue-number de-duplication prevents boundary loss.
    """
    import datetime as _dt
    import urllib.error
    import urllib.parse

    print("Updating TITLE ID database from Vita3K compatibility repository...")
    entries: Dict[str, str] = {}
    seen_issue_numbers: set[int] = set()
    since: Optional[str] = None
    window = 1
    total_api_rows = 0

    def _parse_github_time(value: str) -> _dt.datetime:
        # GitHub timestamps are UTC ISO-8601, normally YYYY-MM-DDTHH:MM:SSZ.
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

    while True:
        window_new = 0
        max_updated: Optional[_dt.datetime] = None
        exhausted = False

        for page in range(1, 11):
            params = {
                "state": "open",
                "sort": "updated",
                "direction": "asc",
                "per_page": "100",
                "page": str(page),
            }
            if since:
                params["since"] = since
            url = f"{GITHUB_ISSUES_API}?{urllib.parse.urlencode(params)}"

            try:
                payload, _headers = request_json(url)
            except urllib.error.HTTPError as exc:
                remaining = exc.headers.get("X-RateLimit-Remaining", "?") if exc.headers else "?"
                reset = exc.headers.get("X-RateLimit-Reset", "?") if exc.headers else "?"
                reset_text = str(reset)
                try:
                    reset_text = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(reset)))
                except (TypeError, ValueError, OSError):
                    pass
                if str(remaining) == "0" or exc.code in (403, 429):
                    detail = f"GitHub API rate limit reached. Try again after {reset_text}."
                else:
                    detail = f"GitHub returned HTTP {exc.code}."
                raise RuntimeError(
                    f"{detail} The database is optional; installed PARAM.SFO metadata and TITLE-ID fallback still work. "
                    f"Rate-limit remaining={remaining}."
                ) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Could not reach GitHub: {exc.reason}") from exc

            if not isinstance(payload, list):
                raise RuntimeError("Unexpected GitHub API response; expected a list of issues.")
            if not payload:
                exhausted = True
                break

            total_api_rows += len(payload)
            for issue in payload:
                if not isinstance(issue, dict) or "pull_request" in issue:
                    continue

                updated_raw = str(issue.get("updated_at", "")).strip()
                if updated_raw:
                    try:
                        updated = _parse_github_time(updated_raw)
                        if max_updated is None or updated > max_updated:
                            max_updated = updated
                    except ValueError:
                        pass

                try:
                    issue_number = int(issue.get("number", 0))
                except (TypeError, ValueError):
                    issue_number = 0
                if issue_number and issue_number in seen_issue_numbers:
                    continue
                if issue_number:
                    seen_issue_numbers.add(issue_number)
                window_new += 1

                title = str(issue.get("title", "")).strip()
                match = ISSUE_TITLE_RE.match(title)
                if not match:
                    continue
                name = sanitize_name(match.group(1).strip())
                title_id = match.group(2).upper()
                if name.lower() in {"app name", "game title", "unknown", "test"}:
                    continue
                entries[title_id] = name

            print(
                f"  window {window}, page {page}: {len(payload)} issues "
                f"({len(entries)} TITLE IDs parsed)"
            )
            if len(payload) < 100:
                exhausted = True
                break

        if exhausted:
            break
        if max_updated is None:
            raise RuntimeError("GitHub pagination made no timestamp progress; existing database was left untouched.")

        # Overlap one second so issues sharing the boundary timestamp cannot be
        # skipped. seen_issue_numbers removes duplicates on the next window.
        next_since_dt = max_updated - _dt.timedelta(seconds=1)
        next_since = next_since_dt.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if since == next_since and window_new == 0:
            raise RuntimeError("GitHub pagination stalled; existing database was left untouched.")
        since = next_since
        window += 1
        if window > 20:
            raise RuntimeError("Aborting after 20 pagination windows; GitHub pagination looks unexpected.")

    if not entries:
        raise RuntimeError("No valid TITLE IDs were parsed; existing database was left untouched.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = db_path.with_name(f".{db_path.name}.tmp.{os.getpid()}")
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("# Batocera PS Vita TITLE ID map\n")
            fh.write("# Source: Vita3K/compatibility open GitHub issues\n")
            fh.write(f"# Generated: {generated_at}\n")
            fh.write("# TITLE_ID\tGAME_NAME\tREGION\n")
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            for title_id in sorted(entries):
                writer.writerow([title_id, entries[title_id], infer_region(title_id)])
        temp_path.replace(db_path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass

    print(f"Database written: {db_path}")
    print(f"TITLE IDs stored: {len(entries)}")
    print(f"GitHub rows examined: {total_api_rows}; unique issues: {len(seen_issue_numbers)}")
    return len(entries)

def load_database(db_path: Path, wanted_ids: Optional[set[str]] = None) -> Dict[str, str]:
    """Load only the TITLE IDs needed for this sync when a filter is supplied."""
    result: Dict[str, str] = {}
    if not db_path.exists():
        return result
    wanted = {x.upper() for x in wanted_ids} if wanted_ids is not None else None
    if wanted is not None and not wanted:
        return result
    try:
        with db_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rows = csv.reader((line for line in fh if not line.startswith("#")), delimiter="\t")
            for row in rows:
                if len(row) < 2:
                    continue
                title_id = row[0].strip().upper()
                if wanted is not None and title_id not in wanted:
                    continue
                if TITLE_ID_RE.fullmatch(title_id):
                    result[title_id] = row[1].strip()
                    if wanted is not None and len(result) == len(wanted):
                        break
    except OSError as exc:
        eprint(f"WARNING: could not read database {db_path}: {exc}")
    return result


def database_is_stale(db_path: Path, max_age_days: int) -> bool:
    if not db_path.exists():
        return True
    if max_age_days <= 0:
        return False
    try:
        age_seconds = time.time() - db_path.stat().st_mtime
    except OSError:
        return True
    return age_seconds > max_age_days * 86400


def discover_title_entries(source: Path, recursive: bool) -> Dict[str, Tuple[Path, bool]]:
    """Find TITLE IDs in one filesystem pass.

    Returns TITLE_ID -> (entry path, is_directory).  A directory is preferred
    over a same-ID file because installed Vita3K apps are directories and can
    provide local PARAM.SFO metadata.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Source is not a directory: {source}")

    found: Dict[str, Tuple[Path, bool]] = {}

    def consider(path_text: str, name: str, is_dir: bool, is_file: bool) -> None:
        if not is_dir and not is_file:
            return
        if is_file and name.lower().endswith(".psvita"):
            return
        match = TITLE_ID_RE.search(name.upper())
        if not match:
            return
        title_id = match.group(1).upper()
        previous = found.get(title_id)
        if previous is None or (is_dir and not previous[1]):
            found[title_id] = (Path(path_text), is_dir)

    try:
        pending = [source]
        while pending:
            root = pending.pop()
            with readonly_scandir(root) as entries:
                for entry in entries:
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        is_file = entry.is_file(follow_symlinks=False)
                    except OSError:
                        continue
                    full_path = root / entry.name
                    consider(str(full_path), entry.name, is_dir, is_file)
                    if recursive and is_dir:
                        pending.append(full_path)
            if not recursive:
                break
    except OSError as exc:
        raise OSError(f"Could not scan source directory {source}: {exc}") from exc

    return found


def parse_sfo(path: Path) -> Dict[str, object]:
    """Parse a PlayStation PARAM.SFO file using only the standard library."""
    try:
        data = read_bytes_readonly(path, MAX_SFO_BYTES)
    except OSError:
        return {}

    if len(data) > MAX_SFO_BYTES:
        return {}
    if len(data) < 20 or data[:4] != b"\x00PSF":
        return {}
    try:
        _version, key_start, data_start, count = struct.unpack_from("<4I", data, 4)
    except struct.error:
        return {}
    if count > 4096 or key_start >= len(data) or data_start >= len(data):
        return {}

    result: Dict[str, object] = {}
    entry_base = 20
    entry_size = 16
    if entry_base + count * entry_size > len(data):
        return {}

    for i in range(count):
        off = entry_base + i * entry_size
        try:
            key_off, fmt, length, _max_length, value_off = struct.unpack_from("<HHIII", data, off)
        except struct.error:
            return {}

        key_pos = key_start + key_off
        if key_pos >= len(data):
            continue
        key_end = data.find(b"\x00", key_pos)
        if key_end < 0:
            continue
        key = data[key_pos:key_end].decode("utf-8", "replace")

        value_pos = data_start + value_off
        if value_pos >= len(data):
            continue
        value_end = min(value_pos + length, len(data))
        raw = data[value_pos:value_end]

        # 0x0204 is UTF-8/string in PARAM.SFO; 0x0404 is uint32.
        if fmt == 0x0204:
            result[key] = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")
        elif fmt == 0x0404 and len(raw) >= 4:
            result[key] = struct.unpack_from("<I", raw, 0)[0]
        else:
            result[key] = raw
    return result


def local_sfo_title(entry_path: Path, is_directory: bool, title_id: str) -> Optional[str]:
    """Return TITLE from an installed Vita3K app without rescanning its parent."""
    if not is_directory:
        return None
    sfo_path = entry_path / "sce_sys" / "param.sfo"
    if not sfo_path.is_file():
        return None
    meta = parse_sfo(sfo_path)
    embedded_id = str(meta.get("TITLE_ID", "")).strip().upper()
    if embedded_id and embedded_id != title_id:
        return None
    for key in ("TITLE", "STITLE"):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_name(value.strip())
    return None


def canonical_launcher_name(
    title_id: str,
    game_name: Optional[str],
    include_region: bool,
    name_max: int = DEFAULT_NAME_MAX,
) -> str:
    """Build a Batocera launcher filename that cannot exceed NAME_MAX bytes."""
    base = sanitize_name(game_name) if game_name else title_id
    region = infer_region(title_id)
    if include_region and region != "Unknown Region":
        suffix = f" ({region}) [{title_id}].psvita"
    else:
        suffix = f" [{title_id}].psvita"

    suffix_bytes = len(suffix.encode("utf-8"))
    available = name_max - suffix_bytes
    if available < 1:
        raise ConfigError(
            f"Filesystem NAME_MAX={name_max} leaves no room for a launcher title suffix: {suffix}"
        )
    base = truncate_utf8(base, available) or truncate_utf8("Game", available) or "G"
    filename = base + suffix
    if len(filename.encode("utf-8")) > name_max:
        raise RuntimeError("Internal error: generated launcher filename exceeds NAME_MAX")
    return filename


def index_existing_launchers(output: Path, wanted_ids: Optional[set[str]] = None) -> Dict[str, List[Path]]:
    """Index only relevant launchers; no sorting is needed for correctness."""
    result: Dict[str, List[Path]] = {}
    if not output.exists():
        return result
    wanted = {x.upper() for x in wanted_ids} if wanted_ids is not None else None
    if wanted is not None and not wanted:
        return result
    try:
        with os.scandir(output) as entries:
            for entry in entries:
                try:
                    if not entry.is_file(follow_symlinks=False) or not entry.name.lower().endswith(".psvita"):
                        continue
                except OSError:
                    continue
                match = LAUNCHER_ID_RE.search(entry.name)
                if match is None:
                    # Batocera also accepts manually named launchers with the
                    # ID elsewhere in the filename. Prefer our exact suffix,
                    # then the rightmost ID so title text cannot take priority.
                    matches = list(TITLE_ID_RE.finditer(entry.name))
                    match = matches[-1] if matches else None
                if not match:
                    continue
                title_id = match.group(1).upper()
                if wanted is not None and title_id not in wanted:
                    continue
                result.setdefault(title_id, []).append(Path(entry.path))
    except OSError as exc:
        raise OSError(f"Could not scan launcher output directory {output}: {exc}") from exc
    return result


def write_unknown_log(path: Path, unknown: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not unknown:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8") as fh:
            fh.write("# TITLE IDs found locally but unresolved by local SFO or the current database.\n")
            for title_id in unknown:
                fh.write(title_id + "\n")
        temp.replace(path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def load_title_cache(path: Path) -> Dict[str, Tuple[int, int, str]]:
    """Load the small local PARAM.SFO cache.

    Cache rows are TITLE_ID, mtime_ns, size, title. Empty titles are retained so
    an unchanged malformed/missing-title SFO does not get reparsed every sync.
    """
    result: Dict[str, Tuple[int, int, str]] = {}
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rows = csv.reader((line for line in fh if not line.startswith("#")), delimiter="\t")
            for row in rows:
                if len(row) < 4:
                    continue
                title_id = row[0].strip().upper()
                if not TITLE_ID_RE.fullmatch(title_id):
                    continue
                try:
                    mtime_ns = int(row[1])
                    size = int(row[2])
                except ValueError:
                    continue
                result[title_id] = (mtime_ns, size, row[3].strip())
    except OSError as exc:
        eprint(f"WARNING: could not read SFO title cache {path}: {exc}")
    return result


def write_title_cache(path: Path, cache: Dict[str, Tuple[int, int, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8", newline="") as fh:
            fh.write("# Local Vita3K PARAM.SFO title cache; safe to delete.\n")
            fh.write("# TITLE_ID\tMTIME_NS\tSIZE\tTITLE\n")
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            for title_id in sorted(cache):
                mtime_ns, size, title = cache[title_id]
                writer.writerow([title_id, mtime_ns, size, title])
        temp.replace(path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def resolve_local_titles(
    discovered: Dict[str, Tuple[Path, bool]],
    old_cache: Dict[str, Tuple[int, int, str]],
    use_cache: bool,
) -> Tuple[Dict[str, str], Dict[str, Tuple[int, int, str]], int, int]:
    """Resolve installed titles with at most one stat per local PARAM.SFO.

    Returns (resolved titles, next cache, cache hits, SFO reads). For a large
    library, unchanged games normally hit the cache and avoid opening PARAM.SFO.
    """
    next_cache: Dict[str, Tuple[int, int, str]] = {}
    titles: Dict[str, str] = {}
    cache_hits = 0
    sfo_reads = 0

    for title_id, (entry_path, is_directory) in discovered.items():
        if not is_directory:
            continue
        sfo_path = entry_path / "sce_sys" / "param.sfo"
        try:
            st = sfo_path.stat()
        except OSError:
            continue
        signature = (st.st_mtime_ns, st.st_size)
        cached = old_cache.get(title_id)
        if use_cache and cached is not None and cached[:2] == signature:
            cached_title = cached[2]
            next_cache[title_id] = cached
            if cached_title:
                titles[title_id] = cached_title
            cache_hits += 1
            continue

        sfo_reads += 1
        meta = parse_sfo(sfo_path)
        embedded_id = str(meta.get("TITLE_ID", "")).strip().upper()
        title = ""
        if not embedded_id or embedded_id == title_id:
            for key in ("TITLE", "STITLE"):
                value = meta.get(key)
                if isinstance(value, str) and value.strip():
                    title = sanitize_name(value.strip())
                    break
        if use_cache:
            next_cache[title_id] = (signature[0], signature[1], title)
        if title:
            titles[title_id] = title

    return titles, next_cache, cache_hits, sfo_reads


def load_managed_state(path: Path) -> Dict[str, str]:
    """Load launcher files explicitly created and owned by this utility."""
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            rows = csv.reader((line for line in fh if not line.startswith("#")), delimiter="\t")
            for row in rows:
                if len(row) < 2:
                    continue
                title_id = row[0].strip().upper()
                filename = row[1].strip()
                if not TITLE_ID_RE.fullmatch(title_id):
                    continue
                # State is filename-only; never permit path traversal.
                if Path(filename).name != filename or not filename.lower().endswith(".psvita"):
                    continue
                match = LAUNCHER_ID_RE.search(filename)
                if not match or match.group(1).upper() != title_id:
                    continue
                result[title_id] = filename
    except OSError as exc:
        eprint(f"WARNING: could not read managed-launcher state {path}: {exc}")
    return result


def write_managed_state(path: Path, state: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        with temp.open("w", encoding="utf-8", newline="") as fh:
            fh.write("# Launchers created by Batocera PS Vita Launcher.\n")
            fh.write("# Only these files are eligible for opt-in stale cleanup.\n")
            fh.write("# TITLE_ID\tFILENAME\n")
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            for title_id in sorted(state):
                writer.writerow([title_id, state[title_id]])
        temp.replace(path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def cleanup_stale_managed_launchers(
    output: Path,
    installed_ids: set[str],
    managed: Dict[str, str],
    dry_run: bool,
    errors: Optional[List[str]] = None,
) -> Tuple[int, Dict[str, str]]:
    """Delete stale launchers conservatively.

    Safety rules are intentionally strict: the launcher must be in our state
    file, absent from installed TITLE IDs, remain a regular non-symlink .psvita
    file, still contain the recorded TITLE ID, and still be zero bytes. If a
    tracked file was modified or replaced, ownership is relinquished instead of
    deleting it. Inspection/deletion errors can be collected by the sync caller
    while preserving the existing return contract and completing other work.
    """
    next_state = dict(managed)
    deleted = 0
    for title_id, filename in sorted(managed.items()):
        if title_id in installed_ids:
            continue
        path = output / filename
        try:
            if path.is_symlink():
                print(f"CLEANUP SKIP: {filename}: symlink; relinquishing management")
                if not dry_run:
                    next_state.pop(title_id, None)
                continue
            st = path.stat()
        except FileNotFoundError:
            if not dry_run:
                next_state.pop(title_id, None)
            continue
        except OSError as exc:
            message = f"cleanup could not inspect {path}: {exc}"
            eprint(f"ERROR: {message}")
            if errors is not None:
                errors.append(message)
            continue

        match = LAUNCHER_ID_RE.search(filename)
        if (
            not path.is_file()
            or not filename.lower().endswith(".psvita")
            or not match
            or match.group(1).upper() != title_id
            or st.st_size != 0
        ):
            print(f"CLEANUP SKIP: {filename}: modified/unexpected; relinquishing management")
            if not dry_run:
                next_state.pop(title_id, None)
            continue

        if dry_run:
            print(f"WOULD DELETE STALE: {path}")
            deleted += 1
            continue
        try:
            path.unlink()
            print(f"DELETED STALE: {path}")
            next_state.pop(title_id, None)
            deleted += 1
        except OSError as exc:
            message = f"could not delete stale launcher {path}: {exc}"
            eprint(f"ERROR: {message}")
            if errors is not None:
                errors.append(message)

    return deleted, next_state


def sync_launchers(
    source: Path,
    output: Path,
    db_path: Path,
    unknown_log: Path,
    managed_state_path: Path,
    title_cache_path: Path,
    recursive: bool,
    rename_existing: bool,
    include_region: bool,
    prefer_local_sfo: bool,
    cache_local_sfo: bool,
    cleanup_stale: bool,
    dry_run: bool = False,
) -> Tuple[int, int, int, int, int]:
    # Direct-call defense: launcher output must never enter Batocera's Vita3K
    # data tree or the configured source tree. main() validates all state paths.
    if _is_within(output, DEFAULT_VITA3K_ROOT) or _is_within(output, source):
        raise ConfigError(
            f"Output must be outside protected Vita3K storage: {DEFAULT_VITA3K_ROOT}"
        )
    discovered = discover_title_entries(source, recursive)
    title_ids = sorted(discovered)
    wanted_ids = set(title_ids)

    # Resolve local metadata first. For normal Vita3K installs this means the web
    # database often is not read at all, which is ideal for large collections.
    local_titles: Dict[str, str] = {}
    next_cache: Dict[str, Tuple[int, int, str]] = {}
    cache_hits = 0
    sfo_reads = 0
    old_cache: Dict[str, Tuple[int, int, str]] = {}
    if prefer_local_sfo:
        if cache_local_sfo:
            old_cache = load_title_cache(title_cache_path)
        local_titles, next_cache, cache_hits, sfo_reads = resolve_local_titles(
            discovered, old_cache, cache_local_sfo
        )

    unresolved_ids = wanted_ids.difference(local_titles)
    title_map = load_database(db_path, unresolved_ids) if unresolved_ids else {}

    if not dry_run:
        output.mkdir(parents=True, exist_ok=True)
    name_max = filesystem_name_max(output)
    existing = index_existing_launchers(output, wanted_ids)
    managed = load_managed_state(managed_state_path)
    next_managed = dict(managed)

    created = 0
    renamed = 0
    unchanged = 0
    failed = 0
    unknown: List[str] = []

    for title_id in title_ids:
        game_name = local_titles.get(title_id) or title_map.get(title_id)
        if not game_name:
            unknown.append(title_id)
        target = output / canonical_launcher_name(title_id, game_name, include_region, name_max)
        current = existing.get(title_id, [])
        tracked_name = next_managed.get(title_id)
        tracked_path = output / tracked_name if tracked_name else None

        # If a tracked launcher vanished while another launcher for this ID now
        # exists, assume the user took control (for example, manually renamed it).
        if tracked_path is not None and not tracked_path.exists() and current:
            if not dry_run:
                next_managed.pop(title_id, None)
            tracked_name = None
            tracked_path = None

        try:
            target_stat = target.lstat()
        except FileNotFoundError:
            target_stat = None
        except OSError as exc:
            eprint(f"ERROR: could not inspect launcher path {target}: {exc}")
            failed += 1
            continue
        if target_stat is not None:
            if stat.S_ISREG(target_stat.st_mode):
                unchanged += 1
            else:
                eprint(f"ERROR: launcher path exists but is not a regular non-symlink file: {target}")
                failed += 1
            continue

        if current:
            if rename_existing and len(current) == 1:
                old = current[0]
                was_managed = tracked_name == old.name
                if dry_run:
                    print(f"WOULD RENAME: {old.name} -> {target.name}")
                    renamed += 1
                    continue
                try:
                    old.rename(target)
                    print(f"RENAMED: {old.name} -> {target.name}")
                    if was_managed:
                        next_managed[title_id] = target.name
                    renamed += 1
                    continue
                except OSError as exc:
                    eprint(f"ERROR: could not rename {old}: {exc}")
                    failed += 1
                    continue
            names = ", ".join(p.name for p in current)
            print(f"EXISTS: {title_id}: preserving existing launcher(s): {names}")
            unchanged += 1
            continue

        if dry_run:
            print(f"WOULD CREATE: {target}")
            created += 1
            continue

        try:
            target.touch(exist_ok=False)
            next_managed[title_id] = target.name
            print(f"CREATED: {target}")
            created += 1
        except FileExistsError:
            unchanged += 1
        except OSError as exc:
            eprint(f"ERROR: could not create {target}: {exc}")
            failed += 1

    deleted = 0
    if cleanup_stale:
        cleanup_errors: List[str] = []
        deleted, next_managed = cleanup_stale_managed_launchers(
            output, wanted_ids, next_managed, dry_run, errors=cleanup_errors
        )
        failed += len(cleanup_errors)

    if not dry_run:
        write_unknown_log(unknown_log, unknown)
        if next_managed != managed:
            write_managed_state(managed_state_path, next_managed)
        if prefer_local_sfo and cache_local_sfo and next_cache != old_cache:
            write_title_cache(title_cache_path, next_cache)

    if dry_run:
        print(
            f"Dry run {'failed' if failed else 'complete'}: found={len(title_ids)}, would_create={created}, would_rename={renamed}, "
            f"would_delete={deleted}, unchanged={unchanged}, unmatched={len(unknown)}, "
            f"sfo_cache_hits={cache_hits}, sfo_reads={sfo_reads}, failed={failed}"
        )
    else:
        print(
            f"Sync {'failed' if failed else 'complete'}: found={len(title_ids)}, created={created}, renamed={renamed}, "
            f"deleted={deleted}, unchanged={unchanged}, unmatched={len(unknown)}, "
            f"sfo_cache_hits={cache_hits}, sfo_reads={sfo_reads}, failed={failed}"
        )
    if unknown:
        print(f"Unmatched TITLE IDs {'would be ' if dry_run else ''}recorded in: {unknown_log}")
    if failed:
        raise RuntimeError(f"{failed} launcher operation(s) failed; see errors above.")
    return len(title_ids), created, renamed, deleted, len(unknown)


def resolve_settings(args: argparse.Namespace) -> dict:
    config_path = Path(args.config).expanduser()
    cfg = load_config(config_path)

    source = Path(args.source or cfg.get("paths", "source", fallback=str(DEFAULT_SOURCE))).expanduser()
    output = Path(args.output or cfg.get("paths", "output", fallback=str(DEFAULT_OUTPUT))).expanduser()
    db_path = Path(args.database or cfg.get("paths", "database", fallback=str(DEFAULT_DB))).expanduser()
    unknown_log = Path(cfg.get("paths", "unknown_log", fallback=str(DEFAULT_UNKNOWN))).expanduser()
    lock_path = Path(cfg.get("paths", "lock_file", fallback=str(DEFAULT_LOCK))).expanduser()
    managed_state = Path(cfg.get("paths", "managed_state", fallback=str(DEFAULT_MANAGED))).expanduser()
    title_cache = Path(cfg.get("paths", "title_cache", fallback=str(DEFAULT_TITLE_CACHE))).expanduser()

    recursive = args.recursive if args.recursive is not None else cfg_bool(cfg, "behavior", "recursive", False)
    rename_existing = cfg_bool(cfg, "behavior", "rename_existing_launchers", False)
    include_region = cfg_bool(cfg, "behavior", "include_region", True)
    prefer_local_sfo = cfg_bool(cfg, "behavior", "prefer_local_sfo", True)
    cache_local_sfo = cfg_bool(cfg, "behavior", "cache_local_sfo", True)
    cleanup_cfg = cfg_bool(cfg, "behavior", "cleanup_stale_launchers", False)
    cleanup_stale = args.cleanup_stale if args.cleanup_stale is not None else cleanup_cfg
    auto_update = cfg_bool(cfg, "behavior", "auto_update_database", False)
    max_age_days = cfg_int(cfg, "behavior", "db_max_age_days", 30)

    return {
        "config_path": config_path,
        "source": source,
        "output": output,
        "db_path": db_path,
        "unknown_log": unknown_log,
        "lock_path": lock_path,
        "managed_state": managed_state,
        "title_cache": title_cache,
        "recursive": recursive,
        "rename_existing": rename_existing,
        "include_region": include_region,
        "prefer_local_sfo": prefer_local_sfo,
        "cache_local_sfo": cache_local_sfo,
        "cleanup_stale": cleanup_stale,
        "auto_update": auto_update,
        "max_age_days": max_age_days,
    }


def maybe_update(settings: dict) -> None:
    db_path: Path = settings["db_path"]
    if not settings["auto_update"]:
        return
    if not database_is_stale(db_path, settings["max_age_days"]):
        return
    try:
        update_database(db_path)
    except Exception as exc:
        if db_path.exists():
            eprint(f"WARNING: database update failed; using existing database: {exc}")
        else:
            eprint(f"WARNING: database update failed; local SFO/TITLE ID fallback will be used: {exc}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Batocera .psvita launchers from PS Vita TITLE IDs.")
    parser.add_argument("command", nargs="?", choices=["sync", "update-db", "list", "status", "doctor", "support-report", "check-config"], default="sync")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config.ini")
    parser.add_argument("--source", help="Read-only Vita3K installed-app directory (normally ux0/app)")
    parser.add_argument("--output", help="Directory in which to create .psvita files")
    parser.add_argument("--database", help="TITLE ID TSV database path")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without modifying launchers")
    recursive = parser.add_mutually_exclusive_group()
    recursive.add_argument("--recursive", dest="recursive", action="store_true", help="Scan source recursively")
    recursive.add_argument("--no-recursive", dest="recursive", action="store_false", help="Only scan source top level")
    parser.set_defaults(recursive=None)
    cleanup = parser.add_mutually_exclusive_group()
    cleanup.add_argument("--cleanup", dest="cleanup_stale", action="store_true", help="Opt in to deleting stale launchers created by this tool")
    cleanup.add_argument("--no-cleanup", dest="cleanup_stale", action="store_false", help="Disable stale managed-launcher cleanup for this run")
    parser.set_defaults(cleanup_stale=None)
    parser.add_argument("--version", action="version", version=APP_VERSION)
    return parser



def count_database_entries(path: Path) -> int:
    """Count valid TITLE-ID database rows without loading the database into RAM."""
    count = 0
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line or line.startswith("#"):
                    continue
                title_id = line.split("\t", 1)[0].strip().upper()
                if TITLE_ID_RE.fullmatch(title_id):
                    count += 1
    except OSError:
        return 0
    return count


def count_unmatched(path: Path) -> int:
    """Count unresolved TITLE IDs from the small unmatched log."""
    count = 0
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                value = line.strip().upper()
                if value and not value.startswith("#") and TITLE_ID_RE.fullmatch(value):
                    count += 1
    except OSError:
        return 0
    return count


def status(settings: dict) -> int:
    """Print a lightweight live status summary for the on-demand GUI/CLI."""
    source = settings["source"]
    output = settings["output"]
    try:
        discovered = discover_title_entries(source, settings["recursive"])
    except (OSError, FileNotFoundError, NotADirectoryError) as exc:
        eprint(f"ERROR: {exc}")
        return 1

    installed_ids = set(discovered)
    try:
        launchers = index_existing_launchers(output)
    except OSError as exc:
        eprint(f"ERROR: {exc}")
        return 1
    launcher_files = sum(len(paths) for paths in launchers.values())
    managed = load_managed_state(settings["managed_state"])
    stale_managed = sum(1 for title_id in managed if title_id not in installed_ids)
    db_entries = count_database_entries(settings["db_path"])
    unmatched = count_unmatched(settings["unknown_log"])

    hook = LIVE_HOOK
    expected_hook = EXPECTED_HOOK
    hook_active = False
    try:
        hook_active = hook.is_symlink() and _resolved(hook) == _resolved(expected_hook)
    except OSError:
        hook_active = False

    cleanup_default = "ON" if settings["cleanup_stale"] else "OFF"
    print(f"Version:             {APP_VERSION}")
    print(f"Installed Vita3K:    {len(installed_ids)}")
    print(f"Launcher files:      {launcher_files}")
    print(f"Launcher TITLE IDs:  {len(launchers)}")
    print(f"Managed launchers:   {len(managed)}")
    print(f"Stale managed:       {stale_managed}")
    print(f"TITLE-ID database:   {db_entries}")
    print(f"Unmatched TITLE IDs: {unmatched}")
    print(f"UPDATE GAMELISTS:    {'hook active' if hook_active else 'hook not active'}")
    try:
        last_hook = DEFAULT_LAST_STATUS.read_text(encoding="utf-8", errors="replace").strip() if DEFAULT_LAST_STATUS.exists() else "never run"
    except OSError:
        last_hook = "unavailable"
    print(f"Last hook sync:      {last_hook}")
    print(f"Auto cleanup:        {cleanup_default} (one-time GUI cleanup is explicit)")
    print(f"Vita3K source:       {source} [READ ONLY]")
    print(f"Launcher output:     {output}")
    return 0

def _batocera_release() -> str:
    """Return a best-effort Batocera release string for diagnostics."""
    for candidate in (Path("/etc/batocera-release"), Path("/usr/share/batocera/batocera.version")):
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip()
    return "unknown"


def doctor(settings: dict) -> int:
    """Run non-destructive checks and print actionable results."""
    import shutil

    problems = 0
    warnings = 0
    print(f"Vita Launcher Manager diagnostics v{APP_VERSION}")
    print(f"Batocera:  {_batocera_release()}")
    print(f"Python:    {sys.executable} ({sys.version.split()[0]})")
    print(f"Source:    {settings['source']} (READ-ONLY INPUT)")
    print(f"Output:    {settings['output']}")
    print(f"Database:  {settings['db_path']}")
    print(f"Config:    {settings['config_path']}")
    print(f"Cleanup:   {'enabled' if settings['cleanup_stale'] else 'disabled'} (managed zero-byte launchers only)")
    print(f"SFO cache: {'enabled' if settings['cache_local_sfo'] else 'disabled'}")

    if sys.version_info < (3, 9):
        eprint("ERROR: Python 3.9 or newer is required.")
        problems += 1

    try:
        validate_source_read_only(settings)
        print(f"Safety:    PASS - writable paths are outside protected Vita3K root {DEFAULT_VITA3K_ROOT}")
    except ConfigError as exc:
        eprint(f"ERROR: {exc}")
        problems += 1

    try:
        discovered = discover_title_entries(settings["source"], settings["recursive"])
        print(f"Source scan: PASS - {len(discovered)} TITLE ID(s) found")
    except (OSError, FileNotFoundError, NotADirectoryError) as exc:
        eprint(f"ERROR: source scan failed: {exc}")
        problems += 1

    output = settings["output"]
    if output.exists() and not output.is_dir():
        eprint(f"ERROR: launcher output exists but is not a directory: {output}")
        problems += 1
    else:
        print(f"Output dir: {'present' if output.is_dir() else 'not created yet (normal before first sync)'}")

    if settings["db_path"].exists():
        print(f"Database entries: {count_database_entries(settings['db_path'])}")
    else:
        print("Database entries: 0 (optional; local PARAM.SFO/TITLE-ID fallback remains available)")

    if shutil.which("batocera-services"):
        print("Services:  batocera-services available")
    else:
        eprint("WARNING: batocera-services is unavailable; boot-time hook registration may not persist.")
        warnings += 1

    if DEFAULT_SERVICE.exists():
        print(f"Service:   present ({DEFAULT_SERVICE})")
    else:
        eprint(f"WARNING: service file is missing: {DEFAULT_SERVICE}")
        warnings += 1

    try:
        hook_ok = LIVE_HOOK.is_symlink() and _resolved(LIVE_HOOK) == _resolved(EXPECTED_HOOK)
    except OSError:
        hook_ok = False
    if hook_ok:
        print(f"Hook:      active ({LIVE_HOOK})")
    else:
        eprint(f"WARNING: UPDATE GAMELISTS hook is not active: {LIVE_HOOK}")
        eprint("         Re-run install.sh or start the psvita-launcher-manager service.")
        warnings += 1

    if shutil.which("yad"):
        print("GUI:       YAD available")
    else:
        print("GUI:       YAD unavailable (core sync still works; GUI shortcuts should be skipped)")

    print(f"Result:    {problems} error(s), {warnings} warning(s)")
    return 0 if problems == 0 else 1


def support_report(settings: dict) -> int:
    """Print one copy/paste report suitable for a GitHub bug report."""
    print("=== Vita Launcher Manager support report ===")
    doctor_rc = doctor(settings)
    print("\n--- Live status ---")
    try:
        status(settings)
    except Exception as exc:
        eprint(f"Status collection failed: {exc}")
    print("\n--- Recent hook log (last 80 lines) ---")
    try:
        if DEFAULT_LOG.exists():
            lines = DEFAULT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
            for line in lines:
                print(line)
        else:
            print("No hook log exists yet.")
    except OSError as exc:
        print(f"Could not read log: {exc}")
    print("=== end report ===")
    return doctor_rc


def main() -> int:
    try:
        args = build_parser().parse_args()
        settings = resolve_settings(args)
        validate_source_read_only(settings)
    except ConfigError as exc:
        eprint(f"ERROR: {exc}")
        return 2

    if args.command == "check-config":
        print("Configuration safety check: OK")
        print(f"Vita3K source: {settings['source']} (read-only input)")
        print(f"Protected root: {DEFAULT_VITA3K_ROOT} (no writes permitted)")
        print(f"Launcher output: {settings['output']}")
        return 0

    if args.command == "list":
        db = load_database(settings["db_path"])
        if not db:
            eprint(f"Database is empty or missing: {settings['db_path']}")
            return 1
        for title_id in sorted(db):
            print(f"{title_id}\t{db[title_id]}\t{infer_region(title_id)}")
        return 0

    if args.command == "status":
        return status(settings)

    if args.command == "doctor":
        return doctor(settings)

    if args.command == "support-report":
        return support_report(settings)

    try:
        with exclusive_lock(settings["lock_path"]):
            if args.command == "update-db":
                update_database(settings["db_path"])
                return 0

            if not args.dry_run:
                maybe_update(settings)
            sync_launchers(
                source=settings["source"],
                output=settings["output"],
                db_path=settings["db_path"],
                unknown_log=settings["unknown_log"],
                managed_state_path=settings["managed_state"],
                title_cache_path=settings["title_cache"],
                recursive=settings["recursive"],
                rename_existing=settings["rename_existing"],
                include_region=settings["include_region"],
                prefer_local_sfo=settings["prefer_local_sfo"],
                cache_local_sfo=settings["cache_local_sfo"],
                cleanup_stale=settings["cleanup_stale"],
                dry_run=args.dry_run,
            )
            return 0
    except Exception as exc:
        eprint(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


