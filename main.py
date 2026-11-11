import json
import logging
import tempfile
from pathlib import Path

from media_processing.ffmpeg import FileSizeLimitError
from youtube.downloader import download_video


logger = logging.getLogger(__name__)


def main():
    config_path = Path(__file__).with_name("download_options.json")
    with config_path.open(encoding="utf-8") as config_file:
        options = json.load(config_file)

    mode = options["mode"]
    if mode not in ("audio", "video"):
        raise ValueError(f"Unsupported download mode: {mode!r}")

    start_end = options["start_end"]
    if start_end is not None:
        start_end = tuple(start_end)

    # TODO: Resolve the platform-specific Downloads folder on Windows and Linux.
    final_download_dir = Path(
        options.get("final_download_dir", "~/Downloads")
    ).expanduser()

    intermediate_dir = options.get("intermediate_dir", "python-temp")
    if intermediate_dir == "python-temp":
        intermediate_parent = None
    else:
        intermediate_parent = Path(intermediate_dir).expanduser()
        intermediate_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix="media-downloader-",
        dir=intermediate_parent,
    ) as work_dir:
        if mode == "audio":
            download_video(
                video_url=options["url"],
                mode="audio",
                download_dir=work_dir,
                final_download_dir=str(final_download_dir),
                max_file_size_mb=options["max_file_size_mb"],
                minimum_audio_bitrate_kbps=options["minimum_audio_bitrate"],
                start_end=start_end,
            )
        else:
            download_video(
                video_url=options["url"],
                mode="video",
                resolution=options["resolution"],
                minimum_resolution=options["minimum_resolution"],
                download_dir=work_dir,
                final_download_dir=str(final_download_dir),
                reencode=options["reencode_video"],
                fast_encode=options["fast_encode"],
                threads=options["threads"],
                start_end=start_end,
                max_file_size_mb=options["max_file_size_mb"],
                minimum_video_bitrate_kbps=options["minimum_bitrate"],
                minimum_audio_bitrate_kbps=options["minimum_audio_bitrate"],
            )


if __name__ == "__main__":
    try:
        main()
    except FileSizeLimitError as error:
        logger.error("Download stopped: %s", error)
