# Vita Launcher Manager v1.7.1

Vita Launcher Manager is a lightweight Batocera utility that creates the `.psvita` launcher files EmulationStation expects for titles already installed in Vita3K.

## Highlights

- Event-driven integration with **GAME SETTINGS -> UPDATE GAMELISTS**.
- No resident Python process or polling daemon.
- Treats `/userdata/saves/psvita` as read-only input.
- Optional YAD GUI from Batocera Ports / F1 Applications.
- Offline, idempotent installer with collision/ownership checks.
- Safe upgrade path from earlier v1.x / v1.7.0 builds.
- Manual database refresh, diagnostics, support report, and stale-launcher cleanup preview.
- Automated unit tests and GitHub Actions CI.

## v1.7.1

This release changes the public-facing name to **Vita Launcher Manager** and adds the new project branding. Existing internal `psvita_*` paths and integration names are intentionally retained to keep upgrades compatible.

## Install

Extract the release ZIP on Batocera and run:

```bash
bash install.sh
```

For a backend-only install without GUI shortcuts:

```bash
bash install.sh --cli-only
```

After a GUI install, run **GAME SETTINGS -> UPDATE GAMELISTS** once so the Ports entry is discovered.

Tested baseline: **Batocera v43 x86_64**.
