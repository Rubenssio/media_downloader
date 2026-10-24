import yt_dlp


def list_streams(url):
    ydl = yt_dlp.YoutubeDL({'listformats': True})
    with ydl:
        ydl.extract_info(url, download=False)


list_streams("https://youtu.be/N6R7OjrYXfM")
