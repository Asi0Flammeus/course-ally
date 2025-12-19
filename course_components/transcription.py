from pathlib import Path
from typing import Union, List, Optional, Tuple
from dataclasses import dataclass, field
from openai import OpenAI
from dotenv import load_dotenv
import os
import tempfile
import subprocess
import math
import re


@dataclass
class TranscriptSegment:
    """A segment of transcript with timestamp information."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Segment text
    
    def format_timestamp(self) -> str:
        """Format start time as [HH:MM:SS]."""
        hours = int(self.start // 3600)
        minutes = int((self.start % 3600) // 60)
        seconds = int(self.start % 60)
        if hours > 0:
            return f"[{hours:02d}:{minutes:02d}:{seconds:02d}]"
        return f"[{minutes:02d}:{seconds:02d}]"


@dataclass 
class TranscriptionResult:
    """
    Result of a transcription with optional timestamp information.
    Implements __str__ for backward compatibility with code expecting str.
    """
    text: str                                           # Full transcript text
    segments: List[TranscriptSegment] = field(default_factory=list)  # Timestamped segments
    duration: Optional[float] = None                    # Total audio duration
    language: Optional[str] = None                      # Detected language
    
    def __str__(self) -> str:
        """Return plain text for backward compatibility."""
        return self.text
    
    def __len__(self) -> int:
        """Return length of text for compatibility."""
        return len(self.text)
    
    def split(self, sep: str = None) -> List[str]:
        """Split text for compatibility with str.split()."""
        return self.text.split(sep)
    
    def format_with_timestamps(self) -> str:
        """Format transcript with timestamps at the start of each segment."""
        if not self.segments:
            return self.text
        
        lines = []
        for segment in self.segments:
            timestamp = segment.format_timestamp()
            lines.append(f"{timestamp} {segment.text}")
        return '\n'.join(lines)

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

    def _split_audio_into_chunks(
        self, 
        audio_file: Path, 
        temp_dir: Path, 
        progress_callback=None,
        include_offsets: bool = False
    ) -> Union[List[Path], List[Tuple[Path, float]]]:
        """
        Split audio file into chunks that are under the size limit.
        
        Args:
            audio_file: Path to the audio file
            temp_dir: Temporary directory to store chunks
            progress_callback: Optional callback for progress updates
            include_offsets: If True, return tuples of (chunk_path, start_offset)
            
        Returns:
            If include_offsets is False: List of chunk file paths
            If include_offsets is True: List of (chunk_path, start_offset_seconds) tuples
        """
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

                # Include offset if requested (for timestamp adjustment)
                if include_offsets:
                    chunk_files.append((chunk_file, start_time))
                else:
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

    def _transcribe_single_file(
        self, 
        audio_file: Path, 
        progress_callback=None,
        include_timestamps: bool = False,
        time_offset: float = 0.0
    ) -> Union[str, Tuple[str, List[TranscriptSegment]]]:
        """
        Transcribe a single audio file.
        
        Args:
            audio_file: Path to the audio file
            progress_callback: Optional callback for progress updates
            include_timestamps: If True, return segments with timestamps
            time_offset: Offset to add to all timestamps (for chunked audio)
            
        Returns:
            If include_timestamps is False: transcript text (str)
            If include_timestamps is True: tuple of (text, list of TranscriptSegment)
        """
        try:
            with open(audio_file, "rb") as audio:
                if include_timestamps:
                    # Use verbose_json to get segment timestamps
                    response = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio,
                        response_format="verbose_json"
                    )
                    
                    # Extract segments with timestamps
                    segments = []
                    for seg in response.segments:
                        segment = TranscriptSegment(
                            start=seg.start + time_offset,
                            end=seg.end + time_offset,
                            text=seg.text.strip()
                        )
                        segments.append(segment)
                    
                    return response.text, segments
                else:
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

    def _format_transcript_with_timestamps(
        self, 
        segments: List[TranscriptSegment]
    ) -> Tuple[str, List[TranscriptSegment]]:
        """
        Format transcript into sentences while preserving timestamp alignment.
        
        Takes raw segments from Whisper and reformats text into sentences,
        assigning each sentence the timestamp of its starting segment.
        
        Args:
            segments: List of TranscriptSegment from Whisper API
            
        Returns:
            Tuple of (formatted text with sentences, list of sentence-aligned segments)
        """
        if not segments:
            return "", []
        
        # Combine all segment text
        full_text = " ".join(seg.text for seg in segments)
        
        # Format into sentences using existing logic
        formatted_text = self._format_transcript(full_text)
        sentences = formatted_text.split('\n')
        
        # Now we need to align each sentence with its timestamp
        # Strategy: Find where each sentence starts in the original segments
        sentence_segments = []
        
        # Build a character-to-timestamp mapping from segments
        char_timestamps = []  # List of (char_position, timestamp)
        current_pos = 0
        
        for seg in segments:
            # Record the start position and timestamp
            char_timestamps.append((current_pos, seg.start, seg.end))
            current_pos += len(seg.text) + 1  # +1 for space between segments
        
        # For each sentence, find its approximate start timestamp
        search_pos = 0
        combined_for_search = " ".join(seg.text for seg in segments)
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Find where this sentence starts in the combined text
            # Use a simplified search - find the first few words
            search_text = sentence[:min(50, len(sentence))].strip()
            
            # Find position in combined text
            found_pos = combined_for_search.find(search_text, search_pos)
            if found_pos == -1:
                # Fallback: try with less text
                search_text = sentence[:min(20, len(sentence))].strip()
                found_pos = combined_for_search.find(search_text, search_pos)
            
            if found_pos == -1:
                found_pos = search_pos  # Use current position as fallback
            
            # Find the timestamp for this position
            start_time = 0.0
            end_time = segments[-1].end if segments else 0.0
            
            for i, (char_pos, seg_start, seg_end) in enumerate(char_timestamps):
                if char_pos <= found_pos:
                    start_time = seg_start
                    # Find the end time from the segment where the sentence likely ends
                    sentence_end_pos = found_pos + len(sentence)
                    for j in range(i, len(char_timestamps)):
                        if j + 1 < len(char_timestamps):
                            if char_timestamps[j + 1][0] > sentence_end_pos:
                                end_time = char_timestamps[j][2]
                                break
                        else:
                            end_time = char_timestamps[j][2]
                else:
                    break
            
            sentence_segments.append(TranscriptSegment(
                start=start_time,
                end=end_time,
                text=sentence.strip()
            ))
            
            # Update search position to avoid matching same text again
            search_pos = found_pos + len(search_text)
        
        return formatted_text, sentence_segments

    def transcribe(
        self, 
        audio_file: Union[str, Path], 
        progress_callback=None,
        include_timestamps: bool = False
    ) -> Union[str, TranscriptionResult]:
        """
        Transcribes the given audio file to text.
        Automatically chunks files larger than the size limit.

        Args:
            audio_file: Path to the audio file.
            progress_callback: Optional callback function for progress updates.
            include_timestamps: If True, return TranscriptionResult with timestamps.

        Returns:
            If include_timestamps is False: Transcribed text (str)
            If include_timestamps is True: TranscriptionResult with text and segments

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

                if include_timestamps:
                    # Get transcript with timestamps
                    transcript, raw_segments = self._transcribe_single_file(
                        audio_path, progress_callback, include_timestamps=True
                    )
                    
                    # Format into sentences with aligned timestamps
                    formatted_text, sentence_segments = self._format_transcript_with_timestamps(raw_segments)
                    
                    if progress_callback:
                        word_count = len(transcript.split())
                        sentence_count = len(sentence_segments)
                        progress_callback(f"Transcription completed ({word_count} words, {sentence_count} sentences with timestamps)")
                    
                    return TranscriptionResult(
                        text=formatted_text,
                        segments=sentence_segments,
                        duration=raw_segments[-1].end if raw_segments else None
                    )
                else:
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

                    if include_timestamps:
                        # Split audio into chunks WITH offset tracking
                        chunk_data = self._split_audio_into_chunks(
                            audio_path, temp_path, progress_callback, include_offsets=True
                        )

                        # Transcribe each chunk with timestamp offset adjustment
                        all_segments = []
                        total_words = 0

                        if progress_callback:
                            progress_callback(f"Transcribing {len(chunk_data)} chunks with timestamps...")

                        for i, (chunk_file, time_offset) in enumerate(chunk_data, 1):
                            if progress_callback:
                                progress_callback(f"Uploading chunk {i}/{len(chunk_data)} to OpenAI...")

                            chunk_text, chunk_segments = self._transcribe_single_file(
                                chunk_file, progress_callback, 
                                include_timestamps=True, 
                                time_offset=time_offset
                            )
                            all_segments.extend(chunk_segments)

                            chunk_words = len(chunk_text.split())
                            total_words += chunk_words

                            if progress_callback:
                                progress_callback(f"Chunk {i}/{len(chunk_data)} completed ({chunk_words} words)")

                        # Format into sentences with aligned timestamps
                        formatted_text, sentence_segments = self._format_transcript_with_timestamps(all_segments)

                        if progress_callback:
                            sentence_count = len(sentence_segments)
                            progress_callback(f"All chunks transcribed and combined ({total_words} words, {sentence_count} sentences with timestamps)")

                        return TranscriptionResult(
                            text=formatted_text,
                            segments=sentence_segments,
                            duration=all_segments[-1].end if all_segments else None
                        )
                    else:
                        # Original logic without timestamps
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

