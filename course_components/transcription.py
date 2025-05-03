from pathlib import Path
from typing import Union
import openai

class TranscriptionService:
    """
    Service for transcribing audio files using OpenAI's Whisper API.
    """
    def __init__(self, model: str = "whisper-1", api_key: str = None) -> None:
        """
        Initializes the transcription service.

        Args:
            model: OpenAI Whisper model identifier.
            api_key: OpenAI API key; if not provided, reads from environment.
        """
        self.model = model
        if api_key:
            openai.api_key = api_key

    def transcribe(self, audio_file: Union[str, Path]) -> str:
        """
        Transcribes the given audio file to text.

        Args:
            audio_file: Path to the audio file.

        Returns:
            Transcribed text.

        Raises:
            ValueError: If the file does not exist.
            RuntimeError: If the transcription request fails.
        """
        audio_path = Path(audio_file)
        if not audio_path.exists():
            raise ValueError(f"Audio file not found: {audio_file}")

        try:
            with open(audio_path, "rb") as f:
                response = openai.Audio.transcribe(self.model, f)
        except Exception as e:
            raise RuntimeError(f"Transcription failed: {e}") from e

        # Extract transcript text
        text = response.get("text")
        if text is None:
            raise RuntimeError("No 'text' field in transcription response")
        return text