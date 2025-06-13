# Course Ally

A powerful command-line tool for extracting and processing YouTube content. Generate lectures, transcripts, and organize video links from YouTube videos and playlists using OpenAI's APIs.

## Requirements

1. **Python 3.8 or higher**
2. **OpenAI API key**: Set in environment variable `export OPENAI_API_KEY=your_api_key`
3. **FFmpeg**: Required for audio processing and chunking large files
   ```bash
   # Ubuntu/Debian
   sudo apt install ffmpeg
   
   # macOS
   brew install ffmpeg
   
   # Windows
   # Download from https://ffmpeg.org/download.html
   ```
4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## Features

### 🎓 Create Lecture
Generate structured lecture content from a single YouTube video.

```bash
python main.py create-lecture <VIDEO_ID> [OPTIONS]
```

**Options:**
- `--output, -o`: Save location for markdown file
- `--sections, -s`: Number of main sections (default: 3)

**What it does:**
- Downloads and converts video to audio
- Transcribes audio using OpenAI Whisper
- Generates structured lecture content with sections and key points
- Outputs clean markdown format

### 🎬 Extract Playlist Transcripts
Transcribe all videos from a YouTube playlist with parallel processing.

```bash
python main.py extract-playlist-transcripts <PLAYLIST_URL> [OPTIONS]
```

**Options:**
- `--subfolder, -s`: Optional subfolder in outputs/transcripts
- `--format, -f`: Output format (txt/json, default: txt)
- `--max-workers, -w`: Parallel workers for faster processing (default: 4)

**What it does:**
- Extracts all video IDs from playlist
- Downloads and transcribes videos in parallel (4x faster!)
- Automatically chunks large audio files (>25MB) for processing
- Saves individual transcript files with metadata
- Supports both text and JSON output formats

### 🔗 Extract Playlist Links
Extract and organize all video links from a YouTube playlist into markdown.

```bash
python main.py extract-playlist-links <PLAYLIST_URL> [OPTIONS]
```

**Options:**
- `--subfolder, -s`: Optional subfolder in outputs/yt_links
- `--live-format, -l`: Use live embed format instead of regular links

**What it does:**
- Extracts playlist metadata and video information
- Generates organized markdown with playlist summary
- Creates properly formatted video links:
  - **Regular format**: `![lecture](video_url)` 
  - **Live format**: `<liveUrl>https://youtube.com/embed/video_id</liveUrl>`
- Includes video titles, durations, and playlist description

## Output Structure

All outputs are organized in the `outputs/` directory:

```
outputs/
├── transcripts/          # Video transcriptions
│   ├── subfolder/       # Optional subfolders
│   └── *.txt/*.json     # Transcript files
└── yt_links/            # Playlist link exports
    ├── subfolder/       # Optional subfolders  
    └── *.md             # Markdown link files
```

## Interactive Mode

Run without arguments for guided setup:

```bash
python main.py
```

The interactive menu will guide you through:
1. Feature selection
2. Input collection (URLs, options)
3. Configuration (workers, formats, etc.)

## Advanced Features

### 🚀 Parallel Processing
- Process multiple videos simultaneously (up to 4 workers by default)
- Configurable worker count for optimal performance
- Thread-safe progress reporting

### 📦 Large File Handling  
- Automatic chunking for audio files >25MB
- Smart duration-based splitting using FFmpeg
- Seamless chunk transcription and recombination

### 🎯 Smart Resumption
- Skips already processed videos automatically
- Continues interrupted playlist processing
- Maintains consistent file naming

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.


You can tip me via LN through this [link](https://getalby.com/p/asi0).

## License

This project is licensed under the MIT License. See `license.md` for details.


