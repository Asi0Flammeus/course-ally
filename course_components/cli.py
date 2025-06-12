import click
import tempfile
import json
import time
from pathlib import Path

from course_components.downloader import YouTubeDownloader
from course_components.transcription import TranscriptionService
from course_components.lecture import LectureGenerator

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
@click.argument('playlist_url')
@click.option('--output-dir', '-d', type=click.Path(), default='transcripts',
              help='Directory to save transcript files.')
@click.option('--subfolder', '-s', type=str, default=None,
              help='Optional subfolder name within transcripts directory.')
@click.option('--format', '-f', type=click.Choice(['txt', 'json']), default='txt',
              help='Output format for transcripts.')
def extract_playlist_transcripts(playlist_url: str, output_dir: str, subfolder: str, format: str) -> None:
    """
    Extract transcripts from all videos in a YouTube playlist.

    PLAYLIST_URL is the YouTube playlist URL.
    """
    start_time = time.time()
    
    downloader = YouTubeDownloader()
    transcription_service = TranscriptionService()
    
    # Always use transcripts as base directory
    base_path = Path('transcripts')
    if subfolder:
        output_path = base_path / subfolder
    else:
        output_path = base_path
    output_path.mkdir(parents=True, exist_ok=True)
    
    click.echo('🎬 Starting playlist transcript extraction...')
    click.echo(f'📁 Output directory: {output_path.absolute()}')
    click.echo(f'📋 Output format: {format}')
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
    
    # Progress callback for individual video processing
    def video_progress(message):
        click.echo(message)
    
    click.echo('─' * 60)
    
    # Process videos individually: download → convert → transcribe → cleanup
    for idx, video_id in enumerate(video_ids, 1):
        click.echo(f'\n🎥 [{idx}/{len(video_ids)}] Processing video ID: {video_id}')
        
        # Check if video is already transcribed
        existing_files = list(output_path.glob(f"*{video_id}*"))
        if existing_files:
            click.echo(f'    ⏭️  Skipping - already transcribed: {existing_files[0].name}')
            continue
        
        video_start_time = time.time()
        
        # Use individual temp directory for each video
        with tempfile.TemporaryDirectory() as video_tmpdir:
            try:
                # Download and convert audio for this video only
                click.echo('    🔽 Downloading and converting audio...')
                audio_path = downloader.download_audio(video_id, video_tmpdir, progress_callback=video_progress)
                
                # Transcribe audio immediately
                click.echo('    🎤 Transcribing audio...')
                transcript = transcription_service.transcribe(audio_path, progress_callback=video_progress)
                
                # Calculate stats
                word_count = len(transcript.split())
                char_count = len(transcript)
                total_words += word_count
                total_characters += char_count
                
                # Save transcript (simplified filename since we don't have title)
                filename = f"{idx:02d}_video_{video_id}"
                
                if format == 'txt':
                    transcript_file = output_path / f"{filename}.txt"
                    
                    # Add metadata header to txt files
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    metadata_header = f"""# Video Transcript
Video ID: {video_id}
URL: {video_url}
Transcribed: {time.strftime('%Y-%m-%d %H:%M:%S')}
Words: {word_count} | Characters: {char_count}

{'='*60}

"""
                    
                    transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                    click.echo(f'    ✅ Transcript saved to {transcript_file.name}')
                else:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    transcripts_data.append({
                        'video_id': video_id,
                        'url': video_url,
                        'transcript': transcript,
                        'word_count': word_count,
                        'character_count': char_count,
                        'transcribed_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    })
                
                successful_transcripts += 1
                video_time = time.time() - video_start_time
                click.echo(f'    ⏱️  Completed in {video_time:.1f}s ({word_count} words)')
                click.echo(f'    🗑️  Audio file cleaned up automatically')
                
            except Exception as e:
                failed_transcripts += 1
                click.echo(f"    ❌ Error processing video {video_id}: {e}", err=True)
                click.echo(f"    ⏭️  Continuing with next video...")
                continue
    
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

