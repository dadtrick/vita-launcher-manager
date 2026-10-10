# Vita Launcher Manager v1.7.2

- Failed launcher creation or renaming now reports a failed sync; successful partial work remains tracked.
- Dry-run sync skips automatic database downloads and writes. The operation lock file is still used.
- Launcher tracking and cleanup use the final TITLE-ID suffix, so bracketed IDs in game names are handled correctly.

Validation: all 11 unit tests passed locally, along with Python compilation and shell syntax checks. Subsequent hands-on testing by dadtrick on Batocera 43.1 / Python 3.12.8 confirmed 0 diagnostic errors or warnings and a successful automatic UPDATE GAMELISTS sync of 1,033 titles (failed=0, unmatched=0, exit=0). GUI actions were not exercised in the supplied test results.

Extract the release ZIP on Batocera and run `bash install.sh` (or `bash install.sh --cli-only`). Existing configuration is preserved. Run **GAME SETTINGS -> UPDATE GAMELISTS** after installation.

## Design and credits

- **ChatGPT / Codex (OpenAI):** software design and code implementation, developed through collaboration with dadtrick.
- **dadtrick:** original idea, project direction, time invested, and hands-on testing on their Batocera system.

