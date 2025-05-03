from pathlib import Path
import yt_dlp

class YouTubeDownloader:
    def download_audio(self, video_id: str, output_dir: str) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path / f'audio_{video_id}.%(ext)s'),
            'progress_hooks': [self._progress_hook],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            # Return path to the downloaded file
            return output_path / f'audio_{video_id}.mp3'
            
        except Exception as e:
            raise RuntimeError(f"Download failed: {str(e)}")
    
    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%')
            print(f"\rDownloading audio... {percent}", end='', flush=True)
        elif d['status'] == 'finished':
            print("\nDownload completed. Converting...")

