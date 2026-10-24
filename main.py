from youtube.downloader import download_video


def main():

    # Examples:
    #
    # VIDEO_URL = "https://www.youtube.com/watch?v=R4MInIP2c-A"
    # VIDEO_URL = "https://www.youtube.com/shorts/f3YgyJp0Aqw"

    VIDEO_URL = "https://youtu.be/24hfDD3gAAU"

    # "video" or "audio"
    MODE = "video"

    # Only for video mode:
    # "highest", "1080p", "720p", etc.
    RESOLUTION = "360p"

    # Video output is retried at lower bitrates until it is below this size.
    MAX_FILE_SIZE_MB = 5

    DOWNLOAD_DIR = "downloads"

    # Video-specific settings.
    REENCODE_VIDEO = True
    FAST_ENCODE = False

    # None = all CPU cores
    THREADS = None

    # -------------------------------------------------
    # AUDIO / VIDEO TRIMMING INSTRUCTIONS
    # -------------------------------------------------
    #
    # None:
    #
    # START_END = None
    #
    # Or:
    #
    # START_END = (42.6, 55.9)
    #
    # This means:
    # start at 42.6 seconds
    # stop at 55.9 seconds
    #
    # Audio trimming works regardless of REENCODE_VIDEO.
    #
    # Video trimming currently requires:
    # REENCODE_VIDEO = True
    #
    START_END = (17.5, 99)

    if MODE == "audio":

        download_video(
            video_url=VIDEO_URL,
            mode="audio",
            download_dir=DOWNLOAD_DIR,
            max_file_size_mb=MAX_FILE_SIZE_MB,
            start_end=START_END
        )

    else:

        download_video(
            video_url=VIDEO_URL,
            mode="video",
            resolution=RESOLUTION,
            download_dir=DOWNLOAD_DIR,
            reencode=REENCODE_VIDEO,
            fast_encode=FAST_ENCODE,
            threads=THREADS,
            start_end=START_END,
            max_file_size_mb=MAX_FILE_SIZE_MB
        )


if __name__ == "__main__":
    main()
