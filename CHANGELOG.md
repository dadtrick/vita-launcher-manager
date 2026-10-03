# Changelog

## 1.7.1 - Vita Launcher Manager rebrand

- Renamed the public-facing project to **Vita Launcher Manager**.
- Added the project logo under `assets/vita_launcher_manager_logo.png`.
- Renamed the Batocera Ports shortcut to `Vita Launcher Manager.sh`.
- Preserved the established internal `psvita_*` paths, service name, hook name,
  configuration, and ownership markers for safe upgrades from v1.x.
- Installer/uninstaller recognize and clean up the previous public shortcut name
  only when it is positively identified as project-owned.

## 1.7.0 - Public release hardening

- Installer no longer performs network access.
- Namespaced the Batocera service and pre-update hook to reduce collision risk.
- Installer and uninstaller verify ownership before overwriting/removing files.
- Installer validates all destinations before writing and preserves the
  read-only Vita3K guarantee during installation.
- GUI shortcuts are installed only when YAD is available; `--cli-only` is
  supported.
- Added local Help and a copy/paste `support-report` diagnostic command.
- Added last automatic-sync status tracking.
- Added a 4 MiB PARAM.SFO read limit for corrupt/untrusted metadata.
- Concurrent operations now time out instead of waiting indefinitely.
- Dry-run summaries use `would_create`, `would_rename`, and `would_delete`.
- Added automated unit tests and GitHub CI.
- Added README, troubleshooting, support policy, license, and project notices.

## 1.6.0

- Added optional YAD GUI and Ports/F1 launchers.
- Added status, diagnostics, manual sync, cleanup preview, explicit cleanup,
  database update, and log viewing.

## 1.5.1

- Fixed GitHub compatibility-database pagination beyond 1,000 issues.

## 1.5.0

- Hardened Vita3K read-only protection, legacy-watcher migration, filename
  length handling, and low-overhead `python3 -S` execution.
