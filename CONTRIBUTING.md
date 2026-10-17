# Contributing

The goal is to make installed Vita games appear in Batocera with less manual
work. Keep changes understandable to someone familiar with Python and Bash.

## Start here

- `psvita_launcher.py`: metadata parsing, title resolution, launcher sync, state,
  CLI, and diagnostics. Normal sync uses the Python standard library.
- `psvita_manager.sh`: optional YAD interface to the CLI.
- `psvita_launcher_service` and `preupdate-gamelists-psvita-launcher-manager`:
  Batocera service and gamelist-hook integration.
- `install.sh`, `uninstall.sh`, `tools/build-release.sh`: deployment and packaging.
- `tests/`: isolated regression tests; they do not require a Batocera installation.

Read [the integration notes](docs/INTEGRATION.md) before changing paths, CLI
arguments, configuration keys, or launcher/state formats.

## Code style

Use PEP 8 naming and four-space indentation for Python. Use four-space block
indentation in Bash, quote path expansions, and use arrays for argument lists.
Keep heredoc contents valid in their own language. `.editorconfig` records the
whitespace rules; `.gitattributes` keeps source files on LF line endings.

Prefer direct functions with descriptive names. Extract a helper when it removes
real duplication or names a useful operation. Comments should explain a format,
compatibility constraint, or decision that the code cannot make clear on its own.
Avoid unrelated rewrites and new runtime dependencies for formatting or logging.

The backend stays in one Python file so Batocera installs remain simple. Bash
uses arrays and process substitution, so these scripts deliberately require Bash
rather than claiming POSIX `sh` compatibility.

## Run checks

Use Python 3.9 or newer and Bash:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile psvita_launcher.py tests/*.py
for file in *.sh psvita_launcher_service preupdate-gamelists-psvita-launcher-manager tools/*.sh; do
    bash -n "$file" || exit
done
```

To build a source ZIP, also install `zip` and the standard checksum utilities:

```bash
bash tools/build-release.sh --check-metadata
bash tools/build-release.sh
```

The builder checks version agreement and writes a ZIP and SHA-256 checksum to
`dist/`. Tests use temporary paths and fake failures. Run storage and installer
tests in fixtures, rather than pointing them at a live Vita3K tree.

## Submit a change

Describe the user-visible problem, the resulting behavior, and the checks you
ran. Preserve existing user names and configuration. Add a regression test for
a changed behavior or a reproduced bug; documentation and formatting changes
usually need only the existing checks.

Disclose material AI assistance and review its output as you would any proposed
code. Keep test claims specific to the evidence. See [AI_DISCLOSURE.md](AI_DISCLOSURE.md).

This project's original code uses the [MIT license](LICENSE). Keep upstream
credits intact. Vita3K or Batocera compatibility issues belong upstream when the
problem reproduces without this launcher utility; include a minimal reproduction
and the relevant upstream versions.
