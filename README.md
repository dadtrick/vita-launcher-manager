# Vita Launcher Manager for Batocera

![Vita Launcher Manager](assets/vita_launcher_manager_logo.png)

A lightweight Batocera utility that creates the empty `.psvita` launcher files
EmulationStation expects for games already installed in Vita3K.

The project is designed around Batocera's documented Vita workflow:

- Vita3K installs titles under `/userdata/saves/psvita/ux0/app/<TITLE ID>`.
- Batocera scans `/userdata/roms/psvita`.
- A launcher may be an empty file as long as its filename contains the TITLE ID,
  for example `Street Fighter X Tekken (USA) [PCSE00005].psvita`.

Official Batocera reference:
https://wiki.batocera.org/systems:psvita

## Project status

**Feature complete.** This public release is intended to be useful as-is; there
is no promised roadmap or support SLA.

Tested baseline: **Batocera v43, x86_64**. Batocera currently documents Vita3K
as x86_64-only. The installer also checks the actual services and gamelist-hook
capabilities it needs, so later Batocera versions may work without modification.

## Why use it?

Without this utility, an installed Vita game generally needs a launcher created
manually in `/userdata/roms/psvita` with the correct TITLE ID.

With this utility:

1. Install a game ZIP through Vita3K.
2. Verify the game installed.
3. Delete the original ZIP if you want to reclaim space.
4. Choose **GAME SETTINGS -> UPDATE GAMELISTS** in Batocera.
5. Missing `.psvita` launchers are created before EmulationStation rescans ROMs.

No polling daemon runs in the background.

## Safety model

`/userdata/saves/psvita` is **read-only input** to this project.

The project never intentionally creates, renames, deletes, chmods, or edits
anything inside that Vita3K tree. It only scans TITLE-ID directories and reads
small `sce_sys/param.sfo` metadata files.

Writable project locations are limited to the launcher output and the project's
own state/configuration paths. The backend and installer both reject writable
paths that resolve under Vita3K storage.

Stale-launcher cleanup is **off by default**. Explicit cleanup can delete only a
launcher that all of these checks identify as project-owned:

- the TITLE ID is no longer installed;
- the launcher is recorded in the project's managed-state file;
- it is still a regular non-symlink `.psvita` file;
- its filename still contains the recorded TITLE ID;
- it is still zero bytes.

If a tracked launcher was modified or replaced, the project relinquishes
management instead of deleting it.

## Resource use

The normal UPDATE GAMELISTS path is event-driven:

- no polling process;
- no resident Python process;
- no persistent project CPU/RAM use during gameplay;
- one non-recursive `ux0/app` scan per sync by default;
- cached local `PARAM.SFO` names avoid repeated file reads;
- concurrent operations time out rather than blocking EmulationStation forever.

The GUI is also on-demand and exits completely when closed.

## Requirements

Core functionality:

- Batocera with `batocera-services`;
- Batocera's `batocera-preupdate-gamelists-hook` dispatcher;
- Python 3.9+;
- Vita3K using the standard Batocera data layout, unless you deliberately edit
  `config.ini`.

Optional GUI:

- YAD/GTK. The installer only creates GUI shortcuts when `yad` is actually
  available.

Internet access is **not required for installation or normal syncing**. Network
access is used only when the user explicitly chooses **Update Database**.

## Install

Download the release ZIP, extract it on Batocera, then from SSH or a terminal:

```bash
cd /path/to/vita-launcher-manager-v1.7.1
bash install.sh
```

A CLI-only install is also available:

```bash
bash install.sh --cli-only
```

The installer is idempotent for project-owned files and upgrades private v1.x
builds in place. It refuses to overwrite unrelated services/hooks and skips
foreign GUI shortcut files instead of clobbering them.

After a GUI install, run **GAME SETTINGS -> UPDATE GAMELISTS** once so the new
Ports entry is discovered.

## Normal use

The intended workflow is simply:

**GAME SETTINGS -> UPDATE GAMELISTS**

Batocera's pre-update hook runs the launcher sync first, then exits, and
Batocera continues its normal gamelist refresh.

## GUI

When YAD is available, open **Vita Launcher Manager** from either:

- EmulationStation -> Ports; or
- F1 -> Applications.

Actions:

- **Sync** - create missing launcher files now.
- **Preview Cleanup** - show proposed cleanup without deleting anything.
- **Clean Stale** - confirmed opt-in cleanup of project-managed stale launchers.
- **Update Database** - manually refresh optional Vita3K compatibility names.
- **Diagnostics** - show a copy/paste support report.
- **View Log** - show recent automatic sync activity.
- **Help** - local quick-reference documentation.

Keyboard/mouse is the reliable input method for the YAD manager. Controller to
keyboard/mouse behavior varies by Batocera/controller configuration.

## Name resolution

For each installed TITLE ID, names are resolved in this order:

1. installed Vita3K `sce_sys/param.sfo` metadata;
2. optional local `title_ids.tsv` database generated from open Vita3K
   compatibility issues;
3. the TITLE ID itself.

The optional database is deliberately not downloaded during installation. This
keeps installation deterministic and avoids GitHub/network/rate-limit failures.

## Command line

Backend:

```bash
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py
```

Useful commands:

```bash
# Status
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py status

# Create missing launchers now
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py sync

# Preview all changes
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py sync --dry-run

# Preview stale cleanup
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py sync --cleanup --dry-run

# Explicit stale cleanup
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py sync --cleanup

# Optional online title-name database refresh
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py update-db

# Configuration and integration checks
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py doctor

# Copy/paste diagnostic report
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py support-report
```

## Files installed

Core:

```text
/userdata/system/psvita_launcher/
/userdata/system/services/psvita-launcher-manager
```

Automatic live hook while the service is active:

```text
/usr/share/emulationstation/hooks/preupdate-gamelists-psvita-launcher-manager
```

Optional GUI shortcuts:

```text
/userdata/roms/ports/Vita Launcher Manager.sh
/userdata/system/.local/share/applications/psvita-launcher-manager.desktop
```

## Uninstall

From the extracted release directory:

```bash
bash uninstall.sh
```

Uninstall removes project-owned services, hooks, state, and GUI shortcuts. It
**does not delete existing `.psvita` launcher files** or any Vita3K data.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For a single diagnostic report:

```bash
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py support-report
```

## Development / tests

The backend uses only the Python standard library.

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile psvita_launcher.py
bash -n install.sh uninstall.sh psvita_manager.sh psvita_manager_port.sh \
  psvita_launcher_service preupdate-gamelists-psvita-launcher-manager
```

Tests cover filename limits, PARAM.SFO parsing and size limits, read-only path
protection, managed cleanup, cache behavior, lock timeouts, and GitHub pagination
past 1,000 compatibility issues.

## Project scope

This project only creates/manages Batocera launcher files. It does not provide
or install Vita firmware, games, licenses, keys, or patches, and it does not fix
Vita3K compatibility problems.

See [SUPPORT.md](SUPPORT.md), [NOTICE.md](NOTICE.md), and [LICENSE](LICENSE).
