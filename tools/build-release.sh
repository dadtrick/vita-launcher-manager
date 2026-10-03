#!/bin/bash
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=$(grep -m1 '^APP_VERSION = ' "$ROOT/psvita_launcher.py" | cut -d'"' -f2)
DIST="$ROOT/dist"
NAME="vita-launcher-manager-v$VERSION"
rm -rf "$DIST"
mkdir -p "$DIST"

cd "$ROOT"
python3 -m py_compile psvita_launcher.py
python3 -m unittest discover -s tests -q
for f in install.sh uninstall.sh psvita_manager.sh psvita_manager_port.sh psvita_launcher_service preupdate-gamelists-psvita-launcher-manager; do
    bash -n "$f"
done

rm -rf "$ROOT/__pycache__" "$ROOT/tests/__pycache__"

FILES=(
  README.md HELP.txt LICENSE NOTICE.md CHANGELOG.md RELEASE_NOTES.md SUPPORT.md TROUBLESHOOTING.md VERSION .gitignore
  config.ini install.sh uninstall.sh psvita_launcher.py psvita_manager.sh
  psvita_manager_port.sh psvita-launcher-manager.desktop psvita_launcher_service
  preupdate-gamelists-psvita-launcher-manager assets tests .github tools
)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/$NAME"
cp -a "${FILES[@]}" "$tmp/$NAME/"
(
  cd "$tmp/$NAME"
  find . -type f ! -name SHA256SUMS.txt -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS.txt
)
(
  cd "$tmp"
  zip -qr "$DIST/$NAME.zip" "$NAME"
)
(cd "$DIST" && sha256sum "$NAME.zip" > "$NAME.zip.sha256")
echo "Built: $DIST/$NAME.zip"
cat "$DIST/$NAME.zip.sha256"
