#!/bin/bash
# Developed with ChatGPT / Codex AI assistance, directed by dadtrick.
# See AI_DISCLOSURE.md at the repository root for attribution and test limits.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
CHECK_METADATA=false

case "${1:-}" in
    "") ;;
    --check-metadata) CHECK_METADATA=true ;;
    *)
        echo "Usage: $0 [--check-metadata]" >&2
        exit 2
        ;;
esac
if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [--check-metadata]" >&2
    exit 2
fi

# Validate release metadata before deleting or creating any release files.
VERSION=$(cat "$ROOT/VERSION")
APP_VERSION=$(python3 -S "$ROOT/psvita_launcher.py" --version)
# The installer keeps its version as one literal VERSION="X.Y.Z" assignment.
INSTALL_VERSION=$(sed -n 's/^VERSION="\([^"]*\)"$/\1/p' "$ROOT/install.sh")
for version in "$VERSION" "$APP_VERSION" "$INSTALL_VERSION"; do
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo "ERROR: VERSION, CLI --version, and installer VERSION must use X.Y.Z." >&2
        exit 1
    fi
done
if [ "$VERSION" != "$APP_VERSION" ] || [ "$VERSION" != "$INSTALL_VERSION" ]; then
    echo "ERROR: release versions do not match: VERSION=$VERSION, CLI=$APP_VERSION, installer=$INSTALL_VERSION" >&2
    exit 1
fi

if [ "$CHECK_METADATA" = true ]; then
    echo "Release metadata OK: $VERSION"
    exit 0
fi

# Prepare the release output directory.
DIST="$ROOT/dist"
NAME="vita-launcher-manager-v$VERSION"
rm -rf "$DIST"
mkdir -p "$DIST"

# Check the application and shell entry points before staging the archive.
cd "$ROOT"
python3 -m py_compile psvita_launcher.py
python3 -m unittest discover -s tests -q
for f in install.sh uninstall.sh psvita_manager.sh psvita_manager_port.sh psvita_launcher_service preupdate-gamelists-psvita-launcher-manager; do
    bash -n "$f"
done

rm -rf "$ROOT/__pycache__" "$ROOT/tests/__pycache__"

# Stage the public source package and its contributor metadata.
FILES=(
    README.md AI_DISCLOSURE.md HELP.txt LICENSE NOTICE.md CHANGELOG.md
    RELEASE_NOTES.md SUPPORT.md TROUBLESHOOTING.md CONTRIBUTING.md
    VERSION .gitignore .editorconfig .gitattributes
    config.ini install.sh uninstall.sh psvita_launcher.py psvita_manager.sh
    psvita_manager_port.sh psvita-launcher-manager.desktop psvita_launcher_service
    preupdate-gamelists-psvita-launcher-manager assets docs tests .github tools
)

STAGING_DIR=$(mktemp -d)
trap 'rm -rf "$STAGING_DIR"' EXIT
mkdir -p "$STAGING_DIR/$NAME"
cp -a "${FILES[@]}" "$STAGING_DIR/$NAME/"
(
    cd "$STAGING_DIR/$NAME"
    find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
    sha256sum -c SHA256SUMS.txt >/dev/null
)

# Create the archive and verify its published checksum.
(
    cd "$STAGING_DIR"
    zip -qr "$DIST/$NAME.zip" "$NAME"
)
(
    cd "$DIST"
    sha256sum "$NAME.zip" > "$NAME.zip.sha256"
    sha256sum -c "$NAME.zip.sha256"
)
echo "Built: $DIST/$NAME.zip"
cat "$DIST/$NAME.zip.sha256"
