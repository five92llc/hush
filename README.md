# Hush

A self-hosted media player that mutes profanity while you watch.

Hush runs on a home server or NAS and plays your movies, shows and music in any browser. It plays files from your NAS shares, folders, links, DLNA servers, Jellyfin and Plex.

Each title gets scanned once. Hush transcribes the dialogue with Whisper, or reads the subtitle track, and marks every word on your list. From then on those moments are muted, or covered with a soft tone, as the video plays.

Your original files are never changed.

![The player muting a word, with the Language panel open](docs/player.png)

```
 source file ──► ffprobe ──► play directly / remux / transcode ──► browser <video>
      │                                                              ▲
      └─► scan: audio → Whisper word timestamps ─┐                   │ Web Audio gain
                or subtitles → estimated timing ─┴─► word list ──► mute ranges ──┘
```

## What it plays

| Source | How it connects |
|---|---|
| Folder on the server | Any path, including NFS/CIFS mounts |
| SMB / NAS share | Direct SMB2/3 with `smbprotocol`, no mount needed (Windows, Synology, QNAP, TrueNAS) |
| Web folder or link | Direct files, nginx/Apache/Caddy listings, HLS `.m3u8` |
| DLNA / UPnP | SSDP discovery and ContentDirectory browsing (MiniDLNA, Serviio, UMS…) |
| FTP / SFTP | Browse and play from a server, with a source or a pasted `ftp://` / `sftp://` link |
| Jellyfin / Emby | API key, plays the original file |
| Plex | Token, plays the original file |

### Play a link

Paste any of these into **Play a link**:

| Link | Result |
|---|---|
| `https://…`, HLS `.m3u8` | Plays, scans and filters like a file |
| `smb://user:pass@nas/Share/folder/film.mkv` | Plays, scans and filters. End with `/` to browse a folder |
| `ftp://user:pass@host/folder/film.mkv`, `sftp://user:pass@host/…` | Plays, scans and filters. End with `/` to browse |
| `.m3u`, `.m3u8`, `.pls` playlist (link or file) | Opens like a folder: one entry per item, grouped by `group-title` for IPTV lists. Entries can be files, `http(s)`, `rtmp://` and other links. An `.m3u8` that is an HLS stream (`#EXT-X-` tags) plays as one video instead |
| `rtmp://`, `rtsp://`, `udp://`, `srt://`, `mms://` | Live or network streams. Played as they are: no scanning, seeking or filtering, because they have no fixed length |

Passwords inside a link are kept in the recent-links list in `data/hush.db`, and never shown in names. Prefer adding a source for anything you use often.

Formats include mp4, m4v, mov, mkv, webm, avi, wmv, flv, mpg, ts, m2ts, mp3, wav, flac, aac, m4a, ogg, opus, wma, aiff and ape. Anything FFmpeg can read will play.

Hush picks the cheapest playback path for each file:

- **Direct**: the browser plays the original bytes with range requests. Typical for mp4/H.264, mp3, wav and flac.
- **Remux**: the video is copied untouched and the audio is converted to AAC. Typical for MKV with H.264/VP9/AV1. This is nearly free on CPU.
- **Transcode**: a full H.264 encode, for HEVC, MPEG-2, DivX and similar. `video_encoder: auto` (the default) uses an NVIDIA (NVENC) or Intel/AMD (VAAPI) GPU when the server can see one, otherwise the CPU; you can also set `h264_nvenc`, `h264_vaapi` or `libx264` yourself. HEVC files are copied untouched to screens that can decode HEVC (most TVs, Fire TV, Safari-less browsers), so they need no re-encode.

## Quick start

### Docker (recommended)

```bash
cp config.example.yaml config.yaml          # edit your sources
echo "HUSH_PASSWORD=choose-a-good-one" > .env
docker compose up -d --build
```

Open `http://<server>:8642`.

The image includes Whisper. The first scan downloads the chosen model (`small.en` is about 250 MB) into the data volume. Build with `--build-arg WHISPER=0` for a small image that scans subtitles only.

### Without Docker

```bash
sudo apt install ffmpeg                      # or brew install ffmpeg
pip install -r requirements.txt
pip install -r requirements-whisper.txt      # optional, for audio scanning
cp config.example.yaml config.yaml
HUSH_PASSWORD=secret python -m hush --config config.yaml
```

Sources can be added in `config.yaml` or from the app with **Add a source**.

## Using it

1. Open a title and press **Language**, then **Scan this title**. Scans also run from the library's **Scan** buttons and keep going if you close the browser.
   To scan a whole library, open a folder and press **Scan all**. It queues every unscanned title in that folder and the folders inside it. To keep a library scanned automatically, open **Tasks** and turn on **Library refresh**: pick the sources and how often, and it records new and removed titles and queues scans for new ones. Tasks shows what ran, when, and what it found, with **Run now** for each. (`analysis.auto_scan` in `config.yaml` can pre-select the sources.) **Clean up** removes leftover scan files and old scan records. **Notifications** on the same page send a webhook message (ntfy, Gotify, Home Assistant…) when a batch of scans finishes or a task fails. Scans you start yourself run before bulk ones, and **Scan next** in the Scans dialog moves any waiting title to the front.
2. Lilac notches on the timeline show every muted moment. Hover a notch to see which word (masked) is muted.
3. In the Language panel you can:
   - switch whole categories on or off (strong profanity, mild language, sexual terms, slurs, taking the Lord's name in vain),
   - let a single moment play,
   - fine-tune a moment's start and end,
   - press **M** twice to mark a moment Hush missed.

   Your edits are kept when you scan again.
4. Subtitles shown in Hush are censored to match the audio.
5. **Filter on/off** (or the **H** key) toggles everything instantly.

Previous and next, **Shuffle** and **Repeat** (off, all, one) are in the control bar, and **Autoplay** (start a title when it opens and move on to the next) is in the settings next to it. Shortcuts: N next · P previous · S shuffle · R repeat · Space/K play/pause · J/L or ←/→ skip 10 s · F full screen · M mark · H filter on/off · Esc close panel.

### Other players and TVs

**Watch on another player** gives a 12-hour signed link. Open it in VLC, Kodi or a smart-TV player. The server mutes the audio in that stream and copies the video untouched.

**Kodi EDL** downloads a `.edl` file. Save it next to the video with the same name and Kodi mutes those moments itself, with normal seeking.

**Save filter file** exports the filter as JSON so you can share it with family or friends. **Load a filter file** imports one.

## How accurate is it?

| Engine | Timing | Best for |
|---|---|---|
| Whisper (`small.en`, default) | word-level, about ±0.1 s | everything; works without subtitles |
| Whisper (`medium.en` / `large-v3`) | best | loud action films and accents, but slower |
| Subtitles | estimated within each line | quick scans when subtitles exist |

Tips:

- **Model size.** On CPU, `small.en` scans a 2-hour movie in roughly 15–30 minutes depending on the machine. With an NVIDIA GPU (`whisper_device: cuda`) it takes a few minutes, and `medium.en` becomes practical.
- **Subtitles are fallible.** Subtitle tracks are often cleaned up or paraphrased compared with what's actually said, so Whisper catches more. In `auto` mode Hush uses Whisper and falls back to subtitles if Whisper can't run.
- **Padding.** Increase `pad_before` and `pad_after` if you hear the edges of words.
- **Custom word list.** Copy `hush/analysis/wordlists/default.yaml`, edit it, and set `analysis.wordlist`. Restart Hush, then press **Reapply word list** in the Language panel. It re-matches the saved transcript instantly; no new transcription is needed.

## Security notes

- **Set a password.** Change it any time from **Password** in the top bar; it is stored hashed (scrypt) in `data/hush.db`, overrides `HUSH_PASSWORD`, and signs other browsers out. If you forget it, delete the saved one with `sqlite3 data/hush.db "delete from settings where key='password_hash'"` and restart; `HUSH_PASSWORD` applies again. Sessions are HMAC-signed, HTTP-only, `SameSite=Strict` cookies, and logins are rate-limited.
- **TLS.** Put Hush behind your reverse proxy (Caddy, Traefik, nginx) for HTTPS, and set `public_url` so links for other players use it.
- **Secrets.** Keep secrets in environment variables (`${NAS_PASSWORD}` syntax in `config.yaml`). Credentials for sources added in the app are stored in `data/hush.db`, so protect the data volume.
- **Path safety.** Paths are confined to their source root, which blocks path traversal.
- **Web sources.** Web sources block link-local and metadata addresses. Use `allowed_hosts` to pin a web source to specific hosts.
- **FFmpeg access.** FFmpeg reads SMB files through a loopback endpoint that requires a per-process random token.
- **Browser hardening.** The UI sends a strict CSP, has no third-party requests, and bundles its fonts (SIL OFL), so it works fully offline on a LAN.

## Profiles

Everyone in the house can have a profile: a name, a colour and a picture (pick from 16 built-in drawings such as a cat, panda or robot, or keep the first letter), with no password. Hush asks **Who's watching?** when you open it, remembers the choice in that browser, and the name in the top bar switches profile. Each profile keeps its own place in movies and shows (**Continue watching**), favorite and recently watched channels, and filter choices. Your existing history became the first profile, **Main**.

A **kids profile** only shows titles that are safe for children. A title appears only when it has been **scanned**, the scan found **no flagged language** (you can allow mild language instead), and it has a **rating** (from the `.nfo` file or TMDB) that is not above the limit you pick (G, PG or PG-13). A clean language scan says nothing about violence or explicit scenes, so titles with no known rating are hidden unless you tick *Also show titles with no known rating*. Titles that were never scanned are hidden too, so run **Scan all** on your library first. Live TV is off unless you allow it, because live channels cannot be checked. Kids also never see raw folders, Tasks, scans, settings or the phone-remote page, the filter stays on for every word category so anything that slips through is muted, and the server refuses those requests even if someone types the address. Set it up under **Profiles** in the sidebar (grown-up profiles only).

This is for family use, not security: with no password anyone can switch to another profile. If you set a Hush password, turn on **Ask for the Hush password to leave a kids profile** on the Profiles page so a child cannot switch back without it.

## Big screen mode (TV)

Press **Big screen** in the top bar to switch to a layout made for a TV and a remote: larger text, a top navigation bar, a high-contrast focus ring, and a **Home** page of shelves (Continue watching, recently watched and favorite channels, Movies, TV shows). A smart TV or Chromecast browser starts in this mode by itself. On a TV the app takes over the remote's arrow keys (including remotes that only report old numeric key codes) and hides the browser's slow mouse pointer while you use the remote; the pointer comes back for a few seconds if you move it.

Use the remote's arrow keys to move between items, **OK** to open, and **Back** to go up one level (it also closes panels, leaves the player, and goes to the parent folder). In the player, **OK** plays or pauses, **←/→** skip 10 seconds, **↓** reaches the control bar, and on Live TV **↑/↓** or **Channel +/−** change channel. Media keys (play/pause, stop, next, previous, rewind, fast-forward), the coloured buttons (red: filter, green: language panel, yellow: channels, blue: mini player), **Info** and **Guide** work too. Leaving a playing title with Back keeps it playing in a **mini player**: in the top-left above the sidebar normally, bottom-right in big screen mode. Turn that off in the player settings if you prefer it to stop.

## Phone remote

Open **Phone remote** on the screen (the TV or computer), switch it on and name it. On your phone open `http://<your server>/remote` (for example `http://hush.local/remote`) and use *Add to Home Screen* to keep it like an app. The remote shows what is playing and has play/pause, skip, volume, the filter switch, channel up/down with a number pad, arrow keys, and Continue / Movies / Shows / Live TV lists: tap one to play it on the screen. Several screens can be controlled by choosing one at the top. The remote needs the same password as Hush. Behind nginx or another proxy, WebSocket upgrades must be allowed for `/api/remote/ws`.

The remote is a small protocol (JSON over one WebSocket, described at the top of `hush/remote.py`), so a native app can use it later.

## Finding things: A–Z and 0–9

Movies, TV shows, Live TV and long folders have a row of **A–Z** and **1–0** buttons at the top. Pick one to see only titles starting with it (pick it again, or **All**, to clear). Letters with nothing under them are dimmed, and the counts follow your other filters, such as the Live TV group. "The", "A" and "An" are ignored for movies and shows, so *The Matrix* files under M. The … button holds titles in other alphabets.

## Resume

Hush remembers where you stopped in every movie, episode and song, on the server, so it works from any device. Opening a title picks up at that spot (with a **Start over** button for a few seconds), the folder lists show **Resume 1:03** or **✓ Watched**, and **Movies** and **TV shows** open with a **Continue watching** row. A title counts as watched at 92% (or in the last 90 seconds of a long one); mark it by hand on its page. Live channels are not tracked.

## Live TV

Open **Live TV** in the left bar. Add an IPTV playlist (an `.m3u` or `.m3u8` list of channels, for example from iptv-org) under **Playlists**, or import the ones already saved as sources. Hush reads it once and keeps the channels in its database: logos (fetched and cached by the server, so the page makes no third-party requests), groups, search, and favorites. Playlists refresh daily from **Tasks → Live TV channels**. Channels that fail to play twice in a row are hidden (there is a switch to show them), because public lists are full of dead and geo-blocked streams. Live channels play unfiltered: they have no fixed length to scan.

Live TV works like a TV: channels are numbered in the list you are looking at, a banner with the logo, number and group shows when you change channel, and **↑ / ↓** (or Page Up/Down) change channel. Type a number (for example **1 2**) to jump to it, **B** returns to the last channel, **G** (or the Channels button) opens the channel list, and **I** shows the banner again. A **Recently watched** row sits at the top of Live TV, and **Back to Live TV** returns to the same group, letter and search you left.

## Safari and iPhone

Safari and every iOS browser cannot play the live MP4 stream Hush uses for MKV, HEVC and live channels, so for them Hush switches to **HLS** automatically. The filter's muting is then done on the server (Safari's audio API does not work with HLS), so changing categories or edits restarts the stream at the same spot. Other browsers are unchanged.

## Library, details and tidy names

Open **Movies** or **TV shows** in the left bar for a poster library. Each title has a page with its summary, genres, runtime and rating, plus **Play**, **Scan this title**, **Fix match** and downloads.

- **Where the details come from.** In order: the `.nfo` file next to the video (Kodi/Jellyfin/Plex format), then an online lookup, then the file name. The online lookup uses **TMDB** if you add a free key under **Tasks → Movie and show details**, and the free **Wikipedia** (movies) and **TVmaze** (shows and episodes) services otherwise. Posters come from a `poster.jpg` next to the video, the online source, or a frame from the video itself.
- **Fix match.** If a title is matched wrongly, press **Fix match**, search, and pick the right one. Your choice is locked and never overwritten.
- **Transcript.** After a title is scanned, download its transcript as text, SRT or WebVTT, optionally with filtered words masked (`f***`). Subtitle and caption tracks inside the file or next to it can be downloaded as SRT or WebVTT too.
- **Tidy file names.** **Tasks → Tidy file names** previews renames such as `72.Hours.2026.1080p.WEBRip.x265-NeoNoir.mkv` → `72 Hours (2026).mkv` and `Collision 2026 S01E01 Business Protocol 1080p….mkv` → `Collision (2026) - S01E01 - Business Protocol.mkv`. By default every file goes straight into the source folder, with its subtitles and `.nfo` renamed to match; or choose one folder per title. Emptied folders are removed, leftovers stay. Nothing changes until you press Rename, nothing is overwritten, and the last rename can be undone. Filters, scans and posters follow the renamed files. This needs Hush to have write access to the folder.

## Legal

Hush filters at playback time: it skips or mutes audio while you watch a copy you're entitled to play, and never writes an edited copy of the work. In the US, this kind of private, in-home filtering is the use contemplated by the Family Movie Act of 2005. The "another player" stream is produced on the fly for your own viewing. Don't use it to redistribute content. Laws differ by country; this isn't legal advice.

## Project layout

```
hush/
  app.py              HTTP API and routes
  media.py            ffprobe, play-mode choice, keyframe seeking
  stream.py           range serving, HTTP proxy, live FFmpeg streams, server-side mute
  auth.py             login sessions, signed links
  sources/            local, smb, http, dlna, jellyfin + plex
  analysis/           jobs, Whisper, subtitles, word matcher, default word list
  web/                single-page app (no build step)
tests/                pytest suite (generates real media with FFmpeg)
```

Run the tests with `pip install pytest && pytest`.

## Roadmap ideas

- Vocal isolation (Demucs) before transcription, for dialogue buried under music
- Scene skipping for nudity and violence using a frame classifier, with the same filter file format
- Per-viewer profiles (kids get stricter categories)
- HLS output so TVs can seek in filtered streams


## Posters, guide and channel extras

- **Artwork without a key.** Posters, summaries and episode stills come from Cinemeta (IMDb data), Wikipedia and TVmaze. A TMDB key (Settings in the library page) still gives the best matches. Titles without artwork are retried automatically.
- **Programme guide.** Live TV shows "Now / Next" on channel cards and in the channel banner. Add guides under Live TV → Playlists → Programme guide (free ones are suggested: EPGShare01, epg.pw, Pluto TV, Samsung TV Plus, Roku), or a playlist can advertise its own (`url-tvg`). Guide channels are matched to yours by tvg-id, by an id inside the stream address, or by name, so a guide that fits your playlist works best (a Pluto playlist with the Pluto guide matches almost completely). It refreshes with the Live TV task.
- **Upcoming episodes.** The "Upcoming episodes" task asks TVmaze about every show in the library; Home gets a "Coming up" row and each show page lists its next episodes.
- **Channel previews.** Rest on a channel card for a moment to see a still from the live stream.
- **Backup sources.** If a channel stops answering, Hush tries another working channel with the same name.
- **Fast zapping.** Channels are scanned briefly, neighbouring channels are prepared in advance, and probe results are remembered across restarts.
- **Updating.** `./update.sh` on the server pulls the latest code from GitHub and restarts Hush.
- **My List.** Each profile has its own list of shows and movies, with a status (Watching, Plan to watch, Completed, Dropped). Shows you start watching join it automatically. Use the My List menu on any show or movie, or search under My List to follow a show that is not in your library yet (adults only). Each card shows the next episode to play and when the next new one airs, and Home gets an "Up next on My List" row.
- **Downloads (qBittorrent).** Under Downloads, connect Hush to the qBittorrent you already run (its Web UI address, user name and password). Hush shows its downloads with progress, lets you pause, resume or remove them from the list, and lists the RSS feeds and download rules qBittorrent follows. Hush does not choose or search for anything: qBittorrent and your own rules decide what is downloaded and where it is saved. Every item of a feed qBittorrent follows has an Add button that sends it to qBittorrent (items it already has are marked), and there is a box to paste a magnet link or .torrent address. A "Save to" menu chooses where new downloads go: qBittorrent's own choice, one of its categories (each with its own folder), or a folder you type (a path on the qBittorrent machine). Each download can be moved to another category or folder afterwards. When a download finishes, Hush sends a notification (if set up) and refreshes the library about 30 seconds later, so new files appear in Movies and TV shows. The qBittorrent password is stored in Hush's database, so use an account that only has Web UI access.
- **Pictures already in your folders.** Hush uses artwork it finds next to your files, and it wins over downloaded artwork: for movies `poster.jpg`, `folder.jpg`, `cover.jpg` or `<name>-poster.jpg`, and `fanart.jpg`, `backdrop.jpg` or `<name>-fanart.jpg` for the background; for shows `poster.jpg` or `folder.jpg` and `fanart.jpg` in the show folder (Season folders are fine); for episodes `<name>-thumb.jpg` or `<name>.jpg`. Backgrounds fade in behind the top of a movie or show page. They are picked up on every library refresh, and again whenever you replace the file. Details still come from the NFO files next to the video (`<name>.nfo`, `movie.nfo`, `tvshow.nfo`).
- **Online backgrounds.** Titles and shows without a background picture of their own get one from their IMDb id, through the keyless metahub image service (the id comes from the NFO, from the provider that matched the title, or from a Cinemeta lookup by name; TVmaze backgrounds fill in for shows with no IMDb picture). Titles with no picture online are retried after a week. Switching online details off in the library settings turns this off too.

## TV and tablet apps

An Android app (Android TV / Google TV such as TCL, Fire TV, Android tablets) and an LG webOS app are in `android/` and `webos/`. They load Hush from your server (each device asks for the server address once) and the Android app updates itself from GitHub releases. See `android/README.md`.

## Old TVs (LG webOS 5 and older)

Older TV browsers cannot read modern JavaScript, so Hush also ships `hush/web/app.legacy.js`, a translated copy of `app.js`. The page starts the normal script and falls back to the copy on its own when the browser cannot read it (`boot.js`). **After changing `app.js`, run `scripts/build-legacy.sh`** (needs Node); a test fails when the copy is out of date.

## Language filter for live TV (captions)

A live channel plays about **10 seconds behind the broadcast** when the filter is on (it is always on for kids profiles). Hush pulls the channel, reads its closed captions (CEA-608/708, carried inside many broadcast streams), matches them against the word list and silences the flagged words before they reach the screen. Only the audio of segments that need it is re-encoded; the video is copied. Captions only say roughly when a word was spoken (live captions run 1-2 seconds late), so the silence is a short window around the word rather than a precise bleep.

- **Channels without captions** are listened to instead: Hush recognises the speech with a small Whisper model (`live_whisper_model`, default `small.en`) on the server's processor, in short overlapping windows, and silences flagged words with tight windows. In a sample of 26 channels only about 1 in 8 carried captions, so most channels use this. Each channel being recognised uses roughly half of 6-8 processor threads; at most `live_asr_sessions` (default 2) channels are recognised at once, and a GPU would raise that a lot. An adult profile on a channel that cannot be checked hears it unfiltered (and is told); a kids profile is refused rather than ever hearing unchecked audio.
- **Starting a channel takes about 15-20 seconds** with the filter on, because of the delay. Turn the filter off (adults) to flip through channels quickly; flipping back to a recent channel is quick.
- Kids profiles can no longer open a live channel unfiltered at all.

## The tuning-in screen

While a channel or title opens, the player shows a Hush-themed screen instead of black: the time, the date, the weather and a count-up with a progress bar (and "Starting the language filter" while a filtered channel starts). Set your town under Settings → Tuning-in screen; the weather comes from Open-Meteo (free, no key). Titles that open in under a second never show it.

## Text entry and the little player on a TV

- **Keyboard for the remote.** In big screen mode, press OK on a text box and Hush opens its own keyboard: the arrow keys move over the keys, OK types, Back closes it. It has shift, numbers and symbols, a cursor, Clear, `.com`, `https://`, Done and Go (submit). A real keyboard types straight in. The TV's own on-screen keyboard is kept from popping up because it ignores the page's arrow keys.
- **Full screen button.** While the little player is playing, a "Full screen: <title>" button appears in the big screen menu (and in the top bar on other screens) to bring it back to full screen.

- **Exit Hush.** In the Android and LG apps the big screen menu has an "Exit Hush" button (the Android app also has it under the Menu key). Android apps older than 1.0.1 cannot quit themselves and say so.
- **OK on a text box.** While a text box has the highlight on a TV it is made read-only: Android's browser otherwise keeps the OK key for its own invisible keyboard and the page never hears it. Typing goes through Hush's keyboard.

- **Little player / full screen key.** While something is playing, the remote's **blue** key (LG and TVs with colour keys), the **Window** key, or `W` on a keyboard switches between the little player and full screen. The Android app's Menu key (the one on a Fire TV remote) lists "Little player / full screen" first. On a TV the little player always shows its controls, and its first button is a gold "Full screen" button.

- **Typing from the phone.** On the phone remote, a Keyboard box types straight into the screen: highlight a text box on the TV (or press OK on it, which opens Hush's keyboard) and the phone shows its name and current text. Type on the phone and it appears on the screen as you go; Go submits the form (search, sign-in...), Clear empties it. When the TV opens its keyboard, the phone's keyboard comes up by itself. The remote's "Mini / full screen" button switches between the little player and full screen.

## Channel numbers

Every Live TV channel has a **permanent number**, like a real lineup. Existing channels were numbered A-Z once; a channel added later gets the next free number; and numbers never change when a playlist is read again, or when a channel disappears and comes back. Cards, the channel banner, the channel list and the phone remote all show it, Live TV lists run in number order, and typing a number on the remote (up to 5 digits) tunes straight to that channel and carries on from there with channel up and down. Give the channel you are watching a number of your own with the **Number** button in the player (a number someone else has can be swapped), or start over with **Renumber A-Z** / **Renumber by group** in Live TV -> Playlists.

## Captions button

Every player has a **CC** button (or press **C**, or use *Captions* on the phone remote). On a **live channel** Hush treats every channel as captioned: it shows the broadcast's own captions when the stream carries them and otherwise listens to the channel and writes the lines itself, about 10 seconds behind live (the same delay the language filter uses). With the filter off, captions are shown but nothing is muted. On **movies and shows** CC turns on the English subtitle track, or the words from the scan when there is no track. Your choice is remembered per profile. **Shuffle** and **Repeat** only appear while music is playing.

On Live TV the channel number is typed into the box in the **Channels** pop-out, and the Language button is hidden.

In the player settings, **Sound sync** adds delay to the sound (− / + in 50 ms steps, or the , and . keys) when it plays before the picture. It is remembered, and is not available on LG and Apple players. The Android app shows its version at the top of the page.
