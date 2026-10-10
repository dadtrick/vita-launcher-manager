#!/bin/bash
# Developed with ChatGPT / Codex AI assistance, directed by dadtrick.
# See AI_DISCLOSURE.md at the repository root for attribution and test limits.
# PSVITA_LAUNCHER_MANAGER_GUI_V2
# Lightweight on-demand YAD front end for Batocera PS Vita Launcher.
# It never runs in the background and never writes to Vita3K storage.
set -u

APP_DIR="/userdata/system/psvita_launcher"
APP="$APP_DIR/psvita_launcher.py"
LOG="$APP_DIR/psvita_launcher.log"
HELP="$APP_DIR/HELP.txt"
TITLE="Vita Launcher Manager"

PYTHON_BIN=$(command -v python3 2>/dev/null || true)
YAD_BIN=$(command -v yad 2>/dev/null || true)

if [ -z "$PYTHON_BIN" ] || [ ! -r "$APP" ]; then
    echo "ERROR: PS Vita Launcher backend is missing." >&2
    exit 1
fi

# Ports normally supplies the display environment. This fallback helps Xorg
# desktop sessions started by Batocera without overriding a valid display.
if [ -z "${DISPLAY:-}" ] && [ -S /tmp/.X11-unix/X0 ]; then
    export DISPLAY=:0.0
fi

if [ -z "$YAD_BIN" ]; then
    echo "ERROR: YAD is not available on this Batocera image." >&2
    echo "The launcher backend still works normally through UPDATE GAMELISTS." >&2
    echo
    "$PYTHON_BIN" -S "$APP" status 2>&1 || true
    exit 1
fi

if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "ERROR: No graphical display is available." >&2
    echo "Launch this manager from EmulationStation Ports or F1 -> Applications." >&2
    exit 1
fi

markup_escape() {
    sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

show_message() {
    kind="$1"
    text="$2"
    case "$kind" in
        error) icon="dialog-error" ;;
        warning) icon="dialog-warning" ;;
        *) icon="dialog-information" ;;
    esac
    "$YAD_BIN" --title="$TITLE" --center --width=700 \
        --image="$icon" --text="$text" --button="OK":0 >/dev/null 2>&1 || true
}

show_file() {
    window_title="$1"
    file="$2"
    [ -f "$file" ] || {
        show_message info "Nothing to display."
        return
    }
    "$YAD_BIN" --title="$window_title" --center --width=900 --height=620 \
        --text-info --filename="$file" --button="Close":0 >/dev/null 2>&1 || true
}

run_action() {
    label="$1"
    shift
    tmp=$(mktemp "/tmp/psvita-manager.XXXXXX") || return 1
    rcfile="${tmp}.rc"

    (
        set +e
        printf '0\n'
        "$@" >"$tmp" 2>&1
        rc=$?
        printf '%s\n' "$rc" >"$rcfile"
        printf '100\n'
        exit 0
    ) | "$YAD_BIN" --title="$TITLE" --center --width=520 \
        --progress --pulsate --auto-close --no-buttons --text="$label" >/dev/null 2>&1 || true

    rc=1
    if [ -r "$rcfile" ]; then
        rc=$(cat "$rcfile" 2>/dev/null || echo 1)
    fi

    if [ "$rc" -eq 0 ] 2>/dev/null; then
        show_file "$label - Complete" "$tmp"
    else
        show_file "$label - Error" "$tmp"
    fi
    rm -f "$tmp" "$rcfile"
    return 0
}

confirm_cleanup() {
    "$YAD_BIN" --title="$TITLE" --center --width=720 --image="dialog-warning" \
        --text="<b>Clean stale launchers?</b>\n\nThis only removes zero-byte .psvita files that this tool previously created and tracks, when their TITLE ID is no longer installed in Vita3K.\n\n<b>Nothing under /userdata/saves/psvita is ever deleted or modified.</b>" \
        --button="Cancel":1 --button="Clean Stale Launchers":0 >/dev/null 2>&1
    return $?
}

view_log() {
    if [ ! -f "$LOG" ]; then
        show_message info "No UPDATE GAMELISTS log exists yet."
        return
    fi
    tmp=$(mktemp "/tmp/psvita-log.XXXXXX") || return
    tail -n 400 "$LOG" > "$tmp" 2>/dev/null || cp "$LOG" "$tmp"
    show_file "$TITLE - Recent Log" "$tmp"
    rm -f "$tmp"
}

while :; do
    set +e
    status_text=$("$PYTHON_BIN" -S "$APP" status 2>&1)
    status_rc=$?

    if [ "$status_rc" -ne 0 ]; then
        status_text="Status check failed:\n$status_text"
    fi
    escaped_status=$(printf '%s\n' "$status_text" | markup_escape)

    "$YAD_BIN" --title="$TITLE" --center --width=940 --height=480 \
        --image="applications-games" \
        --text="<big><b>Vita Launcher Manager</b></big>\n\n<tt>$escaped_status</tt>\n\nThe Vita3K source is read-only. Automatic UPDATE GAMELISTS syncing remains enabled." \
        --button="_Sync":10 \
        --button="_Preview Cleanup":11 \
        --button="_Clean Stale":12 \
        --button="_Update Database":13 \
        --button="_Diagnostics":14 \
        --button="_View Log":15 \
        --button="_Help":16 \
        --button="_Close":0 >/dev/null 2>&1
    choice=$?

    case "$choice" in
        10)
            run_action "Syncing PS Vita launchers" "$PYTHON_BIN" -S "$APP" sync
            ;;
        11)
            run_action "Previewing stale-launcher cleanup" "$PYTHON_BIN" -S "$APP" sync --cleanup --dry-run
            ;;
        12)
            if confirm_cleanup; then
                run_action "Cleaning stale PS Vita launchers" "$PYTHON_BIN" -S "$APP" sync --cleanup
            fi
            ;;
        13)
            run_action "Updating Vita3K TITLE-ID database" "$PYTHON_BIN" -S "$APP" update-db
            ;;
        14)
            run_action "Collecting diagnostics" "$PYTHON_BIN" -S "$APP" support-report
            ;;
        15)
            view_log
            ;;
        16)
            if [ -f "$HELP" ]; then
                show_file "$TITLE - Help" "$HELP"
            else
                show_message info "Help file is missing. Re-run install.sh from the release package."
            fi
            ;;
        0|1|252)
            break
            ;;
        *)
            break
            ;;
    esac
done

exit 0
