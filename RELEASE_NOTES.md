# Vita Launcher Manager v1.7.3

- Cleanup inspection/deletion failures now produce a failed sync while retaining successful work and retryable state.
- Manual launcher names containing TITLE IDs remain indexed and preserved. Generated filename suffixes still take priority over IDs in title text.
- Directories, FIFOs, and symlinks at canonical launcher paths are reported as collisions rather than successful launchers.
- Installer refuses symlinked child destinations before copying, rewriting, or chmodding files.
- Includes the current AI disclosure, credits, tests, and package checksums.

Validation: all 15 regression tests pass locally, with Python compilation, shell syntax checks, and release packaging. dadtrick's prior v1.7.2 Batocera 43.1 test confirmed 1,033 titles and no sync failures. The v1.7.3 patch still needs a hardware sync recheck after installation; cleanup failure cases were tested with isolated temporary files.

Extract the ZIP on Batocera and run `bash install.sh`. Existing configuration is preserved.

Design and generated code: ChatGPT / Codex (OpenAI AI tools). Original idea, direction, time invested, and hands-on testing: dadtrick. See AI_DISCLOSURE.md for scope and limits.
