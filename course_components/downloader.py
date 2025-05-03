from pathlib import Path
from typing import Union
from pytube import YouTube

class YouTubeDownloader:
    """
    Downloads audio streams from YouTube videos using pytube.
    """
    def download_audio(self, video_id: str, output_dir: Union[str, Path]) -> Path:
        """
        Downloads the audio-only stream of a YouTube video to the specified directory.

        Args:
            video_id: YouTube video identifier (e.g., 'dQw4w9WgXcQ').
            output_dir: Directory where the audio file will be saved.

        Returns:
            Path object pointing to the downloaded audio file.

        Raises:
            RuntimeError: If pytube initialization or download fails.
            ValueError: If no audio streams are found.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        video_url = f"https://www.youtube.com/watch?v={video_id}"
        # Progress callback to visualize downloading
        total_size = {'size': None}
        def on_progress(stream, chunk, bytes_remaining):  # noqa: ARG001
            # Initialize total size
            if total_size['size'] is None:
                total_size['size'] = stream.filesize
            downloaded = total_size['size'] - bytes_remaining
            percent = (downloaded / total_size['size'] * 100) if total_size['size'] else 0
            print(f"\rDownloading audio... {percent:5.1f}%", end='', flush=True)
        try:
            yt = YouTube(video_url, on_progress_callback=on_progress)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize YouTube object for '{video_id}': {e}")

        try:
            audio_stream = (
                yt.streams.filter(only_audio=True)
                .order_by('abr').desc()
                .first()
            )
        except Exception as e:
            raise RuntimeError(f"Error filtering audio streams: {e}")
        if not audio_stream:
            raise ValueError(f"No audio streams found for video ID: {video_id}")

        try:
            downloaded_file = audio_stream.download(
                output_path=str(output_path),
                filename_prefix=f"audio_{video_id}_"
            )
            # Newline after progress bar
            print('', flush=True)
        except Exception as e:
            # Ensure newline before error
            print('', flush=True)
            raise RuntimeError(f"Audio download failed: {e}") from e
        return Path(downloaded_file)