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

@cli.command('playlist-to-md')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within playlist_to_md directory.')
def playlist_to_md(subfolder: str) -> None:
    """
    Convert YouTube playlist to markdown file.
    
    Prompts for YouTube playlist URL or ID and creates a markdown file
    with video titles and links.
    """
    # Get playlist URL or ID from user
    click.echo('📺 YouTube Playlist to Markdown Converter')
    click.echo('─' * 60)
    playlist_input = click.prompt('Enter YouTube playlist URL or ID')
    
    # Detect if it's a URL or just an ID
    if playlist_input.startswith('http'):
        playlist_url = playlist_input
    else:
        # Assume it's a playlist ID
        playlist_url = f"https://www.youtube.com/playlist?list={playlist_input}"
    
    start_time = time.time()
    
    downloader = YouTubeDownloader()
    
    # Set up output directory structure
    base_path = Path('outputs') / 'playlist_to_md'
    if subfolder:
        output_path = base_path / subfolder
    else:
        output_path = base_path
    output_path.mkdir(parents=True, exist_ok=True)
    
    click.echo(f'🔗 Starting playlist extraction...')
    click.echo(f'📁 Output directory: {output_path.absolute()}')
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
        ydl_opts = {
            'quiet': True, 
            'extract_flat': True, 
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'extractor_retries': 3,
            'ignoreerrors': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            playlist_title = playlist_info.get('title', 'Unknown Playlist')
            playlist_uploader = playlist_info.get('uploader', 'Unknown Channel')
    except:
        playlist_title = 'YouTube Playlist'
        playlist_uploader = 'Unknown Channel'
    
    # Create markdown content following the template
    md_content = ""
    
    # Add video entries
    for video in videos:
        video_id = video['id']
        video_title = video['title']
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        md_content += f"## {video_title}\n"
        md_content += f"![video]({video_url})\n\n"
    
    # Save markdown file
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    # Create a safe filename from playlist title
    safe_title = "".join(c for c in playlist_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title.replace(' ', '_')[:50]  # Limit length
    filename = f"{safe_title}_{timestamp}.md"
    md_file = output_path / filename
    
    md_file.write_text(md_content, encoding='utf-8')
    
    # Final summary
    extraction_time = time.time() - start_time
    click.echo('═' * 60)
    click.echo('📊 EXTRACTION SUMMARY')
    click.echo('═' * 60)
    click.echo(f'📺 Playlist: {playlist_title}')
    click.echo(f'👤 Channel: {playlist_uploader}')
    click.echo(f'🎬 Total videos: {len(videos)}')
    click.echo(f'⏱️  Processing time: {extraction_time:.1f}s')
    click.echo(f'📄 Markdown file: {md_file}')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! 📋')

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
    
    # Get all txt files in selected folder and sort alphabetically
    all_files = sorted(selected_folder.glob('*.txt'), key=lambda x: x.name.lower())
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
    
    # Get all chapter files in selected folder and sort them alphabetically
    all_files = sorted(list(selected_folder.glob('*_chapter.md')), key=lambda x: x.name)
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
        
        # Collect author and contributor metadata
        generator.collect_metadata()
        
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
        
        # Get existing quiz count for information
        existing_quizzes = [d for d in output_path.iterdir() if d.is_dir() and d.name.isdigit()]
        existing_count = len(existing_quizzes)
        
        file_start_time = time.time()
        
        # Progress callback
        def progress_callback(message):
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] {message}')
        
        try:
            with stats_lock:
                click.echo(f'\n🧠 [{idx}/{len(files_to_process)}] Processing: {chapter_file.name}')
                click.echo(f'    [{idx}/{len(files_to_process)}] 📊 Found {existing_count} existing quizzes')
                click.echo(f'    [{idx}/{len(files_to_process)}] 🤖 Generating quiz with Claude...')
            
            # Generate quizzes (12 total: 4 easy, 4 intermediate, 4 hard) with incremental saving
            all_quizzes = generator.generate_quizzes_from_file(chapter_file, quizz_output_path=output_path)
            
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] 📝 Generated {len(all_quizzes)} quiz questions')
                click.echo(f'    [{idx}/{len(files_to_process)}] 🎯 Difficulties: 4 easy, 4 intermediate, 4 hard')
                if existing_count > 0:
                    click.echo(f'    [{idx}/{len(files_to_process)}] 📈 Will be numbered starting from {existing_count + 1:03d}')
            
            # Interactive validation for each quiz (questions already saved incrementally)
            validated_quizzes = []
            for quiz_idx, quiz_data in enumerate(all_quizzes, 1):
                with stats_lock:
                    click.echo(f'    [{idx}/{len(files_to_process)}] 🔍 Validating question {quiz_idx}/{len(all_quizzes)} ({quiz_data["difficulty"]})')
                    
                # Note: This will pause parallel processing for validation
                validated_quiz = generator.validate_quiz_interactively(quiz_data)
                validated_quizzes.append(validated_quiz)
            
            # No need to save again - questions were saved incrementally during generation
            
            file_time = time.time() - file_start_time
            with stats_lock:
                click.echo(f'    [{idx}/{len(files_to_process)}] ✅ All {len(validated_quizzes)} quizzes saved')
                click.echo(f'    [{idx}/{len(files_to_process)}] ⏱️  Completed in {file_time:.1f}s')
            
            return {
                'status': 'success',
                'file': chapter_file.name,
                'quiz_count': len(validated_quizzes),
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
    click.echo(f'✅ Successful chapters: {successful_quizzes}/{len(files_to_process)}')
    click.echo(f'🧠 Total questions generated: {successful_quizzes * 12}')
    click.echo(f'🎯 Per chapter: 4 easy + 4 intermediate + 4 hard')
    if failed_quizzes > 0:
        click.echo(f'❌ Failed chapters: {failed_quizzes}/{len(files_to_process)}')
    click.echo(f'📝 Total chapters processed: {total_chapters_processed}')
    click.echo(f'⏱️  Total processing time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
    if successful_quizzes > 0:
        click.echo(f'⚡ Average time per chapter: {total_time/successful_quizzes:.1f}s')
    click.echo(f'📁 Output location: {output_path.absolute()}')
    click.echo(f'✨ All done! Happy quizzing! 🧠')

