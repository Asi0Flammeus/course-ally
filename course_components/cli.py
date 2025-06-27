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
from course_components.chapter_generator import ChapterGenerator
from course_components.quiz_generator import QuizGenerator
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

@cli.command('create-chapters')
@click.option('--output-dir', '-d', type=click.Path(), default='outputs/chapters',
              help='Directory to save chapter files.')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within chapters directory.')
@click.option('--max-workers', '-w', type=int, default=2,
              help='Maximum number of parallel workers for chapter generation.')
@click.option('--chapter-title', '-t', type=str, default=None,
              help='Optional custom title for single file chapters.')
def create_chapters(output_dir: str, subfolder: str, max_workers: int, chapter_title: str) -> None:
    """
    Create course chapter markdown files from transcript files or folders.

    INPUT_PATH can be either a single transcript file or a directory containing transcript files.
    """
    start_time = time.time()
    
    # Check if outputs/transcripts directory exists
    transcripts_base = Path('outputs/transcripts')
    if not transcripts_base.exists():
        click.echo("❌ No transcripts directory found at outputs/transcripts")
        click.echo("Run extract-playlist-transcripts first to generate transcripts.")
        raise click.Abort()
    
    # Get all subfolders in outputs/transcripts
    subfolders = [f for f in transcripts_base.iterdir() if f.is_dir()]
    if not subfolders:
        click.echo("❌ No subfolders found in outputs/transcripts")
        raise click.Abort()
    
    # Display available subfolders
    click.echo("📁 Available transcript subfolders:")
    for idx, folder in enumerate(subfolders, 1):
        txt_files = list(folder.glob('*.txt'))
        click.echo(f"  {idx}. {folder.name} ({len(txt_files)} files)")
    
    # Get user selection for subfolder
    while True:
        try:
            choice = click.prompt("\nSelect subfolder number", type=int)
            if 1 <= choice <= len(subfolders):
                selected_folder = subfolders[choice - 1]
                break
            else:
                click.echo(f"❌ Please enter a number between 1 and {len(subfolders)}")
        except click.Abort:
            raise
        except:
            click.echo("❌ Please enter a valid number")
    
    # Get all txt files in selected folder
    all_files = list(selected_folder.glob('*.txt'))
    if not all_files:
        click.echo(f"❌ No .txt files found in {selected_folder.name}")
        raise click.Abort()
    
    # Ask user to choose between whole subfolder or individual files
    click.echo(f"\n📄 Found {len(all_files)} transcript files in '{selected_folder.name}'")
    click.echo("1. Process all files in subfolder")
    click.echo("2. Select individual files")
    
    while True:
        try:
            process_choice = click.prompt("Choose option", type=int)
            if process_choice in [1, 2]:
                break
            else:
                click.echo("❌ Please enter 1 or 2")
        except click.Abort:
            raise
        except:
            click.echo("❌ Please enter a valid number")
    
    if process_choice == 1:
        # Process all files
        mode = 'directory'
        files_to_process = all_files
        input_path = selected_folder
    else:
        # Let user select individual files
        click.echo(f"\n📋 Files in '{selected_folder.name}':")
        for idx, file in enumerate(all_files, 1):
            click.echo(f"  {idx}. {file.name}")
        
        click.echo("\nEnter file numbers to process (comma-separated, e.g., 1,3,5):")
        while True:
            try:
                file_choices = click.prompt("File numbers").strip()
                selected_indices = [int(x.strip()) for x in file_choices.split(',')]
                
                # Validate all indices
                if all(1 <= idx <= len(all_files) for idx in selected_indices):
                    files_to_process = [all_files[idx - 1] for idx in selected_indices]
                    mode = 'individual_files'
                    input_path = selected_folder
                    break
                else:
                    click.echo(f"❌ Please enter numbers between 1 and {len(all_files)}")
            except click.Abort:
                raise
            except:
                click.echo("❌ Please enter valid numbers separated by commas")
    
    click.echo(f'📚 Starting chapter generation...')
    click.echo(f'📄 Mode: {mode}')
    click.echo(f'📁 Input: {input_path.absolute()}')
    click.echo(f'📝 Files to process: {len(files_to_process)}')
    
    # Setup output directory
    base_path = Path(output_dir)
    if subfolder:
        output_path = base_path / subfolder
    else:
        # Use input directory name as subfolder
        output_path = base_path / input_path.name
    
    output_path.mkdir(parents=True, exist_ok=True)
    click.echo(f'📁 Output directory: {output_path.absolute()}')
    click.echo(f'⚡ Max workers: {max_workers}')
    click.echo('─' * 60)
    
    # Initialize chapter generator
    try:
        generator = ChapterGenerator()
        click.echo('✅ Chapter generator initialized')
    except Exception as e:
        click.echo(f"❌ Error initializing chapter generator: {e}", err=True)
        click.echo("Make sure ANTHROPIC_API_KEY is set in your .env file.")
        raise click.Abort()
    
    successful_chapters = 0
    failed_chapters = 0
    total_transcripts_processed = 0
    
    # Thread-safe lock for updating shared variables
    stats_lock = threading.Lock()
    
    def process_transcript_file(file_data):
        """Process a single transcript file: generate chapter."""
        idx, transcript_file = file_data
        
        # Check if chapter already exists
        chapter_filename = transcript_file.stem + '_chapter.md'
        chapter_file = output_path / chapter_filename
        
        if chapter_file.exists():
            return {
                'status': 'skipped',
                'file': transcript_file.name,
                'message': f'Chapter already exists: {chapter_filename}',
                'idx': idx
            }
        
        file_start_time = time.time()
        
        # Progress callback
        def progress_callback(message):
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] {message}')
        
        try:
            with stats_lock:
                click.echo(f'\n📖 [{idx}/{len(files_to_process)}] Processing: {transcript_file.name}')
                click.echo(f'    [{idx}/{len(files_to_process)}] 🤖 Generating chapter with Claude...')
            
            # Generate chapter
            custom_title = chapter_title if mode == 'individual_files' and len(files_to_process) == 1 else None
            chapter_content = generator.generate_chapter_from_file(
                transcript_file=transcript_file,
                output_file=chapter_file,
                chapter_title=custom_title
            )
            
            # Calculate stats
            word_count = len(chapter_content.split())
            line_count = len(chapter_content.split('\n'))
            
            file_time = time.time() - file_start_time
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] ✅ Chapter saved to {chapter_filename}')
                click.echo(f'    [{idx}/{len(files_to_process)}] ⏱️  Completed in {file_time:.1f}s ({word_count} words, {line_count} lines)')
            
            return {
                'status': 'success',
                'file': transcript_file.name,
                'chapter_file': chapter_filename,
                'word_count': word_count,
                'line_count': line_count,
                'processing_time': file_time,
                'idx': idx
            }
            
        except Exception as e:
            with stats_lock:
                click.echo(f"    [{idx}/{len(files_to_process)}] ❌ Error processing {transcript_file.name}: {e}", err=True)
            return {
                'status': 'failed',
                'file': transcript_file.name,
                'error': str(e),
                'idx': idx
            }
    
    click.echo('─' * 60)
    click.echo(f'🚀 Starting chapter generation with {max_workers} workers...')
    
    # Filter out already processed files
    files_to_process_filtered = []
    for idx, transcript_file in enumerate(files_to_process, 1):
        chapter_filename = transcript_file.stem + '_chapter.md'
        chapter_file = output_path / chapter_filename
        if not chapter_file.exists():
            files_to_process_filtered.append((idx, transcript_file))
        else:
            click.echo(f'⏭️  [{idx}/{len(files_to_process)}] Skipping - chapter already exists: {chapter_filename}')
    
    if not files_to_process_filtered:
        click.echo("✅ All chapters already generated!")
    else:
        click.echo(f'📊 Processing {len(files_to_process_filtered)} files...')
        
        # Process files in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_file = {executor.submit(process_transcript_file, file_data): file_data for file_data in files_to_process_filtered}
            
            # Process completed jobs as they finish
            for future in as_completed(future_to_file):
                result = future.result()
                
                if result['status'] == 'success':
                    with stats_lock:
                        successful_chapters += 1
                        total_transcripts_processed += 1
                elif result['status'] == 'failed':
                    with stats_lock:
                        failed_chapters += 1
                        total_transcripts_processed += 1
    
    # Final summary
    total_time = time.time() - start_time
    click.echo('═' * 60)
    click.echo('📊 CHAPTER GENERATION SUMMARY')
    click.echo('═' * 60)
    click.echo(f'✅ Successful chapters: {successful_chapters}/{len(files_to_process)}')
    if failed_chapters > 0:
        click.echo(f'❌ Failed chapters: {failed_chapters}/{len(files_to_process)}')
    click.echo(f'📝 Total files processed: {total_transcripts_processed}')
    click.echo(f'⏱️  Total processing time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
    if successful_chapters > 0:
        click.echo(f'⚡ Average time per chapter: {total_time/successful_chapters:.1f}s')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! Happy learning! 🎓')

@cli.command('create-quiz')
@click.option('--output-dir', '-d', type=click.Path(), default='outputs/quizz',
              help='Directory to save quiz files.')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within quizz directory.')
@click.option('--max-workers', '-w', type=int, default=2,
              help='Maximum number of parallel workers for quiz generation.')
def create_quiz(output_dir: str, subfolder: str, max_workers: int) -> None:
    """
    Create quiz questions from chapter markdown files.
    
    Automatically detects chapters in outputs/chapters/ and creates quiz questions.
    """
    start_time = time.time()
    
    # Check if outputs/chapters directory exists
    chapters_base = Path('outputs/chapters')
    if not chapters_base.exists():
        click.echo("❌ No chapters directory found at outputs/chapters")
        click.echo("Run create-chapters first to generate chapters.")
        raise click.Abort()
    
    # Get all subfolders in outputs/chapters
    subfolders = [f for f in chapters_base.iterdir() if f.is_dir()]
    if not subfolders:
        click.echo("❌ No subfolders found in outputs/chapters")
        raise click.Abort()
    
    # Display available subfolders
    click.echo("📁 Available chapter subfolders:")
    for idx, folder in enumerate(subfolders, 1):
        md_files = list(folder.glob('*_chapter.md'))
        click.echo(f"  {idx}. {folder.name} ({len(md_files)} chapter files)")
    
    # Get user selection for subfolder
    while True:
        try:
            choice = click.prompt("\nSelect subfolder number", type=int)
            if 1 <= choice <= len(subfolders):
                selected_folder = subfolders[choice - 1]
                break
            else:
                click.echo(f"❌ Please enter a number between 1 and {len(subfolders)}")
        except click.Abort:
            raise
        except:
            click.echo("❌ Please enter a valid number")
    
    # Get all chapter files in selected folder
    all_files = list(selected_folder.glob('*_chapter.md'))
    if not all_files:
        click.echo(f"❌ No chapter files found in {selected_folder.name}")
        raise click.Abort()
    
    # Ask user to choose between whole subfolder or individual files
    click.echo(f"\n📄 Found {len(all_files)} chapter files in '{selected_folder.name}'")
    click.echo("1. Process all chapter files")
    click.echo("2. Select individual files")
    
    while True:
        try:
            process_choice = click.prompt("Choose option", type=int)
            if process_choice in [1, 2]:
                break
            else:
                click.echo("❌ Please enter 1 or 2")
        except click.Abort:
            raise
        except:
            click.echo("❌ Please enter a valid number")
    
    if process_choice == 1:
        # Process all files
        mode = 'directory'
        files_to_process = all_files
        input_path = selected_folder
    else:
        # Let user select individual files
        click.echo(f"\n📋 Chapter files in '{selected_folder.name}':")
        for idx, file in enumerate(all_files, 1):
            click.echo(f"  {idx}. {file.name}")
        
        click.echo("\nEnter file numbers to process (comma-separated, e.g., 1,3,5):")
        while True:
            try:
                file_choices = click.prompt("File numbers").strip()
                selected_indices = [int(x.strip()) for x in file_choices.split(',')]
                
                # Validate all indices
                if all(1 <= idx <= len(all_files) for idx in selected_indices):
                    files_to_process = [all_files[idx - 1] for idx in selected_indices]
                    mode = 'individual_files'
                    input_path = selected_folder
                    break
                else:
                    click.echo(f"❌ Please enter numbers between 1 and {len(all_files)}")
            except click.Abort:
                raise
            except:
                click.echo("❌ Please enter valid numbers separated by commas")
    
    click.echo(f'🧠 Starting quiz generation...')
    click.echo(f'📄 Mode: {mode}')
    click.echo(f'📁 Input: {input_path.absolute()}')
    click.echo(f'📝 Files to process: {len(files_to_process)}')
    
    # Setup output directory
    base_path = Path(output_dir)
    if subfolder:
        output_path = base_path / subfolder
    else:
        # Use input directory name as subfolder
        output_path = base_path / input_path.name
    
    output_path.mkdir(parents=True, exist_ok=True)
    click.echo(f'📁 Output directory: {output_path.absolute()}')
    click.echo(f'⚡ Max workers: {max_workers}')
    click.echo('─' * 60)
    
    # Initialize quiz generator
    try:
        generator = QuizGenerator()
        click.echo('✅ Quiz generator initialized')
    except Exception as e:
        click.echo(f"❌ Error initializing quiz generator: {e}", err=True)
        click.echo("Make sure ANTHROPIC_API_KEY is set in your .env file.")
        raise click.Abort()
    
    successful_quizzes = 0
    failed_quizzes = 0
    total_chapters_processed = 0
    
    # Thread-safe lock for updating shared variables
    stats_lock = threading.Lock()
    
    def process_chapter_file(file_data):
        """Process a single chapter file: generate quiz."""
        idx, chapter_file = file_data
        
        # Generate quiz number based on existing files
        existing_quizzes = [d for d in output_path.iterdir() if d.is_dir() and d.name.isdigit()]
        quiz_number = f"{len(existing_quizzes) + 1:03d}"
        
        # Check if quiz already exists for this chapter
        quiz_dir = output_path / quiz_number
        if quiz_dir.exists():
            return {
                'status': 'skipped',
                'file': chapter_file.name,
                'message': f'Quiz directory already exists: {quiz_number}',
                'idx': idx
            }
        
        file_start_time = time.time()
        
        # Progress callback
        def progress_callback(message):
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] {message}')
        
        try:
            with stats_lock:
                click.echo(f'\n🧠 [{idx}/{len(files_to_process)}] Processing: {chapter_file.name}')
                click.echo(f'    [{idx}/{len(files_to_process)}] 🤖 Generating quiz with Claude...')
            
            # Generate quiz
            quiz_data = generator.generate_quiz_from_file(chapter_file)
            
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] 📝 Generated quiz question')
                click.echo(f'    [{idx}/{len(files_to_process)}] ❓ Question: {quiz_data["question"][:60]}...')
            
            # Interactive validation
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] 🔍 Starting interactive validation...')
                
            # Note: This will pause parallel processing for validation
            validated_quiz = generator.validate_quiz_interactively(quiz_data)
            
            # Save quiz files
            generator.save_quiz_files(validated_quiz, output_path, quiz_number)
            
            file_time = time.time() - file_start_time
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] ✅ Quiz saved as {quiz_number}')
                click.echo(f'    [{idx}/{len(files_to_process)}] ⏱️  Completed in {file_time:.1f}s')
            
            return {
                'status': 'success',
                'file': chapter_file.name,
                'quiz_number': quiz_number,
                'processing_time': file_time,
                'idx': idx
            }
            
        except Exception as e:
            with stats_lock:
                click.echo(f"    [{idx}/{len(files_to_process)}] ❌ Error processing {chapter_file.name}: {e}", err=True)
            return {
                'status': 'failed',
                'file': chapter_file.name,
                'error': str(e),
                'idx': idx
            }
    
    click.echo('─' * 60)
    click.echo(f'🚀 Starting quiz generation...')
    
    # Note: Due to interactive validation, we process files sequentially
    for idx, chapter_file in enumerate(files_to_process, 1):
        result = process_chapter_file((idx, chapter_file))
        
        if result['status'] == 'success':
            successful_quizzes += 1
            total_chapters_processed += 1
        elif result['status'] == 'failed':
            failed_quizzes += 1
            total_chapters_processed += 1
    
    # Final summary
    total_time = time.time() - start_time
    click.echo('═' * 60)
    click.echo('📊 QUIZ GENERATION SUMMARY')
    click.echo('═' * 60)
    click.echo(f'✅ Successful quizzes: {successful_quizzes}/{len(files_to_process)}')
    if failed_quizzes > 0:
        click.echo(f'❌ Failed quizzes: {failed_quizzes}/{len(files_to_process)}')
    click.echo(f'📝 Total chapters processed: {total_chapters_processed}')
    click.echo(f'⏱️  Total processing time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
    if successful_quizzes > 0:
        click.echo(f'⚡ Average time per quiz: {total_time/successful_quizzes:.1f}s')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! Happy quizzing! 🧠')

