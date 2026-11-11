# Media Downloader

Before running the downloader, create `download_options.json` next to `main.py`
using [`download_options.example.json`](./download_options.example.json) as a
template. The options are:

- `url`: YouTube video URL to download.
- `mode`: `"audio"` to save an MP3, or `"video"` to save an MP4.
- `final_download_dir`: Directory for completed files. On Mac, use
  `"~/Downloads"` for your regular Downloads folder. `~` is expanded for the
  current user; change this value to choose another destination.
- `intermediate_dir`: Parent directory for temporary working files. The
  default `"python-temp"` uses Python's system temporary location. You can set
  this to a path on a drive with enough free space for large videos. Each run
  gets its own temporary subdirectory, which is removed when processing ends.
- `resolution`: Starting video resolution, such as `"360p"`, or `"highest"`.
  Used only in video mode.
- `minimum_resolution`: Lowest resolution to try if the file-size limit is not
  met. The downloader keeps the original downloaded stream and locally
  downscales through standard steps (`2160p`/4K, `1440p`, `1080p`, `720p`,
  `480p`, `360p`, `240p`, `144p`).
- `max_file_size_mb`: Maximum output size in decimal megabytes, or
  `null` for no size limit. In video mode, video bitrate is reduced first, then
  audio bitrate, before trying a lower resolution. In audio mode, MP3 bitrate
  is reduced from 192 kbps. Both modes stop at `minimum_audio_bitrate`; video
  mode also stops at `minimum_bitrate`.
- `minimum_bitrate`: Minimum video bitrate in kbps for video mode.
- `minimum_audio_bitrate`: Minimum audio bitrate in kbps, used for the audio
  track in video mode and for MP3 output in audio mode.
- `reencode_video`: Re-encode the video instead of copying its streams. Video
  trimming requires this to be `true`; it must also be `true` to use
  `max_file_size_mb`.
- `fast_encode`: Use FFmpeg's faster, lower-compression encoding preset. Used
  only when re-encoding video.
- `threads`: Number of CPU threads for video re-encoding, or `null` to use all
  available cores.
- `start_end`: Optional `[start, end]` trim points in seconds. Use `null` to
  download the full clip. Trimming works in both modes.

Only completed files are kept in `final_download_dir`; downloaded sources and
other intermediate files are cleaned up with the temporary working directory.

Then run:

```sh
uv run python main.py
```
