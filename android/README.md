# Hush for TVs and tablets

One Android app covers **Android TV / Google TV (TCL, Sony, Philips...)**, **Amazon Fire TV / Fire Stick** and **Android tablets**. It is the Hush web app full screen, with the remote's keys and its own updater. The web app on your server is unchanged. **LG** TVs use the webOS app in `../webos` (below).

On first start the app asks for **your Hush server's address** (for example `http://192.168.100.228`) and checks that a Hush server answers there before it saves it. Menu key (or Settings → This app inside Hush) changes it later.

## Install

| Device | How |
|---|---|
| **Fire TV / Fire Stick** | Install the **Downloader** app from the Amazon store. Settings → My Fire TV → Developer options → *Install unknown apps* → turn on Downloader. In Downloader open the APK link from the latest release (github.com/five92llc/hush/releases) and install. |
| **TCL / Google TV / Android TV** | Install **Downloader** from Google Play, allow it under Settings → Apps → Security & restrictions → *Install unknown apps*, then open the release's APK link. Or from a computer: `adb connect <tv-ip>` then `adb install hush-tv-X.Y.Z.apk`. |
| **Android tablet** | Open the release's APK in the tablet's browser and install it. |
| **LG webOS** | See below. |

## Updates

The app asks GitHub for a newer release when it starts (at most every 6 hours). If there is one it offers **Update now**; it downloads the APK, checks its checksum and hands it to Android's installer, which shows one **Install** confirmation. Android does not let an app replace itself silently. The first time, Android asks you to allow Hush to install apps (Settings → *Install unknown apps* → Hush). *Menu → Check for updates* checks on demand.

## Publish a new version

```bash
git tag android-v1.0.1 && git push origin android-v1.0.1
```

GitHub Actions (`.github/workflows/release-apps.yml`) builds the signed APK and the LG package and attaches both to the release; every installed app then offers the update. **Version numbers must go up.**

### One-time setup: the signing key
Every update must be signed with the **same key**, or Android refuses to install it over the old version. The key lives in `android/keystore/` (never committed; keep a backup of this folder somewhere safe!). Add these four **repository secrets** in GitHub (Settings → Secrets and variables → Actions) so the cloud build signs with it:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -i android/keystore/hush-release.jks \| pbcopy` |
| `ANDROID_KEYSTORE_PASSWORD` | `storePassword` from `android/keystore/keystore.properties` |
| `ANDROID_KEY_ALIAS` | `keyAlias` from the same file (`hush`) |
| `ANDROID_KEY_PASSWORD` | `keyPassword` from the same file |

## Build it yourself

```bash
cd android
./gradlew assembleRelease -PversionName=1.0.0     # app/build/outputs/apk/release/app-release.apk
```
Needs JDK 17 and the Android SDK (platform 34, build-tools 34.0.0).

## LG webOS (`../webos`)

LG TVs do not run Android, so they get a small webOS app that remembers your server address and opens Hush. Because it opens the web app on your server, **the interface updates whenever your server does**; the package itself rarely changes.

1. On the TV install **Developer Mode** (LG Content Store) and turn it on; note the TV's IP and passphrase.
2. On your computer: `npm i -g @webos-tools/cli`, then `ares-setup-device` (add the TV as `lgtv`).
3. `ares-package webos` then `ares-install --device lgtv com.hush.app_1.0.0_all.ipk`, and `ares-launch --device lgtv com.hush.app`.
   Or take the `.ipk` from the latest release.

Developer Mode on LG expires every 50 hours unless you press *Extend* in the Developer Mode app (it can be extended from the app; LG's rule, not Hush's).
