import os
import re
import logging
import subprocess
from pytubefix import YouTube
from datetime import timedelta
from yt_dlp import YoutubeDL
from media_processing.ffmpeg import merge_video_audio


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

        # TODO: Move this audio conversion into media_processing.
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
            start_end=start_end,
            max_file_size_mb=max_file_size_mb
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
                start_end=start_end,
                max_file_size_mb=max_file_size_mb
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

            if not stream:
                raise RuntimeError(
                    f"No video stream is available for {resolution}."
                )

            output_path = os.path.join(
                download_dir,
                final_filename
            )

            logger.info(
                f"Downloading progressive stream: "
                f"{stream.resolution}"
            )

            if max_file_size_mb is not None or start_end:
                progressive_path = os.path.join(
                    download_dir,
                    "temp_progressive.mp4"
                )

                stream.download(
                    output_path=download_dir,
                    filename="temp_progressive.mp4"
                )

                merge_video_audio(
                    progressive_path,
                    None,
                    output_path,
                    yt.length,
                    reencode=reencode,
                    fast_encode=fast_encode,
                    threads=threads,
                    start_end=start_end,
                    max_file_size_mb=max_file_size_mb
                )

                if os.path.exists(progressive_path):
                    os.remove(progressive_path)
            else:
                stream.download(
                    output_path=download_dir,
                    filename=final_filename
                )

    logger.info(
        f"Video saved to: {output_path}"
    )
