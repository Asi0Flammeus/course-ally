from pathlib import Path
from typing import Union, List
from openai import OpenAI
from dotenv import load_dotenv
import os
import tempfile
import subprocess
import math
import re

class TranscriptionService:
    """
    Service for transcribing audio files using OpenAI's Whisper API.
    Automatically chunks files larger than 25MB for processing.
    """
    def __init__(self, model: str = "whisper-1", max_file_size_mb: int = 25) -> None:
        """
        Initializes the transcription service.

        Args:
            model: OpenAI Whisper model identifier.
            max_file_size_mb: Maximum file size in MB before chunking (default: 25).
        """
        # Load environment variables
        load_dotenv()
        
        # Get API key from environment variables
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.model = model
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.client = OpenAI(api_key=api_key)

    def _get_audio_duration(self, audio_file: Path) -> float:
        """Get audio duration in seconds using ffprobe."""
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', str(audio_file)
            ], capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except FileNotFoundError:
            raise RuntimeError("ffprobe not found. Please install ffmpeg to enable audio chunking for large files.")
        except (subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"Failed to get audio duration: {e}")

    def _split_audio_into_chunks(self, audio_file: Path, temp_dir: Path, progress_callback=None) -> List[Path]:
        """Split audio file into chunks that are under the size limit."""
        duration = self._get_audio_duration(audio_file)

        # Calculate max chunk duration based on target bitrate (128 kbps)
        # 128 kbps = 16 KB/s, with 80% safety margin for 25 MB limit
        target_size_mb = self.max_file_size_mb * 0.8  # 20 MB target
        bitrate_kbps = 128
        max_chunk_duration = (target_size_mb * 1024 * 8) / bitrate_kbps  # seconds

        # Calculate number of chunks needed
        num_chunks = math.ceil(duration / max_chunk_duration)
        chunk_duration = duration / num_chunks
        
        if progress_callback:
            progress_callback(f"Splitting audio into {num_chunks} chunks (~{chunk_duration:.1f}s each)...")

        chunk_files = []
        for i in range(num_chunks):
            start_time = i * chunk_duration
            # Always use .mp3 for chunks since we're re-encoding
            chunk_file = temp_dir / f"chunk_{i:03d}.mp3"

            # Use ffmpeg to extract chunk with re-encoding for compatibility
            # We re-encode to ensure compatibility across all formats
            cmd = [
                'ffmpeg', '-i', str(audio_file),
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-acodec', 'libmp3lame',  # Re-encode to mp3 for universal compatibility
                '-ab', '128k',  # Reasonable bitrate for transcription
                '-ar', '16000',  # Whisper API works well with 16kHz
                '-ac', '1',  # Mono audio for smaller size
                '-y', str(chunk_file)
            ]

            try:
                subprocess.run(cmd, capture_output=True, check=True, text=True)

                # Verify chunk size is under limit
                chunk_size = chunk_file.stat().st_size
                if chunk_size > self.max_file_size_bytes:
                    raise RuntimeError(
                        f"Chunk {i+1} is {chunk_size / (1024 * 1024):.1f} MB, "
                        f"exceeds {self.max_file_size_mb} MB limit. Try reducing audio quality further."
                    )

                chunk_files.append(chunk_file)

                if progress_callback:
                    progress_callback(f"Created chunk {i+1}/{num_chunks} ({chunk_size / (1024 * 1024):.1f} MB)")

            except FileNotFoundError:
                raise RuntimeError("ffmpeg not found. Please install ffmpeg to enable audio chunking for large files.")
            except subprocess.CalledProcessError as e:
                # Provide more detailed error information
                error_msg = f"Failed to create chunk {i+1}"
                if e.stderr:
                    error_msg += f": {e.stderr}"
                raise RuntimeError(error_msg)
        
        return chunk_files

    def _transcribe_single_file(self, audio_file: Path, progress_callback=None) -> str:
        """Transcribe a single audio file."""
        try:
            with open(audio_file, "rb") as audio:
                response = self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio
                )
                return response.text
        except Exception as e:
            raise RuntimeError(f"Transcription failed for {audio_file.name}: {e}")

    def _format_transcript(self, transcript: str) -> str:
        """
        Format transcript with one sentence per line for better readability.
        
        Args:
            transcript: Raw transcript text
            
        Returns:
            Formatted transcript with sentences on separate lines
        """
        if not transcript or not transcript.strip():
            return transcript
        
        # Clean up the transcript
        text = transcript.strip()
        
        # First, try to split on sentence boundaries with proper punctuation
        # This pattern matches sentence-ending punctuation followed by whitespace and a capital letter
        sentence_endings = r'([.!?]+)\s+(?=[A-Z])'
        
        # Split and keep the delimiters
        parts = re.split(sentence_endings, text)
        
        sentences = []
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and re.match(r'^[.!?]+$', parts[i + 1]):
                # Current part + punctuation
                sentence = parts[i] + parts[i + 1]
                i += 2
            else:
                sentence = parts[i]
                i += 1
            
            sentence = sentence.strip()
            if sentence:
                sentences.append(sentence)
        
        # If we didn't get good sentence breaks, try simpler approaches
        if len(sentences) <= 1:
            # Fall back to splitting on periods followed by space
            if '. ' in text:
                parts = text.split('. ')
                sentences = []
                for i, part in enumerate(parts):
                    part = part.strip()
                    if part:
                        # Add period back except for the last part (which may already have ending punctuation)
                        if i < len(parts) - 1 and not part.endswith(('.', '!', '?')):
                            part += '.'
                        sentences.append(part)
            else:
                # If no good sentence breaks, keep as single block but clean it up
                sentences = [text]
        
        # Clean up sentences and remove empty ones
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and len(sentence) > 1:  # Avoid single character lines
                cleaned_sentences.append(sentence)
        
        # Join sentences with newlines
        return '\n'.join(cleaned_sentences) if cleaned_sentences else text

    def transcribe(self, audio_file: Union[str, Path], progress_callback=None) -> str:
        """
        Transcribes the given audio file to text.
        Automatically chunks files larger than the size limit.

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
            progress_callback(f"Preparing audio file ({file_size_mb:.1f} MB) for transcription...")

        # Check if file needs chunking
        if file_size <= self.max_file_size_bytes:
            # File is small enough, transcribe directly
            if progress_callback:
                progress_callback(f"File size OK ({file_size_mb:.1f} MB ≤ {self.max_file_size_mb} MB), transcribing directly...")

            try:
                if progress_callback:
                    progress_callback(f"Uploading to OpenAI Whisper API...")

                transcript = self._transcribe_single_file(audio_path, progress_callback)

                # Format transcript for better readability
                formatted_transcript = self._format_transcript(transcript)

                if progress_callback:
                    word_count = len(transcript.split())
                    sentence_count = len(formatted_transcript.split('\n'))
                    progress_callback(f"Transcription completed ({word_count} words, {sentence_count} sentences)")
                
                return formatted_transcript
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Transcription failed: {str(e)}")
                raise RuntimeError(f"Transcription failed: {e}") from e

        else:
            # File is too large, need to chunk it
            if progress_callback:
                progress_callback(f"File too large ({file_size_mb:.1f} MB > {self.max_file_size_mb} MB), chunking required...")

            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)

                    # Split audio into chunks
                    chunk_files = self._split_audio_into_chunks(audio_path, temp_path, progress_callback)

                    # Transcribe each chunk
                    transcripts = []
                    total_words = 0

                    if progress_callback:
                        progress_callback(f"Transcribing {len(chunk_files)} chunks...")

                    for i, chunk_file in enumerate(chunk_files, 1):
                        if progress_callback:
                            progress_callback(f"Uploading chunk {i}/{len(chunk_files)} to OpenAI...")

                        chunk_transcript = self._transcribe_single_file(chunk_file, progress_callback)
                        transcripts.append(chunk_transcript)

                        chunk_words = len(chunk_transcript.split())
                        total_words += chunk_words

                        if progress_callback:
                            progress_callback(f"Chunk {i}/{len(chunk_files)} completed ({chunk_words} words)")

                    # Combine all transcripts with spaces between chunks
                    full_transcript = " ".join(transcripts)

                    # Format the combined transcript for better readability
                    formatted_transcript = self._format_transcript(full_transcript)

                    if progress_callback:
                        sentence_count = len(formatted_transcript.split('\n'))
                        progress_callback(f"All chunks transcribed and combined ({total_words} words, {sentence_count} sentences)")

                    return formatted_transcript

            except Exception as e:
                if progress_callback:
                    progress_callback(f"Chunked transcription failed: {str(e)}")
                raise RuntimeError(f"Chunked transcription failed: {e}") from e

