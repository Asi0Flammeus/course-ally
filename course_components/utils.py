"""
Utility functions for Course Ally
"""

import re
from typing import Tuple, Optional
from urllib.parse import urlparse, parse_qs

def detect_youtube_url_type(url: str) -> Tuple[str, Optional[str]]:
    """
    Detect if a YouTube URL is a playlist, single video, or invalid.
    
    Args:
        url: YouTube URL to analyze
        
    Returns:
        Tuple of (type, video_id_or_url) where:
        - type: 'playlist', 'video', or 'invalid'
        - video_id_or_url: For 'video' type returns video_id, for 'playlist' returns original URL, for 'invalid' returns None
        
    Examples:
        >>> detect_youtube_url_type("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        ('video', 'dQw4w9WgXcQ')
        
        >>> detect_youtube_url_type("https://www.youtube.com/playlist?list=PLrAXtmRdnEQy6nuLMHjMZrX3W2VwY")
        ('playlist', 'https://www.youtube.com/playlist?list=PLrAXtmRdnEQy6nuLMHjMZrX3W2VwY')
        
        >>> detect_youtube_url_type("https://youtu.be/dQw4w9WgXcQ")
        ('video', 'dQw4w9WgXcQ')
        
        >>> detect_youtube_url_type("invalid-url")
        ('invalid', None)
    """
    if not url or not isinstance(url, str):
        return ('invalid', None)
    
    # Clean up the URL
    url = url.strip()
    
    try:
        parsed = urlparse(url)
        
        # Check if it's a YouTube domain
        if parsed.netloc not in ['www.youtube.com', 'youtube.com', 'youtu.be', 'm.youtube.com']:
            return ('invalid', None)
        
        # Parse query parameters
        query_params = parse_qs(parsed.query)
        
        # Check for playlist indicators
        if 'list' in query_params:
            # It's a playlist URL
            return ('playlist', url)
        
        # Check for video indicators
        if parsed.netloc == 'youtu.be':
            # Short URL format: https://youtu.be/VIDEO_ID
            video_id = parsed.path.lstrip('/')
            if video_id and len(video_id) == 11:  # YouTube video IDs are 11 characters
                return ('video', video_id)
        
        elif 'v' in query_params:
            # Standard format: https://www.youtube.com/watch?v=VIDEO_ID
            video_id = query_params['v'][0]
            if video_id and len(video_id) == 11:
                return ('video', video_id)
        
        elif '/embed/' in parsed.path:
            # Embed format: https://www.youtube.com/embed/VIDEO_ID
            video_id = parsed.path.split('/embed/')[-1].split('?')[0]
            if video_id and len(video_id) == 11:
                return ('video', video_id)
        
        # If we get here, it's a YouTube URL but not recognized format
        return ('invalid', None)
        
    except Exception:
        return ('invalid', None)

def extract_video_id_from_url(url: str) -> Optional[str]:
    """
    Extract video ID from various YouTube URL formats.
    
    Args:
        url: YouTube video URL
        
    Returns:
        Video ID if found, None otherwise
    """
    url_type, identifier = detect_youtube_url_type(url)
    
    if url_type == 'video':
        return identifier
    
    return None

def is_playlist_url(url: str) -> bool:
    """
    Check if URL is a YouTube playlist.
    
    Args:
        url: YouTube URL
        
    Returns:
        True if it's a playlist URL, False otherwise
    """
    url_type, _ = detect_youtube_url_type(url)
    return url_type == 'playlist'

def is_video_url(url: str) -> bool:
    """
    Check if URL is a YouTube video.
    
    Args:
        url: YouTube URL
        
    Returns:
        True if it's a video URL, False otherwise
    """
    url_type, _ = detect_youtube_url_type(url)
    return url_type == 'video'