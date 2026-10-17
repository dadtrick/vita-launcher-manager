# Batocera integration and compatibility

This project follows Batocera's [documented PS Vita workflow](https://wiki.batocera.org/systems:psvita).
Vita3K owns installed applications and metadata; EmulationStation owns scanning
and launching. This utility generates the small files that connect those steps.

## Entry points and paths

| Interface | Contract |
| --- | --- |
| `psvita_launcher.py` | Existing CLI commands, flags, and exit codes remain compatible. Errors return nonzero. |
| `/userdata/system/psvita_launcher` | Persistent configuration, metadata cache, managed state, and logs. |
| `/userdata/saves/psvita` | Read-only Vita3K input; writes here are rejected. |
| `/userdata/roms/psvita` | Launcher output; manually named launchers are preserved by default. |
| `psvita-launcher-manager` service | Registers the live gamelist hook from persistent storage. |
| `preupdate-gamelists-psvita-launcher-manager` | Runs sync before the gamelist refresh and records its result. |

The hook exits successfully even if sync fails, so a Vita launcher error does not
stop Batocera from refreshing other systems. The backend exit code and hook log
retain the error. Do not make a polling process replace this event-driven path.

Batocera's `/userdata` layout is used instead of generic desktop XDG config and
data paths because it persists across Batocera upgrades. The live hook under
`/usr/share/emulationstation/hooks` is restored by the user service. The desktop
shortcut uses the existing freedesktop `.desktop` format.

## File and configuration formats

Launchers use Batocera's `.psvita` extension and contain no game data. Generated
names end with `[TITLEID].psvita`; the optional region appears before that suffix.
Manual filenames containing a valid title ID are also recognized. Preserve the
suffix preference so an ID in game-title text cannot override the actual ID.

`config.ini` uses Python's `ConfigParser`. Keep existing section and key names
compatible; add defaults when introducing an option. The managed-launcher and
title-cache files use tab-separated records with comment headers. State records
contain filenames, not arbitrary paths. Review migration behavior before changing
these formats or the ownership markers used by installation and cleanup.

## Dependency and implementation choices

The Python backend uses `argparse`, `configparser`, `csv`, and other standard
library modules instead of a private command framework or database service.
Local PARAM.SFO data is preferred; the Vita3K compatibility database is optional.
Network imports stay in update-only functions to keep normal sync local and light.

Shell handles Batocera service registration and the optional YAD interface.
Python handles structured metadata and file state. The persistent `psvita_*`
names remain after the public rebrand to avoid breaking existing installations.

Changes to these contracts should describe the reason, migration, and tests in
the pull request. A simpler internal function layout does not require a new
public interface.
