import json
from pathlib import Path

from youtube.downloader import download_video


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

    DOWNLOAD_DIR = "downloads"
    # TODO: Resolve the platform-specific Downloads folder on Windows and Linux.
    final_download_dir = Path(
        options.get("final_download_dir", "~/Downloads")
    ).expanduser()

    if mode == "audio":
        download_video(
            video_url=options["url"],
            mode="audio",
            download_dir=DOWNLOAD_DIR,
            final_download_dir=str(final_download_dir),
            max_file_size_mb=options["max_file_size_mb"],
            start_end=start_end,
        )
    else:
        download_video(
            video_url=options["url"],
            mode="video",
            resolution=options["resolution"],
            download_dir=DOWNLOAD_DIR,
            final_download_dir=str(final_download_dir),
            reencode=options["reencode_video"],
            fast_encode=options["fast_encode"],
            threads=options["threads"],
            start_end=start_end,
            max_file_size_mb=options["max_file_size_mb"],
        )


if __name__ == "__main__":
    main()
