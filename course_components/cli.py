import click
import tempfile
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
@click.option('--api-key', envvar='OPENAI_API_KEY', default=None,
              help='OpenAI API key or set via OPENAI_API_KEY environment variable.')
def create_lecture(video_id: str, output: str, sections: int, api_key: str) -> None:
    """
    Create a lecture markdown from a YouTube video ID.

    VIDEO_ID is the YouTube video identifier (e.g., dQw4w9WgXcQ).
    """
    downloader = YouTubeDownloader()
    transcription_service = TranscriptionService(api_key=api_key)
    with tempfile.TemporaryDirectory() as tmpdir:
        # Download audio
        click.echo('Downloading audio from YouTube...')
        try:
            audio_path = downloader.download_audio(video_id, tmpdir)
            click.echo(f'Audio downloaded to {audio_path}')
        except Exception as e:
            click.echo(f"Error downloading audio: {e}", err=True)
            raise click.Abort()

        # Transcribe audio
        click.echo('Transcribing audio...')
        try:
            transcript = transcription_service.transcribe(audio_path)
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