# Troubleshooting

Start with the built-in report:

```bash
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py support-report
```

## Manager is not shown in Ports

Run **GAME SETTINGS -> UPDATE GAMELISTS** once after installation. Batocera only
adds a new `.sh` Ports entry after a gamelist refresh.

If the installer reported that YAD is unavailable, no GUI shortcut is installed.
The automatic UPDATE GAMELISTS integration still works.

## GUI does not open

From SSH run:

```bash
command -v yad
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py doctor
```

The GUI is optional. It is only installed when YAD is detected.

## No Vita games were found

The default source is:

```text
/userdata/saves/psvita/ux0/app
```

Vita3K must have actually installed the game there. Installer ZIP files are not
scanned and are not launchers.

## UPDATE GAMELISTS does not create launchers

Check:

```bash
batocera-services status psvita-launcher-manager
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py doctor
tail -n 100 /userdata/system/psvita_launcher/psvita_launcher.log
```

Re-running `bash install.sh` is safe and repairs project-owned integration files.
It will not overwrite unrelated hooks/shortcuts.

## "Another Vita Launcher Manager operation is already running"

A database refresh or another sync is still active. Let it finish, then run
UPDATE GAMELISTS again. The timeout exists so EmulationStation never waits
indefinitely behind a manual network operation.

## Update Database fails

The database is optional. Launcher generation first reads the installed game's
`PARAM.SFO` and falls back to the TITLE ID if no name is available. A GitHub
network/rate-limit failure therefore does not stop normal use. Try the database
refresh later if you want it.

## A game name is stale or wrong

The local title cache is safe to delete:

```bash
rm -f /userdata/system/psvita_launcher/title_cache.tsv
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py sync
```

This only forces a reread of installed `PARAM.SFO` metadata.

## Stale launchers

Use **Preview Cleanup** first. Actual cleanup is explicit and can remove only
project-managed, zero-byte `.psvita` files whose TITLE ID is no longer installed.
Manually created or modified launcher files are preserved.

## Configuration error

The installer keeps a backup before merging an existing configuration:

```text
/userdata/system/psvita_launcher/config.ini.pre-v1.7.bak
```

No writable project path is allowed anywhere below `/userdata/saves/psvita`.
