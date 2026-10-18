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
| Jellyfin / Emby | API key, plays the original file |
| Plex | Token, plays the original file |

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
2. Lilac notches on the timeline show every muted moment. Hover a notch to see which word (masked) is muted.
3. In the Language panel you can:
   - switch whole categories on or off (strong profanity, mild language, sexual terms, slurs, taking the Lord's name in vain),
   - let a single moment play,
   - fine-tune a moment's start and end,
   - press **M** twice to mark a moment Hush missed.

   Your edits are kept when you scan again.
4. Subtitles shown in Hush are censored to match the audio.
5. **Filter on/off** (or the **H** key) toggles everything instantly.

Shortcuts: Space/K play/pause · J/L or ←/→ skip 10 s · F full screen · M mark · H filter on/off · Esc close panel.

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

- **Set a password.** Sessions are HMAC-signed, HTTP-only, `SameSite=Strict` cookies, and logins are rate-limited.
- **TLS.** Put Hush behind your reverse proxy (Caddy, Traefik, nginx) for HTTPS, and set `public_url` so links for other players use it.
- **Secrets.** Keep secrets in environment variables (`${NAS_PASSWORD}` syntax in `config.yaml`). Credentials for sources added in the app are stored in `data/hush.db`, so protect the data volume.
- **Path safety.** Paths are confined to their source root, which blocks path traversal.
- **Web sources.** Web sources block link-local and metadata addresses. Use `allowed_hosts` to pin a web source to specific hosts.
- **FFmpeg access.** FFmpeg reads SMB files through a loopback endpoint that requires a per-process random token.
- **Browser hardening.** The UI sends a strict CSP, has no third-party requests, and bundles its fonts (SIL OFL), so it works fully offline on a LAN.

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
