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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_retries': 3,
            'ignoreerrors': False,
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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_retries': 3,
            'ignoreerrors': False,
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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_retries': 3,
            'ignoreerrors': False,
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

    def download_video(self, video_id_or_url: str, output_dir: str, progress_callback=None) -> Path:
        """
        Download a YouTube video or playlist as MP4 files.
        
        Args:
            video_id_or_url: YouTube video ID, video URL, or playlist URL
            output_dir: Directory to save the video files
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Path to the downloaded video file (for single video) or output directory (for playlist)
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Store callback for progress hook
        self._current_progress_callback = progress_callback
        
        # Determine if it's a video or playlist
        is_playlist = 'list=' in video_id_or_url or 'playlist' in video_id_or_url.lower()
        
        # Build the URL if only ID is provided
        if not video_id_or_url.startswith('http'):
            video_url = f"https://www.youtube.com/watch?v={video_id_or_url}"
        else:
            video_url = video_id_or_url
        
        # Configure yt-dlp options for video download
        ydl_opts = {
            'format': 'best[ext=mp4]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': str(output_path / '%(title)s.%(ext)s'),
            'progress_hooks': [self._progress_hook],
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,  # Continue on error for playlists
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_retries': 3,
        }
        
        # Add skip if file exists
        if not is_playlist:
            ydl_opts['overwrites'] = False
            ydl_opts['nooverwrites'] = True
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if progress_callback:
                    progress_callback("Starting download from YouTube...")
                
                ydl.download([video_url])
            
            if progress_callback:
                progress_callback("Video download completed")
            
            # Return the output directory for playlists, or the specific file for single videos
            if is_playlist:
                return output_path
            else:
                # Find the downloaded file
                video_files = list(output_path.glob('*.mp4'))
                if video_files:
                    return video_files[0]
                return output_path
            
        except Exception as e:
            raise RuntimeError(f"Download failed: {str(e)}")
        finally:
            # Clean up callback reference
            self._current_progress_callback = None
    
    def download_playlist_videos(self, playlist_url: str, output_dir: str, progress_callback=None) -> dict:
        """
        Download all videos from a YouTube playlist with detailed progress tracking.
        
        Args:
            playlist_url: YouTube playlist URL
            output_dir: Directory to save the video files
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary with download statistics
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # First, get the list of videos in the playlist
        if progress_callback:
            progress_callback("Fetching playlist information...")
        
        try:
            videos = self.get_playlist_videos(playlist_url, progress_callback=progress_callback)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch playlist: {str(e)}")
        
        if not videos:
            raise RuntimeError("No videos found in playlist")
        
        total_videos = len(videos)
        successful = 0
        skipped = 0
        failed = 0
        
        if progress_callback:
            progress_callback(f"Found {total_videos} videos in playlist")
        
        # Download each video
        for idx, video in enumerate(videos, 1):
            video_id = video['id']
            video_title = video['title']
            
            # Check if file already exists
            safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).strip()
            existing_files = list(output_path.glob(f"*{video_id}*.mp4")) or list(output_path.glob(f"{safe_title}*.mp4"))
            
            if existing_files:
                skipped += 1
                if progress_callback:
                    progress_callback(f"⏭️ [{idx}/{total_videos}] Skipped (already exists): {video_title[:50]}")
                continue
            
            # Store callback for this video
            self._current_progress_callback = progress_callback
            self._current_video_index = idx
            self._total_videos = total_videos
            self._current_video_title = video_title
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best[ext=mp4]/bestvideo+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'outtmpl': str(output_path / '%(title)s.%(ext)s'),
                'progress_hooks': [self._detailed_progress_hook],
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                },
                'extractor_retries': 3,
                'nooverwrites': True,
            }
            
            try:
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    if progress_callback:
                        progress_callback(f"🎥 [{idx}/{total_videos}] Downloading: {video_title[:50]}")
                    
                    ydl.download([video_url])
                
                successful += 1
                if progress_callback:
                    progress_callback(f"✅ [{idx}/{total_videos}] Completed: {video_title[:50]}")
                    
            except Exception as e:
                error_msg = str(e)
                # Check for common errors to skip
                if any(err in error_msg.lower() for err in ['private video', 'unavailable', 'deleted', 'removed']):
                    skipped += 1
                    if progress_callback:
                        progress_callback(f"⏭️ [{idx}/{total_videos}] Skipped (unavailable): {video_title[:50]}")
                else:
                    failed += 1
                    if progress_callback:
                        progress_callback(f"⚠️ [{idx}/{total_videos}] Failed: {video_title[:50]} - {error_msg[:100]}")
        
        # Clean up
        self._current_progress_callback = None
        self._current_video_index = None
        self._total_videos = None
        self._current_video_title = None
        
        return {
            'total': total_videos,
            'successful': successful,
            'skipped': skipped,
            'failed': failed,
            'output_path': str(output_path)
        }
    
    def _detailed_progress_hook(self, d):
        """Detailed progress hook for playlist downloads"""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            
            if self._current_progress_callback and hasattr(self, '_current_video_index'):
                idx = self._current_video_index
                total = self._total_videos
                title = self._current_video_title[:30]
                self._current_progress_callback(
                    f"📥 [{idx}/{total}] {title}... | {percent} | Speed: {speed} | ETA: {eta}"
                )
        elif d['status'] == 'finished':
            if self._current_progress_callback:
                pass  # Will show completed message in main loop
    
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

