# Support policy

This is a small, feature-complete community utility. There is no guaranteed
support SLA or promise of ongoing releases.

## Supported baseline

- Batocera Linux v43
- x86_64
- Vita3K using Batocera's default `/userdata/saves/psvita` data location
- Python 3.9+

The installer checks required Batocera capabilities rather than relying only on
a version number, so later releases may work, but v43 x86_64 is the tested
baseline.

## Before reporting a software bug

Run:

```bash
/usr/bin/python3 -S /userdata/system/psvita_launcher/psvita_launcher.py support-report
```

Then reproduce the problem once and include the complete report in the issue.
The report contains application paths, counts, versions, and recent project log
lines; it does not read game contents beyond the normal TITLE-ID/PARAM.SFO scan.

## In scope for bug reports

- Installer/uninstaller defects
- Incorrect launcher creation or preservation behavior
- Read-only safety failures
- GUI failures on an otherwise supported Batocera image
- Reproducible database-updater defects

## Out of scope

- Obtaining games, firmware, keys, or copyrighted content
- Vita3K game compatibility, performance, crashes, or rendering issues
- General Batocera setup or controller configuration
- Custom operating systems that only resemble Batocera
- Requests to make unsupported game dumps work

The project intentionally fails conservatively when it cannot prove an operation
is safe.
