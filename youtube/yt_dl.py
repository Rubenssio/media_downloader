import os
import re
import logging
import subprocess
import time
import multiprocessing
from pytubefix import YouTube
from datetime import timedelta
from yt_dlp import YoutubeDL


# TODO: Make video downloading also based on yt-dlp, with fallback between yt-dlp and pytubefix
# TODO: Add optional dependency update mechanism for yt-dlp and pytubefix


# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize filename to remove illegal characters."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def format_duration(seconds: int) -> str:
    """Convert seconds into readable duration format."""
    return str(timedelta(seconds=seconds))


def ensure_unique_filename(
    directory: str,
    base_name: str,
    ext: str = ".mp4"
) -> str:
    """Append (1), (2), etc. if the filename already exists."""

    i = 1
    final_name = f"{base_name}{ext}"

    while os.path.exists(os.path.join(directory, final_name)):
        final_name = f"{base_name} ({i}){ext}"
        i += 1

    return final_name


def merge_video_audio(
    video_path: str,
    audio_path: str,
    output_path: str,
    duration_sec: int,
    reencode: bool = True,
    fast_encode: bool = False,
    threads: int = None,
    start_end: tuple = None
):
    """
    Merge video and audio with optional re-encoding,
    thread control, trimming, and progress display.
    """

    total_cores = multiprocessing.cpu_count()
    used_threads = threads if threads else total_cores

    if reencode:
        command = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-threads", str(used_threads)
        ]

        if fast_encode:
            command += [
                "-preset", "ultrafast"
            ]

        if start_end:
            start, end = start_end

            if end <= start:
                raise ValueError(
                    f"Invalid START_END: end ({end}) "
                    f"must be greater than start ({start})"
                )

            command += [
                "-ss", str(start),
                "-t", str(end - start)
            ]

            duration_sec = end - start

    else:
        command = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c", "copy"
        ]

    command.append(output_path)

    print("[INFO] Merging video and audio...")
    print(f"[INFO] Using {used_threads}/{total_cores} CPU cores")

    process = subprocess.Popen(
        command,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    time_pattern = re.compile(
        r"time=(\d+):(\d+):(\d+)\.(\d+)"
    )

    start_time = time.time()
    last_percent = -1

    for line in process.stderr:
        match = time_pattern.search(line)

        if match:
            h, m, s, ms = map(int, match.groups())

            current_sec = (
                h * 3600
                + m * 60
                + s
                + ms / 100.0
            )

            percent = min(
                (current_sec / duration_sec) * 100,
                100
            )

            if int(percent) != last_percent:
                last_percent = int(percent)

                elapsed = time.time() - start_time

                if percent > 0:
                    remaining = (
                        elapsed / percent
                    ) * (100 - percent)

                    eta = time.time() + remaining

                    eta_str = time.strftime(
                        "%H:%M:%S",
                        time.localtime(eta)
                    )
                else:
                    eta_str = "Calculating..."

                elapsed_str = str(
                    timedelta(seconds=int(elapsed))
                )

                print(
                    f"\r[PROGRESS] "
                    f"{percent:.2f}% | "
                    f"Elapsed: {elapsed_str} | "
                    f"ETA: {eta_str}",
                    end=''
                )

    process.wait()

    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            command
        )

    elapsed = time.time() - start_time

    elapsed_str = str(
        timedelta(seconds=int(elapsed))
    )

    print(
        f"\r[PROGRESS] "
        f"100.00% | "
        f"Elapsed: {elapsed_str} | "
        f"ETA: done      "
    )

    print("\n[INFO] Merging complete.")


def download_audio_with_ytdlp(
    video_url: str,
    download_dir: str,
    start_end: tuple = None,
    bitrate: str = "192k"
):
    """
    Download the best available audio using yt-dlp,
    then ALWAYS re-encode it into a compatibility-focused MP3.

    Output:
        MP3
        192 kbps
        44.1 kHz
        Stereo
        ID3v2.3
    """

    os.makedirs(
        download_dir,
        exist_ok=True
    )

    ydl_opts = {
        "format": "bestaudio/best",

        # Download original audio first.
        # Conversion is handled manually with ffmpeg afterward.
        "outtmpl": os.path.join(
            download_dir,
            "%(title)s.%(ext)s"
        ),

        "quiet": False,
        "no_warnings": False,
    }

    downloaded_path = None

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                video_url,
                download=True
            )

            downloaded_path = ydl.prepare_filename(
                info
            )

            title = info.get(
                "title",
                "audio"
            )

            channel = info.get(
                "uploader",
                "Unknown"
            )

            duration = info.get(
                "duration",
                0
            )

        logger.info(
            f"Title   : {title}"
        )

        logger.info(
            f"Channel : {channel}"
        )

        logger.info(
            f"Duration: {format_duration(duration)}"
        )

        safe_title = sanitize_filename(
            title
        )

        final_filename = ensure_unique_filename(
            download_dir,
            safe_title,
            ext=".mp3"
        )

        final_audio_path = os.path.join(
            download_dir,
            final_filename
        )

        logger.info(
            "Converting downloaded audio "
            "to USB-compatible MP3..."
        )

        command = [
            "ffmpeg",
            "-y",
            "-i", downloaded_path
        ]

        # Optional trimming.
        #
        # Example:
        # START_END = (42.6, 55.9)
        #
        # Means:
        # start at 42.6 seconds
        # stop at 55.9 seconds
        if start_end:
            start, end = start_end

            if start < 0:
                raise ValueError(
                    "START_END start cannot be negative."
                )

            if end <= start:
                raise ValueError(
                    f"Invalid START_END: "
                    f"end ({end}) must be greater "
                    f"than start ({start})"
                )

            logger.info(
                f"Trimming audio: "
                f"{start:.2f}s -> {end:.2f}s "
                f"({end - start:.2f}s)"
            )

            command += [
                "-ss", str(start),
                "-t", str(end - start)
            ]

        command += [
            "-vn",

            # Explicit MP3 encoding.
            # This re-encodes the audio even if
            # the downloaded source is already MP3.
            "-c:a", "libmp3lame",

            # Constant bitrate.
            "-b:a", bitrate,

            # Very common audio sample rate.
            "-ar", "44100",

            # Stereo.
            "-ac", "2",

            # Better compatibility with older
            # MP3 players / USB speakers.
            "-id3v2_version", "3",

            final_audio_path
        ]

        subprocess.run(
            command,
            check=True
        )

        # Delete the original downloaded source.
        if (
            downloaded_path
            and os.path.exists(downloaded_path)
            and os.path.abspath(downloaded_path)
            != os.path.abspath(final_audio_path)
        ):
            os.remove(downloaded_path)

        logger.info(
            f"Audio saved to: "
            f"{final_audio_path}"
        )

        return final_audio_path

    except Exception:
        logger.exception(
            "Audio download/conversion failed"
        )

        return None


def download_video(
    video_url: str,
    resolution: str = "highest",
    download_dir: str = "downloads",
    mode: str = "video",
    max_file_size_mb: int = None,
    reencode: bool = True,
    fast_encode: bool = False,
    threads: int = None,
    start_end: tuple = None
):
    """
    Download a YouTube video or audio.

    Audio mode:
        Uses yt-dlp and ALWAYS re-encodes to MP3.

    Video mode:
        Currently uses pytubefix.
    """

    if mode == "audio":
        download_audio_with_ytdlp(
            video_url=video_url,
            download_dir=download_dir,
            start_end=start_end,
            bitrate="192k"
        )

        return

    # -----------------------------------------
    # VIDEO MODE
    # -----------------------------------------

    try:
        yt = YouTube(
            video_url,
            "WEB"
        )

        title = yt.title
        duration = yt.length
        channel = yt.author

    except Exception:
        logger.exception(
            "Failed to initialize YouTube video"
        )

        return

    logger.info(
        f"Title   : {title}"
    )

    logger.info(
        f"Channel : {channel}"
    )

    logger.info(
        f"Duration: {format_duration(duration)}"
    )

    safe_title = sanitize_filename(
        title
    )

    os.makedirs(
        download_dir,
        exist_ok=True
    )

    final_filename = ensure_unique_filename(
        download_dir,
        safe_title
    )

    if resolution == "highest":

        video_stream = (
            yt.streams
            .filter(
                adaptive=True,
                only_video=True
            )
            .order_by("resolution")
            .desc()
            .first()
        )

        audio_stream = (
            yt.streams
            .filter(
                adaptive=True,
                only_audio=True
            )
            .order_by("abr")
            .desc()
            .first()
        )

        if not video_stream or not audio_stream:
            logger.error(
                "Could not find suitable adaptive streams."
            )

            return

        video_path = os.path.join(
            download_dir,
            "temp_video.mp4"
        )

        audio_path = os.path.join(
            download_dir,
            "temp_audio.mp4"
        )

        output_path = os.path.join(
            download_dir,
            final_filename
        )

        logger.info(
            f"Downloading video: "
            f"{video_stream.resolution}"
        )

        video_stream.download(
            output_path=download_dir,
            filename="temp_video.mp4"
        )

        logger.info(
            f"Downloading audio: "
            f"{audio_stream.abr}"
        )

        audio_stream.download(
            output_path=download_dir,
            filename="temp_audio.mp4"
        )

        logger.info(
            "Merging video and audio with ffmpeg..."
        )

        merge_video_audio(
            video_path,
            audio_path,
            output_path,
            yt.length,
            reencode=reencode,
            fast_encode=fast_encode,
            threads=threads,
            start_end=start_end
        )

        if os.path.exists(video_path):
            os.remove(video_path)

        if os.path.exists(audio_path):
            os.remove(audio_path)

    else:

        video_stream = (
            yt.streams
            .filter(
                adaptive=True,
                only_video=True,
                file_extension="mp4",
                res=resolution
            )
            .first()
        )

        audio_stream = (
            yt.streams
            .filter(
                adaptive=True,
                only_audio=True,
                file_extension="mp4"
            )
            .order_by("abr")
            .desc()
            .first()
        )

        if video_stream and audio_stream:

            logger.info(
                f"Found adaptive video stream "
                f"at {resolution}"
            )

            video_path = os.path.join(
                download_dir,
                "temp_video.mp4"
            )

            audio_path = os.path.join(
                download_dir,
                "temp_audio.mp4"
            )

            output_path = os.path.join(
                download_dir,
                final_filename
            )

            logger.info(
                f"Downloading video: "
                f"{video_stream.resolution}"
            )

            video_stream.download(
                output_path=download_dir,
                filename="temp_video.mp4"
            )

            logger.info(
                f"Downloading audio: "
                f"{audio_stream.abr}"
            )

            audio_stream.download(
                output_path=download_dir,
                filename="temp_audio.mp4"
            )

            logger.info(
                "Merging video and audio "
                "with ffmpeg..."
            )

            merge_video_audio(
                video_path,
                audio_path,
                output_path,
                yt.length,
                reencode=reencode,
                fast_encode=fast_encode,
                threads=threads,
                start_end=start_end
            )

            if os.path.exists(video_path):
                os.remove(video_path)

            if os.path.exists(audio_path):
                os.remove(audio_path)

        else:

            logger.warning(
                f"No adaptive stream found "
                f"for {resolution}, "
                f"trying progressive..."
            )

            stream = (
                yt.streams
                .filter(
                    progressive=True,
                    file_extension="mp4",
                    res=resolution
                )
                .first()
            )

            if not stream:
                logger.warning(
                    f"No progressive stream found "
                    f"for {resolution}, "
                    f"falling back to highest"
                )

                stream = (
                    yt.streams
                    .get_highest_resolution()
                )

            output_path = os.path.join(
                download_dir,
                final_filename
            )

            logger.info(
                f"Downloading progressive stream: "
                f"{stream.resolution}"
            )

            stream.download(
                output_path=download_dir,
                filename=final_filename
            )

    logger.info(
        f"Video saved to: {output_path}"
    )


def convert_to_mp3(
    input_path: str,
    output_path: str,
    bitrate: str = "192k",
    start_end: tuple = None
):
    """
    Convert any audio source to MP3.

    Uses compatibility-focused settings:
        MP3
        specified bitrate
        44.1 kHz
        stereo
        ID3v2.3
    """

    command = [
        "ffmpeg",
        "-y",
        "-i", input_path
    ]

    if start_end:
        start, end = start_end

        if start < 0:
            raise ValueError(
                "START_END start cannot be negative."
            )

        if end <= start:
            raise ValueError(
                f"Invalid START_END: "
                f"end ({end}) must be greater "
                f"than start ({start})"
            )

        command += [
            "-ss", str(start),
            "-t", str(end - start)
        ]

    command += [
        "-vn",
        "-c:a", "libmp3lame",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", bitrate,
        "-id3v2_version", "3",
        output_path
    ]

    subprocess.run(
        command,
        check=True
    )


def convert_to_mp3_with_limit(
    input_path: str,
    output_path: str,
    max_file_size_mb: int,
    duration_sec: int,
    logger,
    min_bitrate_kbps: int = 32
):
    """
    Convert to MP3 and try to keep the final
    file below max_file_size_mb.

    NOTE:
    This function is currently not used by
    the new yt-dlp audio download path.
    """

    max_bytes = (
        max_file_size_mb
        * 1_000_000
    )

    bitrate_kbps = int(
        (max_bytes * 8)
        / duration_sec
        / 1000
    )

    if bitrate_kbps < min_bitrate_kbps:
        logger.warning(
            f"Even minimum bitrate "
            f"{min_bitrate_kbps} kbps "
            f"may exceed target size."
        )

        bitrate_kbps = min_bitrate_kbps

    while bitrate_kbps >= min_bitrate_kbps:

        bitrate_str = (
            f"{bitrate_kbps}k"
        )

        logger.info(
            f"Attempting MP3 conversion "
            f"with bitrate: {bitrate_str}"
        )

        root, ext = os.path.splitext(
            output_path
        )

        temp_output_path = (
            f"{root}_{bitrate_kbps}k{ext}"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-vn",
            "-c:a", "libmp3lame",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", bitrate_str,
            "-id3v2_version", "3",
            temp_output_path
        ]

        subprocess.run(
            command,
            check=True
        )

        final_size = os.path.getsize(
            temp_output_path
        )

        logger.info(
            f"Resulting file size: "
            f"{final_size / 1024:.2f} KB "
            f"({final_size / 1_000_000:.2f} MB decimal)"
        )

        if final_size <= max_bytes:

            os.replace(
                temp_output_path,
                output_path
            )

            return True

        os.remove(
            temp_output_path
        )

        logger.warning(
            f"File too large "
            f"(> {max_file_size_mb} MB), "
            f"reducing bitrate and retrying..."
        )

        bitrate_kbps -= 8

    logger.error(
        f"Could not reduce file under "
        f"{max_file_size_mb} MB "
        f"even at "
        f"{min_bitrate_kbps} kbps."
    )

    return False


def main():

    # Examples:
    #
    # VIDEO_URL = "https://www.youtube.com/watch?v=R4MInIP2c-A"
    # VIDEO_URL = "https://www.youtube.com/shorts/f3YgyJp0Aqw"

    VIDEO_URL = "https://youtu.be/24hfDD3gAAU"

    # "video" or "audio"
    MODE = "video"

    # Used only for video mode:
    # "highest", "1080p", "720p", etc.
    RESOLUTION = "480p"

    # Currently NOT used by the new yt-dlp audio path.
    MAX_FILE_SIZE_MB = None

    DOWNLOAD_DIR = "downloads"

    # Video-specific settings.
    REENCODE_VIDEO = True
    FAST_ENCODE = False

    # None = all CPU cores
    THREADS = None

    # -------------------------------------------------
    # AUDIO / VIDEO TRIMMING
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
    START_END = None

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
            start_end=START_END
        )


if __name__ == "__main__":
    main()