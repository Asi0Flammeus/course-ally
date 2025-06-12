from pathlib import Path
from typing import Union
from openai import OpenAI
from dotenv import load_dotenv
import os

class TranscriptionService:
    """
    Service for transcribing audio files using OpenAI's Whisper API.
    """
    def __init__(self, model: str = "whisper-1") -> None:
        """
        Initializes the transcription service.

        Args:
            model: OpenAI Whisper model identifier.
        """
        # Load environment variables
        load_dotenv()
        
        # Get API key from environment variables
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.model = model
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, audio_file: Union[str, Path], progress_callback=None) -> str:
        """
        Transcribes the given audio file to text.

        Args:
            audio_file: Path to the audio file.
            progress_callback: Optional callback function for progress updates.

        Returns:
            Transcribed text.

        Raises:
            ValueError: If the file does not exist.
            RuntimeError: If the transcription request fails.
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_file}")

        # Get file size for progress indication
        file_size = audio_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        if progress_callback:
            progress_callback(f"    Preparing audio file ({file_size_mb:.1f} MB) for transcription...")

        try:
            if progress_callback:
                progress_callback(f"    Uploading to OpenAI Whisper API...")
            
            with open(audio_path, "rb") as audio:
                if progress_callback:
                    progress_callback(f"    Processing transcription (this may take a few minutes)...")
                
                response = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio
                )
                
            if progress_callback:
                transcript_length = len(response.text)
                word_count = len(response.text.split())
                progress_callback(f"    Transcription completed ({word_count} words, {transcript_length} characters)")
                
        except Exception as e:
            if progress_callback:
                progress_callback(f"    Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {e}") from e

        return response.text

