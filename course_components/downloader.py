from pathlib import Path
import yt_dlp
from typing import List, Dict

class YouTubeDownloader:
    def get_playlist_video_ids(self, playlist_url: str, progress_callback=None) -> List[str]:
        """
        Extract only video IDs from a YouTube playlist (fastest method).
        
        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of video IDs
        """
        if progress_callback:
            progress_callback("Extracting video IDs from playlist...")
        
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,  # Fastest extraction
            'playlistend': None,
            'no_warnings': True,
            'skip_download': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(playlist_url, download=False)
                
                video_ids = []
                entries = playlist_info.get('entries', [])
                
                if progress_callback:
                    progress_callback(f"Found {len(entries)} videos in playlist")
                
                for entry in entries:
                    if entry and entry.get('id'):
                        video_ids.append(entry['id'])
                
                if progress_callback:
                    progress_callback(f"Successfully extracted {len(video_ids)} video IDs")
                
                return video_ids
                
        except Exception as e:
            raise RuntimeError(f"Failed to extract playlist video IDs: {str(e)}")

    def get_playlist_videos(self, playlist_url: str, progress_callback=None) -> List[Dict[str, str]]:
        """
        Extract video information from a YouTube playlist.
        
        Args:
            playlist_url: YouTube playlist URL
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of dictionaries containing video ID, title, and URL
        """
        if progress_callback:
            progress_callback("Connecting to YouTube...")
        
        ydl_opts = {
            'quiet': True,
            'extract_flat': 'in_playlist',  # Only extract minimal info for speed
            'playlistend': None,  # Get all videos
            'no_warnings': True,
            'skip_download': True,  # We only want metadata, not downloads
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if progress_callback:
                    progress_callback("Fetching playlist metadata...")
                
                playlist_info = ydl.extract_info(playlist_url, download=False)
                
                if progress_callback:
                    playlist_title = playlist_info.get('title', 'Unknown Playlist')
                    uploader = playlist_info.get('uploader', 'Unknown Channel')
                    progress_callback(f"Playlist: '{playlist_title}' by {uploader}")
                
                videos = []
                entries = playlist_info.get('entries', [])
                total_entries = len(entries)
                
                if progress_callback:
                    progress_callback(f"Processing {total_entries} video entries...")
                
                for idx, entry in enumerate(entries, 1):
                    if entry:
                        video_id = entry.get('id', '')
                        video_title = entry.get('title', 'Unknown Title')
                        
                        if progress_callback and idx % 10 == 0:  # Progress every 10 videos
                            progress_callback(f"Processed {idx}/{total_entries} video entries...")
                        
                        videos.append({
                            'id': video_id,
                            'title': video_title,
                            'url': entry.get('url', f"https://www.youtube.com/watch?v={video_id}"),
                            'duration_string': entry.get('duration_string', 'Unknown')
                        })
                
                if progress_callback:
                    progress_callback(f"Successfully extracted {len(videos)} valid videos from playlist")
                
                return videos
                
        except Exception as e:
            raise RuntimeError(f"Failed to extract playlist videos: {str(e)}")

    def download_audio(self, video_id: str, output_dir: str, progress_callback=None) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Store callback for progress hook
        self._current_progress_callback = progress_callback
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': str(output_path / f'audio_{video_id}.%(ext)s'),
            'progress_hooks': [self._progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            if progress_callback:
                progress_callback("    Audio download and conversion completed")
            
            # Return path to the downloaded file
            return output_path / f'audio_{video_id}.mp3'
            
        except Exception as e:
            raise RuntimeError(f"Download failed: {str(e)}")
        finally:
            # Clean up callback reference
            self._current_progress_callback = None
    
    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', 'N/A')
            eta = d.get('_eta_str', 'N/A')
            
            if self._current_progress_callback:
                # Use \r to overwrite the same line for progress updates
                import sys
                sys.stdout.write(f"\r    Downloading: {percent} (Speed: {speed}, ETA: {eta})")
                sys.stdout.flush()
            else:
                print(f"\rDownloading audio... {percent} (Speed: {speed})", end='', flush=True)
        elif d['status'] == 'finished':
            if self._current_progress_callback:
                # Clear the download line and show completion
                import sys
                sys.stdout.write("\r" + " " * 80 + "\r")  # Clear line
                self._current_progress_callback("    Download finished, converting to MP3...")
            else:
                print("\nDownload completed. Converting...")
        elif d['status'] == 'error':
            if self._current_progress_callback:
                import sys
                sys.stdout.write("\r" + " " * 80 + "\r")  # Clear line
                self._current_progress_callback(f"    Download error: {d.get('error', 'Unknown error')}")
            else:
                print(f"\nDownload error: {d.get('error', 'Unknown error')}")

