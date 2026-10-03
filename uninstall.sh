#!/bin/bash
# Vita Launcher Manager public uninstaller
set -u

APP_DIR="/userdata/system/psvita_launcher"
MARKER="$APP_DIR/.psvita-launcher-manager"
SERVICE_NAME="psvita-launcher-manager"
SERVICE="/userdata/system/services/$SERVICE_NAME"
LEGACY_SERVICE="/userdata/system/services/psvita_launcher"
SOURCE_HOOK="$APP_DIR/preupdate-gamelists-psvita-launcher-manager"
LIVE_HOOK="/usr/share/emulationstation/hooks/preupdate-gamelists-psvita-launcher-manager"
LEGACY_SOURCE_HOOK="$APP_DIR/preupdate-gamelists-psvita"
LEGACY_LIVE_HOOK="/usr/share/emulationstation/hooks/preupdate-gamelists-psvita"
PORT_LAUNCHER="/userdata/roms/ports/Vita Launcher Manager.sh"
LEGACY_PORT_LAUNCHER="/userdata/roms/ports/PS Vita Launcher Manager.sh"
DESKTOP_ENTRY="/userdata/system/.local/share/applications/psvita-launcher-manager.desktop"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Run this uninstaller as root." >&2
    exit 1
fi

file_has() { [ -f "$1" ] && grep -qF "$2" "$1" 2>/dev/null; }

if command -v batocera-services >/dev/null 2>&1; then
    if file_has "$SERVICE" 'PSVITA_LAUNCHER_MANAGER_SERVICE_V2'; then
        batocera-services stop "$SERVICE_NAME" >/dev/null 2>&1 || true
        batocera-services disable "$SERVICE_NAME" >/dev/null 2>&1 || true
    fi
    if [ -f "$LEGACY_SERVICE" ] && grep -qF 'APP_DIR="/userdata/system/psvita_launcher"' "$LEGACY_SERVICE" 2>/dev/null && grep -qF 'preupdate-gamelists-psvita' "$LEGACY_SERVICE" 2>/dev/null; then
        batocera-services stop psvita_launcher >/dev/null 2>&1 || true
        batocera-services disable psvita_launcher >/dev/null 2>&1 || true
    fi
fi

if [ -L "$LIVE_HOOK" ] && [ "$(readlink "$LIVE_HOOK" 2>/dev/null || true)" = "$SOURCE_HOOK" ]; then
    rm -f "$LIVE_HOOK"
fi
if [ -L "$LEGACY_LIVE_HOOK" ] && [ "$(readlink "$LEGACY_LIVE_HOOK" 2>/dev/null || true)" = "$LEGACY_SOURCE_HOOK" ]; then
    rm -f "$LEGACY_LIVE_HOOK"
fi

if file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1' || file_has "$PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2'; then
    rm -f "$PORT_LAUNCHER"
elif [ -e "$PORT_LAUNCHER" ]; then
    echo "Leaving unrelated/modified Ports entry untouched: $PORT_LAUNCHER"
fi
if file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V1' || file_has "$LEGACY_PORT_LAUNCHER" 'PSVITA_LAUNCHER_MANAGER_PORT_V2'; then
    rm -f "$LEGACY_PORT_LAUNCHER"
elif [ -e "$LEGACY_PORT_LAUNCHER" ]; then
    echo "Leaving unrelated/modified legacy Ports entry untouched: $LEGACY_PORT_LAUNCHER"
fi
if file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V1' || file_has "$DESKTOP_ENTRY" 'PSVITA_LAUNCHER_MANAGER_DESKTOP_V2'; then
    rm -f "$DESKTOP_ENTRY"
elif [ -e "$DESKTOP_ENTRY" ]; then
    echo "Leaving unrelated/modified desktop entry untouched: $DESKTOP_ENTRY"
fi

if file_has "$SERVICE" 'PSVITA_LAUNCHER_MANAGER_SERVICE_V2'; then
    rm -f "$SERVICE"
elif [ -e "$SERVICE" ]; then
    echo "Leaving unrelated/modified service untouched: $SERVICE"
fi
if [ -f "$LEGACY_SERVICE" ] && grep -qF 'APP_DIR="/userdata/system/psvita_launcher"' "$LEGACY_SERVICE" 2>/dev/null && grep -qF 'preupdate-gamelists-psvita' "$LEGACY_SERVICE" 2>/dev/null; then
    rm -f "$LEGACY_SERVICE"
fi

if file_has "$MARKER" 'Vita Launcher Manager' || file_has "$MARKER" 'PS Vita Launcher Manager'; then
    rm -rf "$APP_DIR"
elif [ -d "$APP_DIR" ]; then
    echo "WARNING: $APP_DIR has no project ownership marker; leaving it untouched." >&2
fi

echo "Vita Launcher Manager removed."
echo "Existing .psvita launcher files were intentionally left in /userdata/roms/psvita."
