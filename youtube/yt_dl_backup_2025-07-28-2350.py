import os
import re
import logging
import subprocess
import time
import multiprocessing
from pytubefix import YouTube
from datetime import timedelta


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
    """Convert seconds into mm:ss format."""
    return str(timedelta(seconds=seconds))


def ensure_unique_filename(directory: str, base_name: str, ext: str = ".mp4") -> str:
    """Appends (1), (2)... to filename if one already exists."""
    i = 1
    final_name = f"{base_name}{ext}"
    while os.path.exists(os.path.join(directory, final_name)):
        final_name = f"{base_name} ({i}){ext}"
        i += 1
    return final_name


def merge_video_audio(video_path: str, audio_path: str, output_path: str, duration_sec: int,
                      reencode: bool = True, fast_encode: bool = False, threads: int = None,
                      start_end: tuple = None):
    """Merge video and audio with optional re-encoding, thread control, and progress display."""

    total_cores = multiprocessing.cpu_count()
    used_threads = threads if threads else total_cores

    # Build command
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
            command += ["-preset", "ultrafast"]

        if start_end:
            start, end = start_end
            command += ["-ss", str(start), "-to", str(end)]
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

    print(f"[INFO] Merging video and audio...")
    print(f"[INFO] Using {used_threads}/{total_cores} CPU cores")

    process = subprocess.Popen(command, stderr=subprocess.PIPE, universal_newlines=True)

    time_pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    start_time = time.time()

    last_percent = -1

    for line in process.stderr:
        match = time_pattern.search(line)
        if match:
            h, m, s, ms = map(int, match.groups())
            current_sec = h * 3600 + m * 60 + s + ms / 100.0
            percent = min((current_sec / duration_sec) * 100, 100)

            # Only update every ~1% to avoid spamming
            if int(percent) != last_percent:
                last_percent = int(percent)
                elapsed = time.time() - start_time
                if percent > 0:
                    remaining = (elapsed / percent) * (100 - percent)
                    eta = time.time() + remaining
                    eta_str = time.strftime("%H:%M:%S", time.localtime(eta))
                else:
                    eta_str = "Calculating..."
                elapsed_str = str(timedelta(seconds=int(elapsed)))
                print(f"\r[PROGRESS] {percent:.2f}% | Elapsed: {elapsed_str} | ETA: {eta_str}", end='')

    process.wait()
    # Force final progress update to 100%
    elapsed = time.time() - start_time
    elapsed_str = str(timedelta(seconds=int(elapsed)))
    print(f"\r[PROGRESS] 100.00% | Elapsed: {elapsed_str} | ETA: done      ")

    print("\n[INFO] Merging complete.")


def download_video(video_url: str, resolution: str = "highest", download_dir: str = "downloads",
                       mode: str = "video", max_file_size_mb: int = None, reencode: bool = True,
                       fast_encode: bool = False, threads: int = None, start_end: tuple = None):
    """Download a YouTube video with specified resolution and log metadata."""
    if mode == "audio":
        try:
            yt = YouTube(video_url)
        except Exception as e:
            logger.error(f"Failed to initialize YouTube object: {e}")
            return

        title = yt.title
        duration = yt.length
        channel = yt.author

        logger.info(f"Title   : {title}")
        logger.info(f"Channel : {channel}")
        logger.info(f"Duration: {format_duration(duration)}")

        safe_title = sanitize_filename(title)
        os.makedirs(download_dir, exist_ok=True)
        final_filename = ensure_unique_filename(download_dir, safe_title, ext=".mp3")

        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()

        if not audio_stream:
            logger.error("No audio stream found.")
            return

        temp_audio_path = os.path.join(download_dir, "temp_audio.webm")
        final_audio_path = os.path.join(download_dir, final_filename)

        logger.info(f"Downloading audio: {audio_stream.abr}")
        audio_stream.download(output_path=download_dir, filename="temp_audio.webm")

        # Convert to mp3 with file size constraint if provided
        if max_file_size_mb:
            success = convert_to_mp3_with_limit(
                input_path=temp_audio_path,
                output_path=final_audio_path,
                max_file_size_mb=max_file_size_mb,
                duration_sec=yt.length,
                logger=logger
            )
            os.remove(temp_audio_path)

            if not success:
                logger.error(f"Failed to create MP3 under {max_file_size_mb}MB.")
                return
        else:
            bitrate_str = "192k"
            logger.info(f"Converting to mp3 at default bitrate: {bitrate_str}")
            convert_to_mp3(temp_audio_path, final_audio_path, bitrate=bitrate_str)
            os.remove(temp_audio_path)

        logger.info(f"Audio saved to: {final_audio_path}")
        return

    try:
        yt = YouTube(video_url)
    except Exception as e:
        logger.error(f"Failed to initialize YouTube object: {e}")
        return

    title = yt.title
    duration = yt.length
    channel = yt.author

    # Log video info
    logger.info(f"Title   : {title}")
    logger.info(f"Channel : {channel}")
    logger.info(f"Duration: {format_duration(duration)}")

    # Prepare safe filename and output directory
    safe_title = sanitize_filename(title)
    os.makedirs(download_dir, exist_ok=True)
    final_filename = ensure_unique_filename(download_dir, safe_title)

    if resolution == "highest":
        # Get the highest video+audio adaptive
        video_stream = yt.streams.filter(adaptive=True, only_video=True).order_by('resolution').desc().first()
        audio_stream = yt.streams.filter(adaptive=True, only_audio=True).order_by('abr').desc().first()

        if not video_stream or not audio_stream:
            logger.error("Could not find suitable adaptive streams.")
            return

        video_path = os.path.join(download_dir, "temp_video.mp4")
        audio_path = os.path.join(download_dir, "temp_audio.mp4")
        output_path = os.path.join(download_dir, final_filename)

        logger.info(f"Downloading video: {video_stream.resolution}")
        video_stream.download(output_path=download_dir, filename="temp_video.mp4")

        logger.info(f"Downloading audio: {audio_stream.abr}")
        audio_stream.download(output_path=download_dir, filename="temp_audio.mp4")

        logger.info("Merging video and audio with ffmpeg...")
        merge_video_audio(video_path, audio_path, output_path, yt.length, reencode=reencode, fast_encode=fast_encode,
                          threads=threads, start_end=start_end)

        os.remove(video_path)
        os.remove(audio_path)

    else:
        # Look for progressive streams (video + audio together)
        stream = yt.streams.filter(progressive=True, file_extension="mp4", res=resolution).first()

        if not stream:
            logger.warning(f"No progressive stream found for {resolution}, falling back to 'highest'")
            stream = yt.streams.get_highest_resolution()

        output_path = os.path.join(download_dir, final_filename)
        logger.info(f"Downloading progressive stream: {stream.resolution}")
        stream.download(output_path=download_dir, filename=final_filename)

    logger.info(f"Video saved to: {output_path}")


def convert_to_mp3(input_path: str, output_path: str, bitrate: str = "192k"):
    """Convert audio file to mp3 using ffmpeg with specified bitrate."""
    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vn",  # disable video
        "-ar", "44100",  # sample rate
        "-ac", "2",      # audio channels
        "-b:a", bitrate,  # audio bitrate
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def convert_to_mp3_with_limit(input_path: str, output_path: str, max_file_size_mb: int, duration_sec: int, logger, min_bitrate_kbps: int = 32):
    """Convert to mp3 and ensure final file is under max_file_size_mb."""
    max_bytes = max_file_size_mb * 1_000_000  # Notion uses decimal MB
    # Start with initial estimate
    bitrate_kbps = int((max_bytes * 8) / duration_sec / 1000)

    if bitrate_kbps < min_bitrate_kbps:
        logger.warning(f"Even minimum bitrate {min_bitrate_kbps}kbps exceeds target size.")
        bitrate_kbps = min_bitrate_kbps

    while bitrate_kbps >= min_bitrate_kbps:
        bitrate_str = f"{bitrate_kbps}k"
        logger.info(f"Attempting MP3 conversion with bitrate: {bitrate_str}")

        # Temporary path for current attempt
        temp_output_path = output_path.replace(".mp3", f"_{bitrate_kbps}k.mp3")

        # Convert using ffmpeg
        command = [
            "ffmpeg",
            "-y",
            "-i", input_path,
            "-vn",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", bitrate_str,
            temp_output_path
        ]
        subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        final_size = os.path.getsize(temp_output_path)
        logger.info(f"Resulting file size: {final_size / 1024:.2f} KB ({final_size / 1_000_000:.2f} MB decimal)")

        if final_size <= max_bytes:
            # Rename to final output path
            os.rename(temp_output_path, output_path)
            return True

        # File too big, try lower bitrate
        os.remove(temp_output_path)
        logger.warning(f"File too large (> {max_file_size_mb}MB), reducing bitrate and retrying...")
        bitrate_kbps -= 8  # reduce by 8kbps per retry

    logger.error(f"Could not reduce file under {max_file_size_mb}MB even at {min_bitrate_kbps}kbps.")
    return False


def main():
    # VIDEO_URL = "https://www.youtube.com/watch?v=R4MInIP2c-A"
    # VIDEO_URL = "https://www.youtube.com/shorts/f3YgyJp0Aqw"
    VIDEO_URL = "https://youtu.be/u8s9hpjN25Y"
    MODE = "video"
    RESOLUTION = "highest"
    MAX_FILE_SIZE_MB = None
    DOWNLOAD_DIR = "downloads"
    REENCODE_VIDEO = True
    FAST_ENCODE = False
    THREADS = None  # or set to 2, 4, 6...
    START_END = (806.24, 868.5)  # None or something like (42.6, 55.9) WORKS ONLY WHEN `REENCODE_VIDEO = True`

    if MODE == "audio":
        download_video(
            video_url=VIDEO_URL,
            mode="audio",
            download_dir=DOWNLOAD_DIR,
            max_file_size_mb=MAX_FILE_SIZE_MB
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
        )


if __name__ == "__main__":
    main()