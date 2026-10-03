#!/bin/bash
# PSVITA_LAUNCHER_MANAGER_PORT_V2
# EmulationStation Ports launcher for the on-demand GUI.
set -u
MANAGER="/userdata/system/psvita_launcher/psvita_manager.sh"

restore_cursor() {
    if command -v unclutter-remote >/dev/null 2>&1; then
        unclutter-remote -h >/dev/null 2>&1 || true
    fi
}
trap restore_cursor EXIT HUP INT TERM

if command -v unclutter-remote >/dev/null 2>&1; then
    unclutter-remote -s >/dev/null 2>&1 || true
fi

if [ ! -x "$MANAGER" ]; then
    echo "ERROR: Vita Launcher Manager is not installed: $MANAGER" >&2
    exit 1
fi
"$MANAGER"
exit $?
