from pytubefix import YouTube


def list_available_streams(video_url: str):
    yt = YouTube(video_url)

    print(f"\nTitle   : {yt.title}")
    print(f"Channel : {yt.author}")
    print(f"Length  : {yt.length} seconds\n")

    print("== Progressive Streams (video + audio) ==")
    for stream in yt.streams.filter(progressive=True, file_extension="mp4").order_by('resolution').desc():
        print(f"- {stream.resolution} @ {stream.fps}fps — itag={stream.itag}, size={round(stream.filesize / 1024 / 1024, 2)}MB")

    print("\n== Adaptive Video-Only Streams ==")
    for stream in yt.streams.filter(adaptive=True, only_video=True, file_extension="mp4").order_by('resolution').desc():
        print(f"- {stream.resolution} @ {stream.fps}fps — itag={stream.itag}, size={round(stream.filesize / 1024 / 1024, 2)}MB")

    print("\n== Adaptive Audio-Only Streams ==")
    for stream in yt.streams.filter(adaptive=True, only_audio=True).order_by('abr').desc():
        print(f"- {stream.abr} — itag={stream.itag}, size={round(stream.filesize / 1024 / 1024, 2)}MB")


if __name__ == "__main__":
    # VIDEO_URL = "https://youtu.be/R4MInIP2c-A"
    VIDEO_URL = "https://youtu.be/N6R7OjrYXfM"
    list_available_streams(VIDEO_URL)
