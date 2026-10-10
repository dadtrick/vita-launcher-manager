# Vita Launcher Manager v1.7.2

- Failed launcher creation or renaming now reports a failed sync; successful partial work remains tracked.
- Dry-run sync skips automatic database downloads and writes. The operation lock file is still used.
- Launcher tracking and cleanup use the final TITLE-ID suffix, so bracketed IDs in game names are handled correctly.

Validation: all 11 unit tests passed locally, along with Python compilation and shell syntax checks. Live Batocera GUI and hook integration were not retested for this patch release.

Extract the release ZIP on Batocera and run `bash install.sh` (or `bash install.sh --cli-only`). Existing configuration is preserved. Run **GAME SETTINGS -> UPDATE GAMELISTS** after installation.
