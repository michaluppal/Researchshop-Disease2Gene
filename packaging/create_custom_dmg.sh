#!/bin/bash
# Script to create a custom-designed DMG for Disease2Gene

APP_NAME="Disease2Gene"
VOL_NAME="Disease2Gene Installer"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist"
BG_IMG="${SCRIPT_DIR}/dmg_background_custom.png"
BG_IMG_NAME="$(basename "${BG_IMG}")"
ICON_FILE="${SCRIPT_DIR}/Disease2Gene.icns"
ICON_SIZE=128
WINDOW_WIDTH=800
WINDOW_HEIGHT=500
ICON_APP_X=300
ICON_APP_Y=300
ICON_DEST_X=700
ICON_DEST_Y=300
WINDOW_WIDTH=1000
WINDOW_HEIGHT=640

# Cleanup previous attempts
rm -rf "${DIST_DIR}/${APP_NAME}.dmg"
rm -rf "${DIST_DIR}/pack.temp.dmg"
rm -rf "${DIST_DIR}/dmg_staging"

# Ensure we have an .app bundle (PyInstaller one-dir builds won't create one)
APP_BUNDLE="${DIST_DIR}/${APP_NAME}.app"
ONE_DIR_BUILD="${DIST_DIR}/${APP_NAME}"

if [ ! -d "${APP_BUNDLE}" ]; then
  if [ -d "${ONE_DIR_BUILD}" ]; then
    echo "Creating .app bundle from one-dir build..."
    rm -rf "${APP_BUNDLE}"
    mkdir -p "${APP_BUNDLE}/Contents/MacOS" "${APP_BUNDLE}/Contents/Resources"
    cp -R "${ONE_DIR_BUILD}/." "${APP_BUNDLE}/Contents/MacOS/"
    chmod +x "${APP_BUNDLE}/Contents/MacOS/${APP_NAME}" || true
    if [ -f "${ICON_FILE}" ]; then
      cp "${ICON_FILE}" "${APP_BUNDLE}/Contents/Resources/"
    fi
    cat > "${APP_BUNDLE}/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>pl.researchshop.disease2gene</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleIconFile</key>
  <string>Disease2Gene.icns</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>LSMinimumSystemVersion</key>
  <string>10.15</string>
</dict>
</plist>
EOF
  else
    echo "ERROR: ${APP_BUNDLE} not found and ${ONE_DIR_BUILD} is missing."
    echo "Build the app bundle first (e.g. PyInstaller .spec) or provide a one-dir build."
    exit 1
  fi
fi

# Always refresh the app icon in the bundle if available
if [ -d "${APP_BUNDLE}" ] && [ -f "${ICON_FILE}" ]; then
  cp "${ICON_FILE}" "${APP_BUNDLE}/Contents/Resources/"
  touch "${APP_BUNDLE}/Contents/Info.plist"
  touch "${APP_BUNDLE}"
fi

# Prepare staging
mkdir -p "${DIST_DIR}/dmg_staging"
cp -R "${DIST_DIR}/${APP_NAME}.app" "${DIST_DIR}/dmg_staging/"
ln -s /Applications "${DIST_DIR}/dmg_staging/Applications"

echo "Creating temporary DMG..."
hdiutil create -srcfolder "${DIST_DIR}/dmg_staging" -volname "${VOL_NAME}" -fs HFS+ \
      -fsargs "-c c=64,a=16,e=16" -format UDRW -size 200m "${DIST_DIR}/pack.temp.dmg"

echo "Mounting temporary DMG..."
attach_out=$(hdiutil attach -readwrite -noverify -noautoopen "${DIST_DIR}/pack.temp.dmg" 2>&1)
parse_out=$(ATTACH_OUT="${attach_out}" python3 - <<'PY'
import os
lines = os.environ.get("ATTACH_OUT", "").splitlines()
device = ""
mount = ""
for line in lines:
    if line.startswith("/dev/") and "/Volumes/" in line:
        parts = line.split()
        device = parts[0]
        mount = " ".join(parts[2:]) if len(parts) >= 3 else ""
        break
print(f"{device}|{mount}")
PY
)
device="${parse_out%%|*}"
mount_dir="${parse_out#*|}"
vol_name="$(basename "${mount_dir}")"

if [ -z "${mount_dir}" ]; then
  echo "ERROR: Failed to determine mount point. hdiutil output:"
  echo "${attach_out}"
  exit 1
fi
sleep 2

echo "Applying customizations..."
# Copy background image
mkdir -p "${mount_dir}/.background"
cp "${BG_IMG}" "${mount_dir}/.background/${BG_IMG_NAME}"
sleep 1

# Set Volume Icon (if SetFile is available)
if command -v SetFile >/dev/null 2>&1; then
  if [ -f "${ICON_FILE}" ]; then
    cp "${ICON_FILE}" "${mount_dir}/.VolumeIcon.icns"
    SetFile -c icnC "${mount_dir}/.VolumeIcon.icns"
    SetFile -a C "${mount_dir}"
  fi
fi

# AppleScript to set layout
echo '
   tell application "Finder"
     tell disk "'${vol_name}'"
           open
           set current view of container window to icon view
           set toolbar visible of container window to false
           set statusbar visible of container window to false
           set the bounds of container window to {300, 140, 1300, 780}
           set theViewOptions to the icon view options of container window
           set arrangement of theViewOptions to not arranged
           set icon size of theViewOptions to '${ICON_SIZE}'
           set background picture of theViewOptions to file ".background:'${BG_IMG_NAME}'"
           delay 1
           set position of item "'${APP_NAME}'.app" of container window to {'${ICON_APP_X}', '${ICON_APP_Y}'}
           set position of item "Applications" of container window to {'${ICON_DEST_X}', '${ICON_DEST_Y}'}
           update without registering applications
           delay 5
           close
     end tell
   end tell
' | osascript

sync

echo "Detaching temporary DMG..."
hdiutil detach "${mount_dir}"

echo "Compressing final DMG..."
hdiutil convert "${DIST_DIR}/pack.temp.dmg" -format UDZO -o "${DIST_DIR}/${APP_NAME}.dmg"
rm -f "${DIST_DIR}/pack.temp.dmg"

echo "Done: ${DIST_DIR}/${APP_NAME}.dmg"
