#!/bin/bash
# Vita Launcher Manager public installer
set -eu

VERSION="1.7.1"
SRC_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
APP_DIR="/userdata/system/psvita_launcher"
MARKER="$APP_DIR/.psvita-launcher-manager"
PROTECTED_ROOT="/userdata/saves/psvita"
SERVICE_DIR="/userdata/system/services"
SERVICE_NAME="psvita-launcher-manager"
SERVICE="$SERVICE_DIR/$SERVICE_NAME"
LEGACY_SERVICE_NAME="psvita_launcher"
LEGACY_SERVICE="$SERVICE_DIR/$LEGACY_SERVICE_NAME"
PORTS_DIR="/userdata/roms/ports"
PORT_LAUNCHER="$PORTS_DIR/Vita Launcher Manager.sh"
LEGACY_PORT_LAUNCHER="$PORTS_DIR/PS Vita Launcher Manager.sh"
DESKTOP_DIR="/userdata/system/.local/share/applications"
DESKTOP_ENTRY="$DESKTOP_DIR/psvita-launcher-manager.desktop"
LIVE_HOOK="/usr/share/emulationstation/hooks/preupdate-gamelists-psvita-launcher-manager"
LEGACY_LIVE_HOOK="/usr/share/emulationstation/hooks/preupdate-gamelists-psvita"
LEGACY_SOURCE_HOOK="$APP_DIR/preupdate-gamelists-psvita"
INSTALL_GUI=1

usage() {
    cat <<USAGE
Usage: bash install.sh [--cli-only]

  --cli-only   Install the backend + UPDATE GAMELISTS hook without GUI shortcuts.
USAGE
}

for arg in "$@"; do
    case "$arg" in
        --cli-only) INSTALL_GUI=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this installer as root. Batocera SSH normally logs in as root." >&2
    exit 1
fi

PYTHON_BIN=$(command -v python3 2>/dev/null || true)
if [ -z "$PYTHON_BIN" ]; then
    echo "ERROR: Python 3 was not found. This package requires Batocera's Python 3." >&2
    exit 1
fi
if ! "$PYTHON_BIN" -S - <<'PYVER'
import sys
raise SystemExit(0 if sys.version_info >= (3, 9) else 1)
PYVER
then
    echo "ERROR: Python 3.9 or newer is required." >&2
    exit 1
fi

# Capability checks are more reliable than guessing from a version number.
if ! command -v batocera-services >/dev/null 2>&1; then
    echo "ERROR: batocera-services was not found. This public build requires a Batocera version with user services." >&2
    exit 1
fi
if [ ! -x /usr/bin/batocera-preupdate-gamelists-hook ]; then
    echo "ERROR: Batocera's pre-update-gamelists hook dispatcher was not found." >&2
    echo "This Batocera build is not compatible with the automatic UPDATE GAMELISTS integration." >&2
    exit 1
fi

# Uphold the read-only Vita3K guarantee during installation too. Resolve existing
# symlinks before any mkdir/cp operation and reject destinations under Vita3K.
if ! "$PYTHON_BIN" -S - "$PROTECTED_ROOT" "$APP_DIR" "$SERVICE" "$PORT_LAUNCHER" "$DESKTOP_ENTRY" <<'PYPATH'
import os, sys
protected=os.path.realpath(sys.argv[1])
bad=[]
for raw in sys.argv[2:]:
    resolved=os.path.realpath(raw)
    if resolved == protected or resolved.startswith(protected + os.sep):
        bad.append((raw,resolved))
if bad:
    for raw,resolved in bad:
        print(f"ERROR: install destination resolves inside protected Vita3K storage: {raw} -> {resolved}", file=sys.stderr)
    raise SystemExit(1)
PYPATH
then
    exit 1
fi

file_has() {
    file="$1"; marker="$2"
    [ -f "$file" ] && grep -qF "$marker" "$file" 2>/dev/null
}

app_dir_is_ours() {
    file_has "$MARKER" 'Vita Launcher Manager' && return 0
    file_has "$MARKER" 'PS Vita Launcher Manager' && return 0
    # Adopt private pre-public releases from this same project.
    [ -f "$APP_DIR/psvita_launcher.py" ] && \
        grep -qF 'Batocera PS Vita .psvita launcher generator' "$APP_DIR/psvita_launcher.py" 2>/dev/null
}

if [ -L "$APP_DIR" ]; then
    echo "ERROR: refusing to install into symlinked application directory: $APP_DIR" >&2
    exit 1
fi

if [ -d "$APP_DIR" ] && [ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ] && ! app_dir_is_ours; then
    echo "ERROR: $APP_DIR already exists and does not appear to belong to Vita Launcher Manager." >&2
    echo "Refusing to overwrite an unrelated directory." >&2
    exit 1
fi

if [ -L "$SERVICE" ]; then
    echo "ERROR: refusing to replace symlinked Batocera service: $SERVICE" >&2
    exit 1
fi
if [ -e "$SERVICE" ] && ! file_has "$SERVICE" 'PSVITA_LAUNCHER_MANAGER_SERVICE_V2'; then
    echo "ERROR: refusing to overwrite unrelated Batocera service: $SERVICE" >&2
    exit 1
fi
if [ -e "$LIVE_HOOK" ] || [ -L "$LIVE_HOOK" ]; then
    if [ ! -L "$LIVE_HOOK" ] || [ "$(readlink "$LIVE_HOOK" 2>/dev/null || true)" != "$APP_DIR/preupdate-gamelists-psvita-launcher-manager" ]; then
        echo "ERROR: refusing to replace unrelated EmulationStation hook: $LIVE_HOOK" >&2
        exit 1
    fi
fi

# Stop/remove only legacy files that can be positively identified as ours.
if [ -f "$LEGACY_SERVICE" ] && \
   grep -qF 'APP_DIR="/userdata/system/psvita_launcher"' "$LEGACY_SERVICE" 2>/dev/null && \
   grep -qF 'preupdate-gamelists-psvita' "$LEGACY_SERVICE" 2>/dev/null; then
    echo "Migrating older Vita Launcher Manager service..."
    batocera-services stop "$LEGACY_SERVICE_NAME" >/dev/null 2>&1 || true
    batocera-services disable "$LEGACY_SERVICE_NAME" >/dev/null 2>&1 || true
    rm -f "$LEGACY_SERVICE"
fi
if [ -L "$LEGACY_LIVE_HOOK" ] && [ "$(readlink "$LEGACY_LIVE_HOOK" 2>/dev/null || true)" = "$LEGACY_SOURCE_HOOK" ]; then
    rm -f "$LEGACY_LIVE_HOOK"
fi

mkdir -p "$APP_DIR" "$SERVICE_DIR"
printf 'Vita Launcher Manager\nversion=%s\n' "$VERSION" > "$MARKER"

cp -f "$SRC_DIR/psvita_launcher.py" "$APP_DIR/psvita_launcher.py"
cp -f "$SRC_DIR/preupdate-gamelists-psvita-launcher-manager" "$APP_DIR/preupdate-gamelists-psvita-launcher-manager"
cp -f "$SRC_DIR/psvita_launcher_service" "$SERVICE"
cp -f "$SRC_DIR/psvita_manager.sh" "$APP_DIR/psvita_manager.sh"
[ -f "$SRC_DIR/HELP.txt" ] && cp -f "$SRC_DIR/HELP.txt" "$APP_DIR/HELP.txt"

# Preserve user config and merge missing keys. If an existing config is malformed,
# leave its backup intact and fail with a precise message instead of rewriting it.
if [ ! -f "$APP_DIR/config.ini" ]; then
    cp "$SRC_DIR/config.ini" "$APP_DIR/config.ini"
else
    echo "Keeping existing config: $APP_DIR/config.ini"
    cp -f "$APP_DIR/config.ini" "$APP_DIR/config.ini.pre-v1.7.bak"
    if ! "$PYTHON_BIN" -S - "$APP_DIR/config.ini" <<'PYCFG'
import configparser, sys
from pathlib import Path
path=Path(sys.argv[1])
cfg=configparser.ConfigParser()
try:
    with path.open('r',encoding='utf-8') as fh:
        cfg.read_file(fh)
except Exception as exc:
    print(f"ERROR: existing config is invalid: {exc}", file=sys.stderr)
    raise SystemExit(1)
for section in ('paths','behavior'):
    if not cfg.has_section(section): cfg.add_section(section)
path_defaults={
 'source':'/userdata/saves/psvita/ux0/app',
 'output':'/userdata/roms/psvita',
 'database':'/userdata/system/psvita_launcher/title_ids.tsv',
 'unknown_log':'/userdata/system/psvita_launcher/unmatched_title_ids.txt',
 'lock_file':'/userdata/system/psvita_launcher/psvita_launcher.lock',
 'managed_state':'/userdata/system/psvita_launcher/managed_launchers.tsv',
 'title_cache':'/userdata/system/psvita_launcher/title_cache.tsv',
}
behavior_defaults={
 'recursive':'false','auto_update_database':'false','db_max_age_days':'30',
 'rename_existing_launchers':'false','cleanup_stale_launchers':'false',
 'include_region':'true','prefer_local_sfo':'true','cache_local_sfo':'true',
}
for k,v in path_defaults.items():
    if not cfg.has_option('paths',k): cfg.set('paths',k,v)
for k,v in behavior_defaults.items():
    if not cfg.has_option('behavior',k): cfg.set('behavior',k,v)
with path.open('w',encoding='utf-8') as fh: cfg.write(fh)
PYCFG
    then
        echo "ERROR: Could not migrate config. Original backup: $APP_DIR/config.ini.pre-v1.7.bak" >&2
        exit 1
    fi
fi

chmod +x "$APP_DIR/psvita_launcher.py" "$APP_DIR/preupdate-gamelists-psvita-launcher-manager" "$APP_DIR/psvita_manager.sh" "$SERVICE"
"$PYTHON_BIN" -S "$APP_DIR/psvita_launcher.py" --version >/dev/null
if ! "$PYTHON_BIN" -S "$APP_DIR/psvita_launcher.py" check-config >/dev/null; then
    echo "ERROR: configuration safety check failed. Run:" >&2
    echo "  $PYTHON_BIN -S $APP_DIR/psvita_launcher.py doctor" >&2
    exit 1
fi

# Public installs stay offline and deterministic. The optional compatibility DB
# can be refreshed later from the GUI/CLI; local PARAM.SFO metadata is primary.
if [ -s "$APP_DIR/title_ids.tsv" ]; then
    echo "Keeping existing optional TITLE-ID database: $APP_DIR/title_ids.tsv"
else
    echo "Optional TITLE-ID database not present; skipping network download during install."
    echo "Installed PARAM.SFO metadata is the primary name source. Update Database is available later if wanted."
fi

# GUI integration is optional. Do not install dead shortcuts on images without YAD.
GUI_INSTALLED=0
if [ "$INSTALL_GUI" -eq 1 ] && command -v yad >/dev/null 2>&1; then
    mkdir -p "$PORTS_DIR" "$DESKTOP_DIR"
    if [ -L "$PORT_LAUNCHER" ] || { [ -e "$PORT_LAUNCHER" ] && ! file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2' && ! file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1'; }; then
        echo "WARNING: leaving unrelated/symlinked Ports entry untouched: $PORT_LAUNCHER" >&2
    else
        cp -f "$SRC_DIR/psvita_manager_port.sh" "$PORT_LAUNCHER"
        chmod +x "$PORT_LAUNCHER"
        if file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1' || file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2'; then
            rm -f "$LEGACY_PORT_LAUNCHER"
        fi
        GUI_INSTALLED=1
    fi
    if [ -L "$DESKTOP_ENTRY" ] || { [ -e "$DESKTOP_ENTRY" ] && ! file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V2' && ! file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V1'; }; then
        echo "WARNING: leaving unrelated/symlinked desktop entry untouched: $DESKTOP_ENTRY" >&2
    else
        cp -f "$SRC_DIR/psvita-launcher-manager.desktop" "$DESKTOP_ENTRY"
        GUI_INSTALLED=1
    fi
else
    # Remove only obsolete shortcuts from this project so users do not get a GUI
    # entry that cannot launch on a non-YAD image.
    if file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1' || file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2'; then rm -f "$PORT_LAUNCHER"; fi
    if file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1' || file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2'; then rm -f "$LEGACY_PORT_LAUNCHER"; fi
    if file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V1' || file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V2'; then rm -f "$DESKTOP_ENTRY"; fi
    [ "$INSTALL_GUI" -eq 0 ] || echo "NOTICE: YAD is not available on this Batocera image; installing core functionality without GUI shortcuts."
fi

batocera-services enable "$SERVICE_NAME" >/dev/null
if ! batocera-services start "$SERVICE_NAME"; then
    echo "ERROR: Could not register the UPDATE GAMELISTS hook." >&2
    exit 1
fi

# Non-destructive diagnostics are useful but source absence should not undo an
# otherwise valid install (for example, Vita3K has not installed a game yet).
echo
echo "Installation diagnostics:"
"$PYTHON_BIN" -S "$APP_DIR/psvita_launcher.py" doctor || true

echo
echo "Vita Launcher Manager v$VERSION installed."
echo "Backend:  $APP_DIR/psvita_launcher.py"
echo "Config:   $APP_DIR/config.ini"
echo "Service:  $SERVICE"
echo "Log:      $APP_DIR/psvita_launcher.log"
echo "No polling process or resident Python process is used."
echo "Use GAME SETTINGS -> UPDATE GAMELISTS to create missing .psvita launchers."
if [ "$GUI_INSTALLED" -eq 1 ]; then
    echo "GUI:      Vita Launcher Manager in Ports and/or F1 -> Applications."
    echo "Run UPDATE GAMELISTS once so a newly installed Ports shortcut appears."
else
    echo "GUI:      not installed; core UPDATE GAMELISTS integration is active."
fi
echo "Help:     $APP_DIR/HELP.txt"
echo "Report:   $PYTHON_BIN -S $APP_DIR/psvita_launcher.py support-report"
