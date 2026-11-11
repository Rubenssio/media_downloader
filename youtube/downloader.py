import os
import re
import logging
import shutil
import subprocess
from pytubefix import YouTube
from datetime import timedelta
from yt_dlp import YoutubeDL
from media_processing.ffmpeg import (
    AudioSizeLimitError,
    merge_video_audio,
)


# TODO: Make video downloading also based on yt-dlp, with fallback between yt-dlp and pytubefix
# TODO: Add optional dependency update mechanism for yt-dlp and pytubefix


# Setup logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

STANDARD_RESOLUTION_HEIGHTS = (2160, 1440, 1080, 720, 480, 360, 240, 144)


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


def move_to_final_location(working_path: str, final_path: str) -> None:
    if os.path.abspath(working_path) != os.path.abspath(final_path):
        shutil.move(working_path, final_path)


def _resolution_height(resolution: str) -> int:
    match = re.fullmatch(r"(\d+)p", resolution)
    if not match:
        raise ValueError(f"Invalid video resolution: {resolution!r}")
    return int(match.group(1))


def _build_resolution_attempts(
    source_resolution: str,
    minimum_resolution: str,
) -> list[tuple[str, int]]:
    source_height = _resolution_height(source_resolution)
    minimum_height = _resolution_height(minimum_resolution)
    if minimum_height not in STANDARD_RESOLUTION_HEIGHTS:
        raise ValueError(
            "minimum_resolution must be one of "
            f"{', '.join(f'{height}p' for height in STANDARD_RESOLUTION_HEIGHTS)}."
        )
    if minimum_height > source_height:
        raise ValueError(
            f"minimum_resolution ({minimum_resolution}) cannot be higher "
            f"than the downloaded resolution ({source_resolution})."
        )

    heights = [source_height]
    heights.extend(
        height
        for height in STANDARD_RESOLUTION_HEIGHTS
        if minimum_height <= height < source_height
    )
    return [(f"{height}p", height) for height in heights]


def _stream_bitrate_kbps(stream) -> int:
    bitrate = stream.bitrate
    if bitrate is None or bitrate <= 0:
        raise RuntimeError(
            f"Could not determine the source bitrate for {stream}."
        )
    return max(1, round(bitrate / 1000))


def _video_encoding_options(
    video_stream,
    audio_stream,
    max_file_size_mb: float | None,
    minimum_resolution: str,
    minimum_video_bitrate_kbps: int,
    minimum_audio_bitrate_kbps: int,
    progressive: bool = False,
) -> dict:
    source_resolution_height = _resolution_height(video_stream.resolution)
    initial_video_bitrate_kbps = None
    initial_audio_bitrate_kbps = 96
    resolution_attempts = None

    if max_file_size_mb is not None:
        initial_audio_bitrate_kbps = (
            _stream_bitrate_kbps(audio_stream)
            if audio_stream is not None
            else 96
        )
        initial_video_bitrate_kbps = _stream_bitrate_kbps(video_stream)
        if progressive:
            initial_video_bitrate_kbps = max(
                minimum_video_bitrate_kbps,
                initial_video_bitrate_kbps - initial_audio_bitrate_kbps,
            )
        resolution_attempts = _build_resolution_attempts(
            video_stream.resolution,
            minimum_resolution,
        )

    return {
        "resolution_attempts": resolution_attempts,
        "source_resolution_height": source_resolution_height,
        "initial_video_bitrate_kbps": initial_video_bitrate_kbps,
        "initial_audio_bitrate_kbps": initial_audio_bitrate_kbps,
        "minimum_video_bitrate_kbps": minimum_video_bitrate_kbps,
        "minimum_audio_bitrate_kbps": minimum_audio_bitrate_kbps,
    }


def download_audio_with_ytdlp(
    video_url: str,
    download_dir: str,
    start_end: tuple = None,
    bitrate: int = 192,
    final_download_dir: str = None,
    max_file_size_mb: float | None = None,
    minimum_audio_bitrate_kbps: int = 32,
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

    output_dir = final_download_dir or download_dir
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

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
            output_dir,
            safe_title,
            ext=".mp3"
        )

        final_audio_path = os.path.join(
            output_dir,
            final_filename
        )
        working_audio_path = os.path.join(
            download_dir,
            final_filename
        )

        # TODO: Move this audio conversion into media_processing.
        logger.info(
            "Converting downloaded audio "
            "to USB-compatible MP3..."
        )

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

        if minimum_audio_bitrate_kbps <= 0:
            raise ValueError("Minimum audio bitrate must be greater than zero.")
        if max_file_size_mb is not None and max_file_size_mb <= 0:
            raise ValueError("Maximum file size must be greater than zero.")

        bitrate_kbps = max(bitrate, minimum_audio_bitrate_kbps)
        while True:
            command = [
                "ffmpeg",
                "-y",
                "-i", downloaded_path,
            ]
            if start_end:
                command += [
                    "-ss", str(start_end[0]),
                    "-t", str(start_end[1] - start_end[0]),
                ]
            command += [
                "-vn",
                "-c:a", "libmp3lame",
                "-b:a", f"{bitrate_kbps}k",
                "-ar", "44100",
                "-ac", "2",
                "-id3v2_version", "3",
                working_audio_path,
            ]
            subprocess.run(command, check=True)

            if max_file_size_mb is None:
                break

            max_bytes = int(max_file_size_mb * 1_000_000)
            output_size = os.path.getsize(working_audio_path)
            if output_size < max_bytes:
                logger.info(
                    "Audio output size: %.2f MB (< %g MB)",
                    output_size / 1_000_000,
                    max_file_size_mb,
                )
                break

            if bitrate_kbps <= minimum_audio_bitrate_kbps:
                os.remove(working_audio_path)
                raise AudioSizeLimitError(
                    f"Could not meet the {max_file_size_mb:g} MB size limit "
                    f"at the minimum audio bitrate of "
                    f"{minimum_audio_bitrate_kbps} kbps."
                )

            next_bitrate_kbps = int(
                bitrate_kbps * max_bytes / output_size * 0.9
            )
            if next_bitrate_kbps >= bitrate_kbps:
                next_bitrate_kbps = bitrate_kbps - 8
            bitrate_kbps = max(
                minimum_audio_bitrate_kbps,
                next_bitrate_kbps,
            )
            logger.info(
                "Audio exceeds the size limit; retrying at %s kbps.",
                bitrate_kbps,
            )

        move_to_final_location(
            working_audio_path,
            final_audio_path
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

    except AudioSizeLimitError:
        raise
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
    start_end: tuple = None,
    final_download_dir: str = None,
    minimum_resolution: str = "144p",
    minimum_video_bitrate_kbps: int = 50,
    minimum_audio_bitrate_kbps: int = 32,
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
            bitrate=192,
            final_download_dir=final_download_dir,
            max_file_size_mb=max_file_size_mb,
            minimum_audio_bitrate_kbps=minimum_audio_bitrate_kbps,
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

    output_dir = final_download_dir or download_dir
    os.makedirs(download_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    final_filename = ensure_unique_filename(
        output_dir,
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
            output_dir,
            final_filename
        )
        working_output_path = os.path.join(
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
            working_output_path,
            yt.length,
            reencode=reencode,
            fast_encode=fast_encode,
            threads=threads,
            start_end=start_end,
            max_file_size_mb=max_file_size_mb,
            **_video_encoding_options(
                video_stream,
                audio_stream,
                max_file_size_mb,
                minimum_resolution,
                minimum_video_bitrate_kbps,
                minimum_audio_bitrate_kbps,
            ),
        )
        move_to_final_location(
            working_output_path,
            output_path
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
                output_dir,
                final_filename
            )
            working_output_path = os.path.join(
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
                working_output_path,
                yt.length,
                reencode=reencode,
                fast_encode=fast_encode,
                threads=threads,
                start_end=start_end,
                max_file_size_mb=max_file_size_mb,
                **_video_encoding_options(
                    video_stream,
                    audio_stream,
                    max_file_size_mb,
                    minimum_resolution,
                    minimum_video_bitrate_kbps,
                    minimum_audio_bitrate_kbps,
                ),
            )
            move_to_final_location(
                working_output_path,
                output_path
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
                output_dir,
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
                    os.path.join(download_dir, final_filename),
                    yt.length,
                    reencode=reencode,
                    fast_encode=fast_encode,
                    threads=threads,
                    start_end=start_end,
                    max_file_size_mb=max_file_size_mb,
                    **_video_encoding_options(
                        stream,
                        None,
                        max_file_size_mb,
                        minimum_resolution,
                        minimum_video_bitrate_kbps,
                        minimum_audio_bitrate_kbps,
                        progressive=True,
                    ),
                )
                move_to_final_location(
                    os.path.join(download_dir, final_filename),
                    output_path
                )

                if os.path.exists(progressive_path):
                    os.remove(progressive_path)
            else:
                stream.download(
                    output_path=download_dir,
                    filename=final_filename
                )
                move_to_final_location(
                    os.path.join(download_dir, final_filename),
                    output_path
                )

    logger.info(
        f"Video saved to: {output_path}"
    )
