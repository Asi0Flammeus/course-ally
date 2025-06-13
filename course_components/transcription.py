from pathlib import Path
from typing import Union, List
from openai import OpenAI
from dotenv import load_dotenv
import os
import tempfile
import subprocess
import math

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
        file_size = audio_file.stat().st_size
        duration = self._get_audio_duration(audio_file)
        
        # Calculate number of chunks needed
        num_chunks = math.ceil(file_size / self.max_file_size_bytes)
        chunk_duration = duration / num_chunks
        
        if progress_callback:
            progress_callback(f"    Splitting audio into {num_chunks} chunks (~{chunk_duration:.1f}s each)...")
        
        chunk_files = []
        for i in range(num_chunks):
            start_time = i * chunk_duration
            chunk_file = temp_dir / f"chunk_{i:03d}.mp3"
            
            # Use ffmpeg to extract chunk
            cmd = [
                'ffmpeg', '-i', str(audio_file),
                '-ss', str(start_time),
                '-t', str(chunk_duration),
                '-acodec', 'copy',
                '-y', str(chunk_file)
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                chunk_files.append(chunk_file)
                
                if progress_callback:
                    progress_callback(f"    Created chunk {i+1}/{num_chunks}")
                    
            except FileNotFoundError:
                raise RuntimeError("ffmpeg not found. Please install ffmpeg to enable audio chunking for large files.")
            except subprocess.CalledProcessError as e:
                raise RuntimeError(f"Failed to create chunk {i+1}: {e}")
        
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
            progress_callback(f"    Preparing audio file ({file_size_mb:.1f} MB) for transcription...")

        # Check if file needs chunking
        if file_size <= self.max_file_size_bytes:
            # File is small enough, transcribe directly
            if progress_callback:
                progress_callback(f"    File size OK ({file_size_mb:.1f} MB ≤ {self.max_file_size_mb} MB), transcribing directly...")
            
            try:
                if progress_callback:
                    progress_callback(f"    Uploading to OpenAI Whisper API...")
                
                transcript = self._transcribe_single_file(audio_path, progress_callback)
                
                if progress_callback:
                    word_count = len(transcript.split())
                    progress_callback(f"    Transcription completed ({word_count} words, {len(transcript)} characters)")
                
                return transcript
                
            except Exception as e:
                if progress_callback:
                    progress_callback(f"    Transcription failed: {str(e)}")
                raise RuntimeError(f"Transcription failed: {e}") from e
        
        else:
            # File is too large, need to chunk it
            if progress_callback:
                progress_callback(f"    File too large ({file_size_mb:.1f} MB > {self.max_file_size_mb} MB), chunking required...")
            
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    
                    # Split audio into chunks
                    chunk_files = self._split_audio_into_chunks(audio_path, temp_path, progress_callback)
                    
                    # Transcribe each chunk
                    transcripts = []
                    total_words = 0
                    
                    if progress_callback:
                        progress_callback(f"    Transcribing {len(chunk_files)} chunks...")
                    
                    for i, chunk_file in enumerate(chunk_files, 1):
                        if progress_callback:
                            progress_callback(f"    Processing chunk {i}/{len(chunk_files)}...")
                        
                        chunk_transcript = self._transcribe_single_file(chunk_file, progress_callback)
                        transcripts.append(chunk_transcript)
                        
                        chunk_words = len(chunk_transcript.split())
                        total_words += chunk_words
                        
                        if progress_callback:
                            progress_callback(f"    Chunk {i}/{len(chunk_files)} completed ({chunk_words} words)")
                    
                    # Combine all transcripts
                    full_transcript = " ".join(transcripts)
                    
                    if progress_callback:
                        progress_callback(f"    All chunks transcribed and combined ({total_words} words, {len(full_transcript)} characters)")
                    
                    return full_transcript
                    
            except Exception as e:
                if progress_callback:
                    progress_callback(f"    Chunked transcription failed: {str(e)}")
                raise RuntimeError(f"Chunked transcription failed: {e}") from e

