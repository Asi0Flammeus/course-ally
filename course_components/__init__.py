"""
Course Components Package

This package provides modular components for building course materials,
including downloading YouTube audio, transcribing audio, and generating
lecture content in markdown format.
"""

# Import main components with error handling for optional dependencies
try:
    from .downloader import YouTubeDownloader
except ImportError:
    YouTubeDownloader = None

try:
    from .transcription import TranscriptionService
except ImportError:
    TranscriptionService = None

from .chapter_generator import ChapterGenerator
from .quiz_generator import QuizGenerator
from .quiz_workflow import QuizWorkflowManager
from .utils import detect_youtube_url_type

__all__ = [
    'YouTubeDownloader',
    'TranscriptionService', 
    'ChapterGenerator',
    'QuizGenerator',
    'QuizWorkflowManager',
    'detect_youtube_url_type'
]