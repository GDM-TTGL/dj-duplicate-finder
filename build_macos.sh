#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$ROOT/.mac-build"
OUT_DIR="$ROOT/dist-mac"
PYTHON_VERSION="3.12"
FFMPEG_VERSION="8.1.3"

fail() { echo "Error: $*" >&2; exit 1; }
command -v brew >/dev/null 2>&1 || fail "Para compilar necesitas Homebrew en esta Mac."
command -v xcrun >/dev/null 2>&1 || fail "Instala Xcode Command Line Tools en esta Mac."
brew install "python@$PYTHON_VERSION" "python-tk@$PYTHON_VERSION"
PYTHON="$(brew --prefix "python@$PYTHON_VERSION")/bin/python$PYTHON_VERSION"
[ -x "$PYTHON" ] || fail "No se encontró Python $PYTHON_VERSION de Homebrew."

ARCH="$("$PYTHON" -c 'import platform; print(platform.machine())')"
case "$ARCH" in arm64|x86_64) ;; *) fail "Arquitectura Mac no compatible: $ARCH" ;; esac

mkdir -p "$BUILD_DIR" "$OUT_DIR"
FFMPEG_ARCHIVE="$BUILD_DIR/ffmpeg-$FFMPEG_VERSION.tar.xz"
FFMPEG_SOURCE="$BUILD_DIR/ffmpeg-$FFMPEG_VERSION"
FFMPEG_PREFIX="$BUILD_DIR/ffmpeg-install-$ARCH"
if [ ! -f "$FFMPEG_ARCHIVE" ]; then
  curl --fail --location --retry 3 "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" --output "$FFMPEG_ARCHIVE"
fi
if [ ! -d "$FFMPEG_SOURCE" ]; then
  tar -xJf "$FFMPEG_ARCHIVE" -C "$BUILD_DIR"
fi
rm -rf "$FFMPEG_PREFIX"
(
  cd "$FFMPEG_SOURCE"
  ./configure --prefix="$FFMPEG_PREFIX" --arch="$ARCH" \
    --disable-gpl --disable-nonfree --disable-shared --enable-static \
    --disable-doc --disable-debug --disable-autodetect \
    --enable-ffmpeg --enable-ffprobe
  make -j"$(sysctl -n hw.logicalcpu)"
  make install
)
FFMPEG="$FFMPEG_PREFIX/bin/ffmpeg"
FFPROBE="$FFMPEG_PREFIX/bin/ffprobe"
[ -x "$FFMPEG" ] && [ -x "$FFPROBE" ] || fail "No se pudieron compilar FFmpeg y ffprobe."
"$FFMPEG" -version | head -n 1
"$FFPROBE" -version | head -n 1
"$FFMPEG" -L 2>&1 | grep -q 'LGPL version 2.1 or later' || fail "La compilación FFmpeg no reportó la licencia LGPL esperada."
"$FFMPEG" -buildconf 2>&1 | grep -q -- '--disable-gpl' || fail "FFmpeg no confirmó --disable-gpl."
"$FFMPEG" -buildconf 2>&1 | grep -q -- '--disable-nonfree' || fail "FFmpeg no confirmó --disable-nonfree."

BUILD_VENV="$BUILD_DIR/venv-$ARCH"
if [ ! -x "$BUILD_VENV/bin/python" ]; then "$PYTHON" -m venv "$BUILD_VENV"; fi
source "$BUILD_VENV/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$ROOT/requirements.txt" 'pyinstaller>=6.22,<7'

ICONSET="$BUILD_DIR/DJ_Duplicate_Finder.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
PNG="$ROOT/assets/DJ_Duplicate_Finder.png"
for spec in '16 16' '16 32' '32 32' '32 64' '128 128' '128 256' '256 256' '256 512' '512 512' '512 1024'; do
  set -- $spec
  logical="$1"; pixels="$2"
  suffix=""
  [ "$pixels" = "$((logical * 2))" ] && suffix="@2x"
  sips -s format png -z "$pixels" "$pixels" "$PNG" --out "$ICONSET/icon_${logical}x${logical}${suffix}.png" >/dev/null
done
ICON="$BUILD_DIR/DJ_Duplicate_Finder.icns"
iconutil -c icns "$ICONSET" -o "$ICON"

DIST="$BUILD_DIR/pyinstaller-dist"
WORK="$BUILD_DIR/pyinstaller-work"
rm -rf "$DIST" "$WORK"
python -m PyInstaller --noconfirm --clean --windowed \
  --name 'DJ Duplicate Finder' \
  --icon "$ICON" \
  --osx-bundle-identifier 'com.djduplicatefinder.app' \
  --add-data "$PNG:assets" \
  --add-binary "$FFMPEG:ffmpeg" \
  --add-binary "$FFPROBE:ffmpeg" \
  --distpath "$DIST" --workpath "$WORK" \
  "$ROOT/app.py"

APP="$DIST/DJ Duplicate Finder.app"
[ -d "$APP" ] || fail "PyInstaller no creó la aplicación .app."
BUNDLED_FFMPEG="$(find "$APP/Contents/Frameworks" -type f -path '*/ffmpeg/ffmpeg' -print -quit)"
BUNDLED_FFPROBE="$(find "$APP/Contents/Frameworks" -type f -path '*/ffmpeg/ffprobe' -print -quit)"
[ -x "$BUNDLED_FFMPEG" ] && [ -x "$BUNDLED_FFPROBE" ] || fail "No se encontraron los ejecutables empaquetados de FFmpeg."
"$BUNDLED_FFMPEG" -version >/dev/null
"$BUNDLED_FFPROBE" -version >/dev/null
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

STAGE="$BUILD_DIR/dmg-root"
rm -rf "$STAGE"
mkdir -p "$STAGE"
ditto "$APP" "$STAGE/DJ Duplicate Finder.app"
ln -s /Applications "$STAGE/Applications"
cp "$ROOT/LEEME_Mac.txt" "$STAGE/LEEME.txt"
cp "$FFMPEG_SOURCE/COPYING.LGPLv2.1" "$STAGE/Licencia FFmpeg LGPLv2.1.txt"
cp "$FFMPEG_ARCHIVE" "$STAGE/Codigo fuente FFmpeg $FFMPEG_VERSION.tar.xz"
cat > "$STAGE/Avisos de terceros.txt" <<EOF
DJ Duplicate Finder v3.0.4 para macOS

FFmpeg $FFMPEG_VERSION y ffprobe se compilaron desde el codigo fuente oficial adjunto con --disable-gpl y --disable-nonfree. FFmpeg reporto LGPL version 2.1 or later al compilarse. El codigo fuente exacto se incluye en este disco como Codigo fuente FFmpeg $FFMPEG_VERSION.tar.xz y su licencia como Licencia FFmpeg LGPLv2.1.txt.
Fuente upstream: https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz
EOF
DMG="$OUT_DIR/DJ_Duplicate_Finder_v3_Mac_${ARCH}.dmg"
rm -f "$DMG"
hdiutil create -volname 'DJ Duplicate Finder v3' -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

echo "Listo: $DMG"
echo "Arquitectura: $ARCH"
echo "FFmpeg/ffprobe estaticos, LGPL y ejecutados desde la app."
