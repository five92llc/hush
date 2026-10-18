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
- **Transcode**: a full H.264 encode, for HEVC, MPEG-2, DivX and similar. Set `video_encoder: h264_nvenc` (or `qsv`/`vaapi`) for GPU encoding.

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
