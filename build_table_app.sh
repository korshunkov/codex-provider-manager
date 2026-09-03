#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
APP="$ROOT/dist/Модели Codex.app"
CONTENTS="$APP/Contents"

rm -rf "$APP"
mkdir -p "$CONTENTS/MacOS" "$CONTENTS/Resources"

cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>ru</string>
    <key>CFBundleDisplayName</key>
    <string>Модели Codex</string>
    <key>CFBundleExecutable</key>
    <string>ProviderModelPicker</string>
    <key>CFBundleIdentifier</key>
    <string>local.codex.provider-model-picker</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Модели Codex</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.utilities</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
</dict>
</plist>
PLIST

/usr/bin/swiftc -parse-as-library -O \
    -o "$CONTENTS/MacOS/ProviderModelPicker" \
    "$ROOT/src/ProviderModelPicker.swift"

/usr/bin/codesign --force --sign - "$APP"

if [[ "${1:-}" == "--install" ]]; then
    target="/Users/admin/Applications/Модели Codex.app"
    rm -rf "$target"
    /usr/bin/ditto "$APP" "$target"
    /usr/bin/codesign --force --sign - "$target"
    print "Установлено: $target"
else
    print "Собрано: $APP"
fi
