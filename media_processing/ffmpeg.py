import logging
import multiprocessing
import os
import re
import subprocess
import time
from datetime import timedelta


logger = logging.getLogger(__name__)


def merge_video_audio(
    video_path: str,
    audio_path: str | None,
    output_path: str,
    duration_sec: int,
    reencode: bool = True,
    fast_encode: bool = False,
    threads: int = None,
    start_end: tuple = None,
    max_file_size_mb: float = None
):
    """
    Merge video and audio with optional re-encoding,
    thread control, trimming, and progress display.
    """

    total_cores = multiprocessing.cpu_count()
    used_threads = threads if threads else total_cores

    if max_file_size_mb is not None and not reencode:
        raise ValueError(
            "A maximum file size requires video re-encoding."
        )

    if start_end:
        start, end = start_end

        if start < 0 or end <= start:
            raise ValueError(
                f"Invalid START_END: {start_end}. "
                "Start must be non-negative and end must be greater than start."
            )

        duration_sec = end - start

    if duration_sec <= 0:
        raise ValueError("Video duration must be greater than zero.")

    max_bytes = None
    video_bitrate_kbps = None

    if max_file_size_mb is not None:
        if max_file_size_mb <= 0:
            raise ValueError("Maximum file size must be greater than zero.")

        max_bytes = int(max_file_size_mb * 1_000_000)
        audio_bitrate_kbps = 96
        target_total_bitrate_kbps = (
            max_bytes * 8 / duration_sec / 1000 * 0.9
        )
        video_bitrate_kbps = max(
            50,
            int(target_total_bitrate_kbps - audio_bitrate_kbps)
        )

    time_pattern = re.compile(
        r"time=(\d+):(\d+):(\d+)\.(\d+)"
    )

    while True:
        command = [
            "ffmpeg",
            "-y",
            "-i", video_path
        ]

        if audio_path:
            command += ["-i", audio_path]

        if reencode:
            command += [
                "-c:v", "libx264",
                "-c:a", "aac",
                "-movflags", "+faststart",
                "-threads", str(used_threads)
            ]

            if max_bytes is not None:
                command += [
                    "-b:v", f"{video_bitrate_kbps}k",
                    "-b:a", "96k"
                ]

            if fast_encode:
                command += ["-preset", "ultrafast"]

            if start_end:
                command += [
                    "-ss", str(start),
                    "-t", str(end - start)
                ]
        else:
            command += ["-c", "copy"]

        command.append(output_path)

        print("[INFO] Merging video and audio...")
        print(f"[INFO] Using {used_threads}/{total_cores} CPU cores")
        if max_bytes is not None:
            print(
                f"[INFO] Encoding video at "
                f"{video_bitrate_kbps} kbps to meet the "
                f"{max_file_size_mb:g} MB size limit"
            )

        process = subprocess.Popen(
            command,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        start_time = time.time()
        last_percent = -1

        for line in process.stderr:
            match = time_pattern.search(line)

            if match:
                h, m, s, ms = map(int, match.groups())
                current_sec = h * 3600 + m * 60 + s + ms / 100.0
                percent = min((current_sec / duration_sec) * 100, 100)

                if int(percent) != last_percent:
                    last_percent = int(percent)
                    elapsed = time.time() - start_time

                    if percent > 0:
                        remaining = (elapsed / percent) * (100 - percent)
                        eta = time.time() + remaining
                        eta_str = time.strftime(
                            "%H:%M:%S",
                            time.localtime(eta)
                        )
                    else:
                        eta_str = "Calculating..."

                    elapsed_str = str(timedelta(seconds=int(elapsed)))
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

        elapsed_str = str(
            timedelta(seconds=int(time.time() - start_time))
        )
        print(
            f"\r[PROGRESS] "
            f"100.00% | "
            f"Elapsed: {elapsed_str} | "
            f"ETA: done      "
        )

        if max_bytes is None:
            break

        output_size = os.path.getsize(output_path)
        if output_size < max_bytes:
            logger.info(
                f"Output size: {output_size / 1_000_000:.2f} MB "
                f"(< {max_file_size_mb:g} MB)"
            )
            break

        logger.warning(
            f"Output is {output_size / 1_000_000:.2f} MB, "
            f"not below the {max_file_size_mb:g} MB limit; "
            "reducing video bitrate and retrying."
        )

        next_bitrate_kbps = int(
            video_bitrate_kbps * max_bytes / output_size * 0.9
        )
        if next_bitrate_kbps >= video_bitrate_kbps:
            next_bitrate_kbps = video_bitrate_kbps - 10

        if next_bitrate_kbps < 50:
            os.remove(output_path)
            raise RuntimeError(
                f"Could not encode the video below "
                f"{max_file_size_mb:g} MB without reducing "
                "the video bitrate below 50 kbps."
            )

        video_bitrate_kbps = next_bitrate_kbps

    print("\n[INFO] Merging complete.")


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
