#!/usr/bin/env bash
# Build the Android app and the LG package on this Mac and publish them as a GitHub release.
#   ./android/release.sh 1.0.1
# Installed apps then offer the update by themselves. The version must be higher than the last one.
set -euo pipefail
VERSION="${1:?Usage: android/release.sh <version>   e.g. 1.0.1}"
cd "$(dirname "$0")"

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
[ -f keystore/hush-release.jks ] || { echo "The signing key android/keystore/hush-release.jks is missing."; exit 1; }
command -v gh >/dev/null || { echo "Install the GitHub CLI first: brew install gh"; exit 1; }

echo ">> Building the Android app $VERSION"
./gradlew --no-daemon assembleRelease -PversionName="$VERSION"
APK="hush-tv-$VERSION.apk"
cp app/build/outputs/apk/release/app-release.apk "$APK"

echo ">> Building the LG webOS package"
rm -rf ../webos-build && cp -R ../webos ../webos-build
sed -i '' "s/\"version\": \"[0-9.]*\"/\"version\": \"$VERSION\"/" ../webos-build/appinfo.json
npx -y -p @webos-tools/cli ares-package ../webos-build -o .
rm -rf ../webos-build
IPK="com.hush.app_${VERSION}_all.ipk"

echo ">> Publishing release android-v$VERSION"
gh release create "android-v$VERSION" "$APK" "$IPK" --repo five92llc/hush \
  --title "Hush apps $VERSION" \
  --notes "Android app (TVs, Fire TV, tablets): $APK. Installed apps offer this update by themselves.
LG webOS app: $IPK."
rm -f "$APK" "$IPK"
echo ">> Done: https://github.com/five92llc/hush/releases/tag/android-v$VERSION"
