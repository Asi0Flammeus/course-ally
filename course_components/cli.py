import click
import tempfile
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import yt_dlp

from course_components.downloader import YouTubeDownloader
from course_components.transcription import TranscriptionService
from course_components.lecture import LectureGenerator
from course_components.utils import detect_youtube_url_type

@click.group()
def cli() -> None:
    """
    Course Components CLI.

    Use this CLI to generate various course components, such as lectures.
    """
    pass

@cli.command('create-lecture')
@click.argument('video_id')
@click.option('--output', '-o', type=click.Path(), default=None,
              help='Path to save the generated lecture markdown file.')
@click.option('--sections', '-s', default=3, show_default=True,
              help='Number of main sections for the lecture.')
def create_lecture(video_id: str, output: str, sections: int) -> None:
    """
    Create a lecture markdown from a YouTube video ID.

    VIDEO_ID is the YouTube video identifier (e.g., dQw4w9WgXcQ).
    """
    downloader = YouTubeDownloader()
    transcription_service = TranscriptionService()  # Removed api_key parameter
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Progress callback for download and transcription
        def progress_callback(message):
            click.echo(message)

        # Download audio
        click.echo('Downloading audio from YouTube...')
        try:
            audio_path = downloader.download_audio(video_id, tmpdir, progress_callback=progress_callback)
            click.echo(f'Audio downloaded to {audio_path}')
        except Exception as e:
            click.echo(f"Error downloading audio: {e}", err=True)
            raise click.Abort()

        # Transcribe audio
        click.echo('Transcribing audio...')
        try:
            transcript = transcription_service.transcribe(audio_path, progress_callback=progress_callback)
            click.echo('Transcription completed.')
        except Exception as e:
            click.echo(f"Error during transcription: {e}", err=True)
            raise click.Abort()

        click.echo('Generating lecture content...')
        generator = LectureGenerator()
        try:
            lecture_md = generator.generate_markdown(transcript, num_sections=sections)
        except Exception as e:
            click.echo(f"Error generating lecture: {e}", err=True)
            raise click.Abort()
        click.echo('Lecture generation completed.')

        if output:
            output_path = Path(output)
            output_path.write_text(lecture_md, encoding='utf-8')
            click.echo(f'Lecture saved to {output_path}')
        else:
            click.echo('\nGenerated Lecture:\n')
            click.echo(lecture_md)

@cli.command('extract-playlist-transcripts')
@click.argument('youtube_url')
@click.option('--output-dir', '-d', type=click.Path(), default='transcripts',
              help='Directory to save transcript files.')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within transcripts directory.')
@click.option('--format', '-f', type=click.Choice(['txt', 'json']), default='txt',
              help='Output format for transcripts.')
@click.option('--max-workers', '-w', type=int, default=4,
              help='Maximum number of parallel workers for transcription.')
def extract_playlist_transcripts(youtube_url: str, output_dir: str, subfolder: str, format: str, max_workers: int) -> None:
    """
    Extract transcripts from YouTube content (auto-detects videos vs playlists).

    YOUTUBE_URL can be either a single video URL or playlist URL.
    """
    start_time = time.time()
    
    # Detect URL type
    url_type, identifier = detect_youtube_url_type(youtube_url)
    
    if url_type == 'invalid':
        click.echo("❌ Invalid YouTube URL provided.")
        click.echo("Supported formats:")
        click.echo("  • https://www.youtube.com/watch?v=VIDEO_ID")
        click.echo("  • https://youtu.be/VIDEO_ID")
        click.echo("  • https://www.youtube.com/playlist?list=PLAYLIST_ID")
        raise click.Abort()
    
    click.echo(f'🔍 URL Type Detected: {url_type.upper()}')
    
    downloader = YouTubeDownloader()
    transcription_service = TranscriptionService()
    
    # Use outputs/transcripts as base directory
    base_path = Path('outputs') / 'transcripts'
    if subfolder:
        output_path = base_path / subfolder
    else:
        output_path = base_path
    output_path.mkdir(parents=True, exist_ok=True)
    
    if url_type == 'video':
        # Handle single video
        video_id = identifier
        click.echo('🎥 Starting single video transcript extraction...')
        click.echo(f'📁 Output directory: {output_path.absolute()}')
        click.echo(f'📋 Output format: {format}')
        click.echo('─' * 60)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Progress callback
            def progress_callback(message):
                click.echo(message)

            try:
                # Download audio
                click.echo('🔽 Downloading audio from YouTube...')
                audio_path = downloader.download_audio(video_id, tmpdir, progress_callback=progress_callback)
                click.echo(f'Audio downloaded to {audio_path}')

                # Transcribe audio
                click.echo('🎤 Transcribing audio...')
                transcript = transcription_service.transcribe(audio_path, progress_callback=progress_callback)
                click.echo('Transcription completed.')

                # Save transcript
                timestamp = time.strftime('%Y%m%d_%H%M%S')
                
                if format == 'txt':
                    filename = f"video_{video_id}_{timestamp}.txt"
                    transcript_file = output_path / filename
                    
                    # Add metadata header
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    word_count = len(transcript.split())
                    sentence_count = len(transcript.split('\n'))
                    
                    metadata_header = f"""# Video Transcript
Video ID: {video_id}
URL: {video_url}
Transcribed: {time.strftime('%Y-%m-%d %H:%M:%S')}
Words: {word_count} | Sentences: {sentence_count}

{'='*60}

"""
                    
                    transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                    click.echo(f'📄 Transcript saved to {transcript_file}')
                    
                else:  # JSON format
                    filename = f"video_{video_id}_{timestamp}.json"
                    transcript_file = output_path / filename
                    
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    transcript_data = {
                        'video_id': video_id,
                        'url': video_url,
                        'transcript': transcript,
                        'word_count': len(transcript.split()),
                        'sentence_count': len(transcript.split('\n')),
                        'transcribed_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    
                    with open(transcript_file, 'w', encoding='utf-8') as f:
                        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                    
                    click.echo(f'📄 Transcript saved to {transcript_file}')

                click.echo(f'📁 Output location: {output_path.absolute()}')
                click.echo('✅ Single video transcription completed!')
                return

            except Exception as e:
                click.echo(f"❌ Error: {e}", err=True)
                raise click.Abort()
    
    # Handle playlist (existing logic)
    playlist_url = youtube_url
    click.echo('🎬 Starting playlist transcript extraction...')
    click.echo(f'📁 Output directory: {output_path.absolute()}')
    click.echo(f'📋 Output format: {format}')
    click.echo(f'⚡ Max workers: {max_workers}')
    click.echo('─' * 60)
    
    # Progress callback for playlist extraction
    def playlist_progress(message):
        click.echo(f'📋 {message}')
    
    # Get playlist video IDs (fastest method)
    try:
        video_ids = downloader.get_playlist_video_ids(playlist_url, progress_callback=playlist_progress)
        click.echo('─' * 60)
        if not video_ids:
            click.echo("❌ No videos found in playlist.")
            return
            
        click.echo(f'✅ Ready to process {len(video_ids)} videos')
        
    except Exception as e:
        click.echo(f"❌ Error extracting playlist: {e}", err=True)
        raise click.Abort()
    
    transcripts_data = []
    successful_transcripts = 0
    failed_transcripts = 0
    total_words = 0
    total_characters = 0
    
    # Thread-safe lock for updating shared variables
    stats_lock = threading.Lock()
    
    def process_video(video_data):
        """Process a single video: download, transcribe, and save."""
        idx, video_id = video_data
        
        # Check if video is already transcribed
        existing_files = list(output_path.glob(f"*{video_id}*"))
        if existing_files:
            return {
                'status': 'skipped',
                'video_id': video_id,
                'message': f'Already transcribed: {existing_files[0].name}',
                'idx': idx
            }
        
        video_start_time = time.time()
        
        # Create individual instances for thread safety
        video_downloader = YouTubeDownloader()
        video_transcription_service = TranscriptionService()
        
        # Progress callback for individual video processing
        def video_progress(message):
            with stats_lock:
                click.echo(f'    [{idx}/{len(video_ids)}] {message}')
        
        # Use individual temp directory for each video
        with tempfile.TemporaryDirectory() as video_tmpdir:
            try:
                with stats_lock:
                    click.echo(f'\n🎥 [{idx}/{len(video_ids)}] Processing video ID: {video_id}')
                
                # Download and convert audio for this video only
                with stats_lock:
                    click.echo(f'    [{idx}/{len(video_ids)}] 🔽 Downloading and converting audio...')
                audio_path = video_downloader.download_audio(video_id, video_tmpdir, progress_callback=video_progress)
                
                # Transcribe audio immediately
                with stats_lock:
                    click.echo(f'    [{idx}/{len(video_ids)}] 🎤 Transcribing audio...')
                transcript = video_transcription_service.transcribe(audio_path, progress_callback=video_progress)
                
                # Calculate stats
                word_count = len(transcript.split())
                char_count = len(transcript)
                
                # Save transcript (simplified filename since we don't have title)
                filename = f"{idx:02d}_video_{video_id}"
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                
                result_data = {
                    'video_id': video_id,
                    'url': video_url,
                    'transcript': transcript,
                    'word_count': word_count,
                    'character_count': char_count,
                    'transcribed_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'filename': filename
                }
                
                if format == 'txt':
                    transcript_file = output_path / f"{filename}.txt"
                    
                    # Add metadata header to txt files
                    metadata_header = f"""# Video Transcript
Video ID: {video_id}
URL: {video_url}
Transcribed: {time.strftime('%Y-%m-%d %H:%M:%S')}
Words: {word_count} | Characters: {char_count}

{'='*60}

"""
                    
                    transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                    with stats_lock:
                        click.echo(f'    [{idx}/{len(video_ids)}] ✅ Transcript saved to {transcript_file.name}')
                
                video_time = time.time() - video_start_time
                with stats_lock:
                    click.echo(f'    [{idx}/{len(video_ids)}] ⏱️  Completed in {video_time:.1f}s ({word_count} words)')
                    click.echo(f'    [{idx}/{len(video_ids)}] 🗑️  Audio file cleaned up automatically')
                
                return {
                    'status': 'success',
                    'data': result_data,
                    'idx': idx,
                    'video_id': video_id
                }
                
            except Exception as e:
                with stats_lock:
                    click.echo(f"    [{idx}/{len(video_ids)}] ❌ Error processing video {video_id}: {e}", err=True)
                return {
                    'status': 'failed',
                    'video_id': video_id,
                    'error': str(e),
                    'idx': idx
                }
    
    click.echo('─' * 60)
    click.echo(f'🚀 Starting parallel processing with {max_workers} workers...')
    
    # Filter out already processed videos
    videos_to_process = []
    for idx, video_id in enumerate(video_ids, 1):
        existing_files = list(output_path.glob(f"*{video_id}*"))
        if not existing_files:
            videos_to_process.append((idx, video_id))
        else:
            click.echo(f'⏭️  [{idx}/{len(video_ids)}] Skipping - already transcribed: {existing_files[0].name}')
    
    if not videos_to_process:
        click.echo("✅ All videos already transcribed!")
    else:
        click.echo(f'📊 Processing {len(videos_to_process)} videos in parallel...')
        
        # Process videos in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_video = {executor.submit(process_video, video_data): video_data for video_data in videos_to_process}
            
            # Process completed jobs as they finish
            for future in as_completed(future_to_video):
                result = future.result()
                
                if result['status'] == 'success':
                    with stats_lock:
                        successful_transcripts += 1
                        total_words += result['data']['word_count']
                        total_characters += result['data']['character_count']
                        if format == 'json':
                            transcripts_data.append(result['data'])
                elif result['status'] == 'failed':
                    with stats_lock:
                        failed_transcripts += 1
    
    # Save JSON format if requested
    if format == 'json':
        json_file = output_path / 'playlist_transcripts.json'
        
        # Add summary metadata to JSON
        summary_data = {
            'playlist_url': playlist_url,
            'extraction_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_videos': len(video_ids),
            'successful_transcripts': successful_transcripts,
            'failed_transcripts': failed_transcripts,
            'total_words': total_words,
            'total_characters': total_characters,
            'transcripts': transcripts_data
        }
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
        click.echo(f'\n📄 All transcripts saved to {json_file}')
    
    # Final summary
    total_time = time.time() - start_time
    click.echo('═' * 60)
    click.echo('📊 EXTRACTION SUMMARY')
    click.echo('═' * 60)
    click.echo(f'✅ Successful transcripts: {successful_transcripts}/{len(video_ids)}')
    if failed_transcripts > 0:
        click.echo(f'❌ Failed transcripts: {failed_transcripts}/{len(video_ids)}')
    click.echo(f'📝 Total words transcribed: {total_words:,}')
    click.echo(f'📄 Total characters: {total_characters:,}')
    click.echo(f'⏱️  Total processing time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
    if successful_transcripts > 0:
        click.echo(f'⚡ Average time per video: {total_time/successful_transcripts:.1f}s')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! Happy learning! 🎓')

@cli.command('extract-playlist-links')
@click.argument('playlist_url')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within yt_links directory.')
@click.option('--live-format', '-l', is_flag=True, default=False,
              help='Use live embed format instead of regular video links.')
def extract_playlist_links(playlist_url: str, subfolder: str, live_format: bool) -> None:
    """
    Extract all video links from a YouTube playlist and save to markdown.

    PLAYLIST_URL is the YouTube playlist URL.
    """
    start_time = time.time()
    
    downloader = YouTubeDownloader()
    
    # Set up output directory structure
    base_path = Path('outputs') / 'yt_links'
    if subfolder:
        output_path = base_path / subfolder
    else:
        output_path = base_path
    output_path.mkdir(parents=True, exist_ok=True)
    
    click.echo('🔗 Starting playlist link extraction...')
    click.echo(f'📁 Output directory: {output_path.absolute()}')
    click.echo(f'🎬 Link format: {"Live embed" if live_format else "Regular video"}')
    click.echo('─' * 60)
    
    # Progress callback for playlist extraction
    def playlist_progress(message):
        click.echo(f'📋 {message}')
    
    # Get playlist videos with metadata
    try:
        videos = downloader.get_playlist_videos(playlist_url, progress_callback=playlist_progress)
        click.echo('─' * 60)
        if not videos:
            click.echo("❌ No videos found in playlist.")
            return
            
        click.echo(f'✅ Found {len(videos)} videos')
        
    except Exception as e:
        click.echo(f"❌ Error extracting playlist: {e}", err=True)
        raise click.Abort()
    
    # Generate markdown content
    click.echo('📝 Generating markdown file...')
    
    # Get playlist metadata
    try:
        ydl_opts = {'quiet': True, 'extract_flat': True, 'no_warnings': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            playlist_title = playlist_info.get('title', 'Unknown Playlist')
            playlist_uploader = playlist_info.get('uploader', 'Unknown Channel')
            playlist_description = playlist_info.get('description', 'No description available')
    except:
        playlist_title = 'YouTube Playlist'
        playlist_uploader = 'Unknown Channel'
        playlist_description = 'No description available'
    
    # Create markdown content
    md_content = f"""# {playlist_title}

## Playlist Information
- **Channel:** {playlist_uploader}
- **Total Videos:** {len(videos)}
- **Extracted:** {time.strftime('%Y-%m-%d %H:%M:%S')}
- **Link Format:** {"Live Embed" if live_format else "Regular Video Links"}
- **Original URL:** {playlist_url}

## Description
{playlist_description[:500]}{"..." if len(playlist_description) > 500 else ""}

---

## Video Links

"""
    
    # Add video links
    for idx, video in enumerate(videos, 1):
        video_id = video['id']
        video_title = video['title']
        duration = video.get('duration_string', 'Unknown')
        
        if live_format:
            # Live embed format
            embed_url = f"https://youtube.com/embed/{video_id}"
            md_content += f"{idx:02d}. **{video_title}** ({duration})  \n"
            md_content += f"<liveUrl>{embed_url}</liveUrl>\n\n"
        else:
            # Regular video link format
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            md_content += f"{idx:02d}. **{video_title}** ({duration})  \n"
            md_content += f"![lecture]({video_url})\n\n"
    
    # Add footer
    md_content += f"""---

**Generated by Course Ally** 🎓  
*Extraction completed in {time.time() - start_time:.1f} seconds*
"""
    
    # Save markdown file
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    filename = f"playlist_links_{timestamp}.md"
    md_file = output_path / filename
    
    md_file.write_text(md_content, encoding='utf-8')
    
    # Final summary
    extraction_time = time.time() - start_time
    click.echo('═' * 60)
    click.echo('📊 EXTRACTION SUMMARY')
    click.echo('═' * 60)
    click.echo(f'📺 Playlist: {playlist_title}')
    click.echo(f'🎬 Total videos: {len(videos)}')
    click.echo(f'🔗 Link format: {"Live embed" if live_format else "Regular video"}')
    click.echo(f'⏱️  Processing time: {extraction_time:.1f}s')
    click.echo(f'📄 Markdown file: {md_file}')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! Happy organizing! 📋')

