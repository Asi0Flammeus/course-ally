from flask import Flask, render_template, request, jsonify, Response, send_file
from flask_cors import CORS
import json
import time
import threading
import queue
import tempfile
from pathlib import Path
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Import your existing modules
from course_components.downloader import YouTubeDownloader
from course_components.transcription import TranscriptionService
from course_components.chapter_generator import ChapterGenerator
from course_components.quiz_generator import QuizGenerator
from course_components.quiz_workflow import QuizWorkflowManager
from course_components.utils import detect_youtube_url_type
from course_components.course_editor import CourseEditor

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Global progress queue for SSE
progress_queues = {}
# Global process tracking for cancellation
active_processes = {}

def create_progress_queue():
    """Create a unique progress queue for a session"""
    import uuid
    session_id = str(uuid.uuid4())
    progress_queues[session_id] = queue.Queue()
    return session_id

def send_progress(session_id, message, status="processing", percentage=None):
    """Send progress update to the client"""
    if session_id in progress_queues:
        data = {
            "message": message,
            "status": status,
            "timestamp": time.time()
        }
        if percentage is not None:
            data["percentage"] = percentage
        progress_queues[session_id].put(json.dumps(data))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/cancel/<session_id>', methods=['POST'])
def cancel_process(session_id):
    """Cancel a running process"""
    if session_id in active_processes:
        active_processes[session_id]['cancelled'] = True
        send_progress(session_id, "🛑 Process cancelled by user", "error", 100)
        return jsonify({"status": "cancelled"})
    return jsonify({"status": "not_found"}), 404

@app.route('/api/playlist-to-md', methods=['POST'])
def playlist_to_md():
    """Convert YouTube playlist to markdown"""
    data = request.json
    playlist_url = data.get('playlist_url')
    subfolder = data.get('subfolder', None)
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "🔗 Starting playlist extraction...", "processing", 10)
            
            downloader = YouTubeDownloader()
            
            # Set up output directory
            base_path = Path('outputs') / 'playlist_to_md'
            if subfolder:
                output_path = base_path / subfolder
            else:
                output_path = base_path
            output_path.mkdir(parents=True, exist_ok=True)
            
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "📋 Fetching playlist information...", "processing", 30)
            
            # Get playlist videos
            def playlist_progress(message):
                send_progress(session_id, f"📋 {message}", "processing", 40)
            
            videos = downloader.get_playlist_videos(playlist_url, progress_callback=playlist_progress)
            
            if not videos:
                send_progress(session_id, "❌ No videos found in playlist.", "error", 100)
                return
            
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, f"✅ Found {len(videos)} videos", "processing", 60)
            
            # Generate markdown content
            send_progress(session_id, "📝 Generating markdown file...", "processing", 80)
            
            md_content = ""
            for video in videos:
                video_id = video['id']
                video_title = video['title']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                md_content += f"## {video_title}\n"
                md_content += f"![video]({video_url})\n\n"
            
            # Save markdown file
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"playlist_{timestamp}.md"
            md_file = output_path / filename
            md_file.write_text(md_content, encoding='utf-8')
            
            send_progress(session_id, f"✨ Markdown file created: {filename}", "success", 100)
            
        except Exception as e:
            send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/extract-transcripts', methods=['POST'])
def extract_transcripts():
    """Extract transcripts from YouTube videos"""
    data = request.json
    youtube_url = data.get('youtube_url')
    subfolder = data.get('subfolder', None)
    format_type = data.get('format', 'txt')
    max_workers = data.get('max_workers', 4)  # Add max_workers support
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "🔍 Detecting URL type...", "processing", 5)
            
            # Detect URL type
            url_type, identifier = detect_youtube_url_type(youtube_url)
            
            if url_type == 'invalid':
                send_progress(session_id, "❌ Invalid YouTube URL provided.", "error", 100)
                return
            
            send_progress(session_id, f"✅ URL Type: {url_type.upper()}", "processing", 10)
            
            downloader = YouTubeDownloader()
            transcription_service = TranscriptionService()
            
            # Set up output directory
            base_path = Path('outputs') / 'transcripts'
            if subfolder:
                output_path = base_path / subfolder
            else:
                output_path = base_path
            output_path.mkdir(parents=True, exist_ok=True)
            
            if url_type == 'video':
                # Handle single video
                video_id = identifier
                send_progress(session_id, "🎥 Processing single video...", "processing", 20)
                
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Download audio
                    send_progress(session_id, "🔽 Downloading audio from YouTube...", "processing", 30)
                    
                    def download_progress(message):
                        send_progress(session_id, message, "processing", 40)
                    
                    audio_path = downloader.download_audio(video_id, tmpdir, progress_callback=download_progress)
                    
                    if active_processes.get(session_id, {}).get('cancelled', False):
                        return
                    
                    # Transcribe audio
                    send_progress(session_id, "🎤 Transcribing audio...", "processing", 60)
                    
                    def transcribe_progress(message):
                        send_progress(session_id, message, "processing", 80)
                    
                    transcript = transcription_service.transcribe(audio_path, progress_callback=transcribe_progress)
                    
                    # Save transcript
                    timestamp = time.strftime('%Y%m%d_%H%M%S')
                    filename = f"video_{video_id}_{timestamp}.{format_type}"
                    transcript_file = output_path / filename
                    
                    if format_type == 'txt':
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        metadata_header = f"""# Video Transcript
Video ID: {video_id}
URL: {video_url}
Transcribed: {time.strftime('%Y-%m-%d %H:%M:%S')}

{'='*60}

"""
                        transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                    else:
                        transcript_data = {
                            'video_id': video_id,
                            'transcript': transcript,
                            'transcribed_at': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        with open(transcript_file, 'w', encoding='utf-8') as f:
                            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                    
                    send_progress(session_id, f"✅ Transcript saved: {filename}", "success", 100)
            
            else:
                # Handle playlist
                send_progress(session_id, "🎬 Processing playlist...", "processing", 20)
                
                def playlist_progress(message):
                    send_progress(session_id, f"📋 {message}", "processing", 30)
                
                video_ids = downloader.get_playlist_video_ids(youtube_url, progress_callback=playlist_progress)
                
                if not video_ids:
                    send_progress(session_id, "❌ No videos found in playlist.", "error", 100)
                    return
                
                send_progress(session_id, f"✅ Found {len(video_ids)} videos", "processing", 40)
                send_progress(session_id, f"⚡ Using {max_workers} parallel workers", "processing", 42)
                
                # Thread-safe counters
                successful = 0
                failed = 0
                stats_lock = threading.Lock()
                
                def process_video(video_data):
                    """Process a single video"""
                    idx, video_id = video_data
                    
                    # Check if cancelled
                    if active_processes.get(session_id, {}).get('cancelled', False):
                        return {'status': 'cancelled'}
                    
                    with tempfile.TemporaryDirectory() as tmpdir:
                        try:
                            # Create individual instances for thread safety
                            video_downloader = YouTubeDownloader()
                            video_transcription = TranscriptionService()
                            
                            # Download and transcribe
                            with stats_lock:
                                send_progress(session_id, f"🎥 [{idx}/{len(video_ids)}] Downloading video {video_id}", "processing")
                            
                            audio_path = video_downloader.download_audio(video_id, tmpdir)
                            
                            # Check if cancelled
                            if active_processes.get(session_id, {}).get('cancelled', False):
                                return {'status': 'cancelled'}
                            
                            with stats_lock:
                                send_progress(session_id, f"🎤 [{idx}/{len(video_ids)}] Transcribing audio", "processing")
                            
                            transcript = video_transcription.transcribe(audio_path)
                            
                            # Save transcript
                            filename = f"{idx:02d}_video_{video_id}.txt"
                            transcript_file = output_path / filename
                            
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            metadata_header = f"""# Video Transcript
Video ID: {video_id}
URL: {video_url}

{'='*60}

"""
                            transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                            
                            return {'status': 'success', 'video_id': video_id}
                            
                        except Exception as e:
                            return {'status': 'failed', 'video_id': video_id, 'error': str(e)}
                
                # Process videos in parallel
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(process_video, (idx, vid)): (idx, vid) 
                              for idx, vid in enumerate(video_ids, 1)}
                    
                    for future in as_completed(futures):
                        # Check if cancelled
                        if active_processes.get(session_id, {}).get('cancelled', False):
                            executor.shutdown(wait=False)
                            break
                        
                        result = future.result()
                        idx, vid = futures[future]
                        
                        with stats_lock:
                            if result['status'] == 'success':
                                successful += 1
                                percentage = 40 + ((successful + failed) / len(video_ids)) * 50
                                send_progress(session_id, f"✅ [{idx}/{len(video_ids)}] Completed: {result['video_id']}", "processing", percentage)
                            elif result['status'] == 'failed':
                                failed += 1
                                percentage = 40 + ((successful + failed) / len(video_ids)) * 50
                                send_progress(session_id, f"⚠️ [{idx}/{len(video_ids)}] Failed: {result.get('error', 'Unknown error')}", "warning", percentage)
                
                if not active_processes.get(session_id, {}).get('cancelled', False):
                    send_progress(session_id, f"✅ Completed: {successful} successful, {failed} failed", "success", 100)
                
        except Exception as e:
            send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        finally:
            # Clean up
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/download-video', methods=['POST'])
def download_video():
    """Download YouTube video or playlist as MP4"""
    data = request.json
    video_url = data.get('video_url')
    subfolder = data.get('subfolder', None)
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "🔍 Analyzing YouTube URL...", "processing", 5)
            
            downloader = YouTubeDownloader()
            
            # Set up output directory
            base_path = Path('outputs') / 'videos'
            if subfolder:
                output_path = base_path / subfolder
            else:
                output_path = base_path
            output_path.mkdir(parents=True, exist_ok=True)
            
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
            
            # Determine if it's a playlist or single video
            is_playlist = 'list=' in video_url or 'playlist' in video_url.lower()
            
            if is_playlist:
                send_progress(session_id, "🎬 Detected playlist - preparing to download all videos...", "processing", 10)
                
                # Download progress callback
                def download_progress(message):
                    if not active_processes.get(session_id, {}).get('cancelled', False):
                        send_progress(session_id, message, "processing", 50)
                
                # Use the new playlist download method
                stats = downloader.download_playlist_videos(video_url, str(output_path), progress_callback=download_progress)
                
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return
                
                # Success message with statistics
                summary = f"✅ Download Complete! Total: {stats['total']} | ✅ Success: {stats['successful']} | ⏭️ Skipped: {stats['skipped']}"
                if stats['failed'] > 0:
                    summary += f" | ⚠️ Failed: {stats['failed']}"
                send_progress(session_id, summary, "success", 100)
                
            else:
                send_progress(session_id, "🎥 Detected single video - starting download...", "processing", 10)
                
                # Download progress callback
                def download_progress(message):
                    if not active_processes.get(session_id, {}).get('cancelled', False):
                        send_progress(session_id, f"📥 {message}", "processing", 50)
                
                # Download single video
                result_path = downloader.download_video(video_url, str(output_path), progress_callback=download_progress)
                
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return
                
                send_progress(session_id, f"✅ Video downloaded successfully: {result_path.name if isinstance(result_path, Path) else 'video.mp4'}", "success", 100)
            
        except Exception as e:
            send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/create-chapters', methods=['POST'])
def create_chapters():
    """Create chapters from transcripts"""
    data = request.json
    transcript_folder = data.get('transcript_folder')
    subfolder = data.get('subfolder', None)
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "📚 Starting chapter generation...", "processing", 10)
            
            # Find transcript files
            transcripts_path = Path('outputs') / 'transcripts' / transcript_folder
            if not transcripts_path.exists():
                send_progress(session_id, f"❌ Transcript folder not found: {transcript_folder}", "error", 100)
                return
            
            txt_files = list(transcripts_path.glob('*.txt'))
            if not txt_files:
                send_progress(session_id, "❌ No transcript files found", "error", 100)
                return
            
            send_progress(session_id, f"📄 Found {len(txt_files)} transcript files", "processing", 20)
            
            # Set up output directory
            base_path = Path('outputs') / 'chapters'
            if subfolder:
                output_path = base_path / subfolder
            else:
                output_path = base_path / transcript_folder
            output_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize chapter generator
            try:
                generator = ChapterGenerator()
                send_progress(session_id, "✅ Chapter generator initialized", "processing", 30)
            except Exception as e:
                send_progress(session_id, f"❌ Error initializing generator: {str(e)}", "error", 100)
                return
            
            # Process each transcript
            for idx, transcript_file in enumerate(txt_files, 1):
                if active_processes.get(session_id, {}).get('cancelled', False):
                    break
                    
                percentage = 30 + (idx / len(txt_files)) * 60
                send_progress(session_id, f"📖 Processing: {transcript_file.name}", "processing", percentage)
                
                chapter_filename = transcript_file.stem + '_chapter.md'
                chapter_file = output_path / chapter_filename
                
                if not chapter_file.exists():
                    try:
                        chapter_content = generator.generate_chapter_from_file(
                            transcript_file=transcript_file,
                            output_file=chapter_file
                        )
                        send_progress(session_id, f"✅ Created: {chapter_filename}", "processing", percentage)
                    except Exception as e:
                        send_progress(session_id, f"⚠️ Error with {transcript_file.name}: {str(e)}", "warning", percentage)
                else:
                    send_progress(session_id, f"⏭️ Skipping existing: {chapter_filename}", "processing", percentage)
            
            if not active_processes.get(session_id, {}).get('cancelled', False):
                send_progress(session_id, "✅ All chapters generated successfully!", "success", 100)
            
        except Exception as e:
            send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/create-quiz', methods=['POST'])
def create_quiz():
    """Create quiz from chapters - supports both old and new workflow"""
    data = request.json
    
    # Check if this is the new wizard workflow (has 'repository' field)
    if 'repository' in data:
        # New wizard workflow
        from course_components.quiz_workflow import QuizWorkflowManager
        
        repository = data.get('repository')
        courses = data.get('courses', [])
        language = data.get('language', 'en')
        chapters = data.get('chapters', 'all')
        specific_chapters = data.get('specific_chapters', [])  # Get the actual chapter IDs
        difficulty = data.get('difficulty', {'easy': 3, 'intermediate': 3, 'hard': 3})
        author = data.get('author', 'Unknown Author')
        contributors_str = data.get('contributors', '')
        
        session_id = create_progress_queue()
        active_processes[session_id] = {'cancelled': False}
        
        def process():
            try:
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return
                    
                send_progress(session_id, "🚀 Initializing quiz workflow manager...", "processing", 5)
                
                # Initialize workflow manager
                workflow_manager = QuizWorkflowManager()
                
                # Set author and contributors
                workflow_manager.author = author
                contributors = []
                if contributors_str:
                    contributors = [name.strip() for name in contributors_str.split(',') if name.strip()]
                    workflow_manager.contributors = contributors
                
                send_progress(session_id, f"📚 Processing {len(courses)} course(s)...", "processing", 10)
                
                total_questions_generated = 0
                questions_per_chapter = sum(difficulty.values())
                
                # Process each course
                for course_idx, course in enumerate(courses):
                    course_progress_base = 10 + (course_idx * 80 / len(courses))
                    
                    if active_processes.get(session_id, {}).get('cancelled', False):
                        send_progress(session_id, "🛑 Process cancelled", "error", 100)
                        return
                    
                    send_progress(session_id, f"📖 Processing course: {course}", "processing", course_progress_base)
                    
                    # Get chapters for the course
                    course_chapters = workflow_manager.list_chapters(repository, course, language)
                    
                    if not course_chapters:
                        send_progress(session_id, f"⚠️ No chapters found for {course}", "warning", course_progress_base + 5)
                        continue
                    
                    # Filter chapters if specific ones requested
                    if chapters == 'specific' and specific_chapters:
                        course_chapters = [ch for ch in course_chapters if ch['chapter_id'] in specific_chapters]
                    
                    send_progress(session_id, f"📝 Found {len(course_chapters)} chapters in {course}", "processing", course_progress_base + 10)
                    
                    # Extract chapter IDs for quiz generation
                    chapter_ids = [ch['chapter_id'] for ch in course_chapters]
                    
                    # Calculate total questions per chapter based on difficulty
                    questions_per_chapter = sum(difficulty.values())
                    
                    # Generate quiz using the workflow manager
                    try:
                        # Create progress callback that accepts 3 arguments
                        def quiz_progress(message, status, percentage):
                            nonlocal total_questions_generated
                            if 'Generated' in message:
                                total_questions_generated += 1
                            send_progress(session_id, message, status, 
                                        course_progress_base + 20 + (course_idx * 60 / len(courses)))
                        
                        # Generate quiz for all chapters in this course
                        for progress_update in workflow_manager.generate_quiz(
                            repo_key=repository,
                            course_name=course,
                            chapter_ids=chapter_ids,
                            language=language,
                            question_count=questions_per_chapter,
                            difficulty_proportions={
                                'easy': difficulty['easy'] / questions_per_chapter,
                                'intermediate': difficulty['intermediate'] / questions_per_chapter,
                                'hard': difficulty['hard'] / questions_per_chapter
                            },
                            author=author,
                            contributors=contributors,
                            progress_callback=quiz_progress
                        ):
                            if active_processes.get(session_id, {}).get('cancelled', False):
                                send_progress(session_id, "🛑 Process cancelled", "error", 100)
                                return
                    except Exception as e:
                        send_progress(session_id, f"⚠️ Error generating quiz for {course}: {str(e)}", "warning", course_progress_base + 80)
                
                send_progress(session_id, f"🎉 Quiz generation complete! Generated {total_questions_generated} questions", "success", 100)
                
            except Exception as e:
                send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        
        # Start processing in background
        thread = threading.Thread(target=process)
        thread.start()
        
        return jsonify({"session_id": session_id})
    
    else:
        # Old workflow (backward compatibility)
        chapter_folder = data.get('chapter_folder')
        subfolder = data.get('subfolder', None)
        author = data.get('author', 'Unknown Author')
        contributors_str = data.get('contributors', '')
        
        session_id = create_progress_queue()
        active_processes[session_id] = {'cancelled': False}
        
        def process():
            try:
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return
                    
                send_progress(session_id, "🧠 Starting quiz generation...", "processing", 10)
                
                # Find chapter files
                chapters_path = Path('outputs') / 'chapters' / chapter_folder
                if not chapters_path.exists():
                    send_progress(session_id, f"❌ Chapter folder not found: {chapter_folder}", "error", 100)
                    return
                
                # Sort chapter files alphabetically to maintain order
                md_files = sorted(list(chapters_path.glob('*_chapter.md')), key=lambda x: x.name)
                if not md_files:
                    send_progress(session_id, "❌ No chapter files found", "error", 100)
                    return
                
                send_progress(session_id, f"📄 Found {len(md_files)} chapter files (processing in order)", "processing", 20)
                
                # Set up output directory
                base_path = Path('outputs') / 'quizz'
                if subfolder:
                    output_path = base_path / subfolder
                else:
                    output_path = base_path / chapter_folder
                output_path.mkdir(parents=True, exist_ok=True)
                
                # Initialize quiz generator
                try:
                    generator = QuizGenerator()
                    generator.author = author
                    
                    # Parse contributors
                    if contributors_str:
                        generator.contributor_names = [name.strip() for name in contributors_str.split(',') if name.strip()]
                    else:
                        generator.contributor_names = []
                        
                    send_progress(session_id, f"✅ Quiz generator initialized with author: {author}", "processing", 30)
                    if generator.contributor_names:
                        send_progress(session_id, f"📝 Contributors: {', '.join(generator.contributor_names)}", "processing", 32)
                except Exception as e:
                    send_progress(session_id, f"❌ Error initializing generator: {str(e)}", "error", 100)
                    return
                
                # Process each chapter
                for idx, chapter_file in enumerate(md_files, 1):
                    if active_processes.get(session_id, {}).get('cancelled', False):
                        break
                        
                    percentage = 30 + (idx / len(md_files)) * 60
                    send_progress(session_id, f"🧠 Processing: {chapter_file.name}", "processing", percentage)
                    
                    try:
                        # Generate quizzes (simplified - not interactive for web)
                        all_quizzes = generator.generate_quizzes_from_file(chapter_file)
                        
                        # Save quizzes
                        generator.save_multiple_quizzes(all_quizzes, output_path, chapter_file.stem)
                        
                        send_progress(session_id, f"✅ Created {len(all_quizzes)} quiz questions", "processing", percentage)
                    except Exception as e:
                        send_progress(session_id, f"⚠️ Error with {chapter_file.name}: {str(e)}", "warning", percentage)
                
                if not active_processes.get(session_id, {}).get('cancelled', False):
                    send_progress(session_id, "✅ All quizzes generated successfully!", "success", 100)
                
            except Exception as e:
                send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
            finally:
                if session_id in active_processes:
                    del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/list-folders', methods=['GET'])
def list_folders():
    """List available folders in outputs directory"""
    folder_type = request.args.get('type', 'transcripts')
    
    base_path = Path('outputs') / folder_type
    if not base_path.exists():
        return jsonify({"folders": []})
    
    folders = [f.name for f in base_path.iterdir() if f.is_dir()]
    return jsonify({"folders": sorted(folders)})

@app.route('/api/quiz/repos', methods=['GET'])
def quiz_list_repos():
    """List available quiz repositories"""
    try:
        workflow_manager = QuizWorkflowManager()
        repositories = workflow_manager.list_repositories()
        
        # Create a dictionary indexed by repo key for frontend compatibility
        repo_dict = {}
        repo_data = []
        
        for repo in repositories:
            repo_info = {
                'key': repo.key,
                'name': repo.name,
                'path': str(repo.path),
                'configured': repo.configured,
                'exists': repo.exists,
                'valid': repo.valid,
                'available': repo.valid  # Add 'available' field for frontend
            }
            repo_data.append(repo_info)
            repo_dict[repo.key] = repo_info
        
        return jsonify({
            'repositories': repo_dict,  # Dictionary for easy lookup
            'repositoryList': repo_data,  # Array for iteration
            'total': len(repo_data),
            'valid': len([r for r in repo_data if r['valid']])
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/courses', methods=['GET'])
def quiz_list_courses():
    """List courses in a repository"""
    repo_key = request.args.get('repo_key')
    if not repo_key:
        return jsonify({'error': 'repo_key parameter required'}), 400
    
    try:
        workflow_manager = QuizWorkflowManager()
        courses = workflow_manager.list_courses(repo_key)
        
        return jsonify({
            'courses': courses,
            'total': len(courses),
            'repository': repo_key
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/chapters', methods=['GET'])
def quiz_list_chapters():
    """List chapters in a course"""
    repo_key = request.args.get('repo_key')
    course_name = request.args.get('course_name')
    language = request.args.get('language', 'en')
    
    if not repo_key or not course_name:
        return jsonify({'error': 'repo_key and course_name parameters required'}), 400
    
    try:
        workflow_manager = QuizWorkflowManager()
        chapters = workflow_manager.list_chapters(repo_key, course_name, language)
        
        return jsonify({
            'chapters': chapters,
            'total': len(chapters),
            'repository': repo_key,
            'course': course_name,
            'language': language
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/languages', methods=['GET'])
def quiz_list_languages():
    """List available languages for a course"""
    repo_key = request.args.get('repo_key')
    course_name = request.args.get('course_name')
    
    if not repo_key or not course_name:
        return jsonify({'error': 'repo_key and course_name parameters required'}), 400
    
    try:
        workflow_manager = QuizWorkflowManager()
        language_codes = workflow_manager.list_languages(repo_key, course_name)
        
        # Map language codes to full names
        language_names = {
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'ja': 'Japanese',
            'ko': 'Korean',
            'zh': 'Chinese',
            'zh-Hans': 'Chinese (Simplified)',
            'zh-Hant': 'Chinese (Traditional)',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'cs': 'Czech',
            'nl': 'Dutch',
            'pl': 'Polish',
            'sv': 'Swedish',
            'fi': 'Finnish',
            'et': 'Estonian',
            'id': 'Indonesian',
            'vi': 'Vietnamese',
            'fa': 'Persian',
            'sw': 'Swahili',
            'sr-Latn': 'Serbian (Latin)',
            'nb-NO': 'Norwegian',
            'rn': 'Kirundi'
        }
        
        # Format languages as objects with code and name
        languages = []
        for code in language_codes:
            languages.append({
                'code': code,
                'name': language_names.get(code, code.upper())
            })
        
        return jsonify({
            'languages': languages,
            'total': len(languages),
            'repository': repo_key,
            'course': course_name
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/quiz/generate', methods=['POST'])
def quiz_generate():
    """Generate quiz questions with progress updates"""
    data = request.json
    
    # Validate required parameters
    required_fields = ['repo_key', 'course_name', 'chapter_ids']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} parameter required'}), 400
    
    repo_key = data['repo_key']
    course_name = data['course_name']
    chapter_ids = data['chapter_ids']
    language = data.get('language', 'en')
    question_count = data.get('question_count', 5)
    author = data.get('author', 'Course Ally')
    contributors = data.get('contributors', [])
    
    # Difficulty proportions
    difficulty_proportions = data.get('difficulty_proportions', {
        'easy': 0.3,
        'intermediate': 0.5,
        'hard': 0.2
    })
    
    # Validate parameters
    if not isinstance(chapter_ids, list) or len(chapter_ids) == 0:
        return jsonify({'error': 'chapter_ids must be a non-empty list'}), 400
    
    if question_count < 1 or question_count > 50:
        return jsonify({'error': 'question_count must be between 1 and 50'}), 400
    
    # Validate difficulty proportions
    if not all(isinstance(v, (int, float)) for v in difficulty_proportions.values()):
        return jsonify({'error': 'difficulty_proportions values must be numeric'}), 400
    
    total_proportion = sum(difficulty_proportions.values())
    if abs(total_proportion - 1.0) > 0.01:  # Allow small floating point errors
        return jsonify({'error': 'difficulty_proportions must sum to 1.0'}), 400
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            workflow_manager = QuizWorkflowManager()
            
            # Check if process was cancelled
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
            
            # Generate quiz with progress updates
            for progress_update in workflow_manager.generate_quiz(
                repo_key=repo_key,
                course_name=course_name,
                chapter_ids=chapter_ids,
                language=language,
                question_count=question_count,
                difficulty_proportions=difficulty_proportions,
                author=author,
                contributors=contributors,
                progress_callback=lambda msg, status, pct: send_progress(session_id, msg, status, pct)
            ):
                # Check if process was cancelled
                if active_processes.get(session_id, {}).get('cancelled', False):
                    send_progress(session_id, "🛑 Quiz generation cancelled", "error", 100)
                    return
                
                # Send progress update
                send_progress(
                    session_id,
                    progress_update['message'],
                    progress_update['status'],
                    progress_update.get('percentage')
                )
                
                # If this is the final message, break
                if progress_update['status'] in ['success', 'error']:
                    break
                    
        except Exception as e:
            send_progress(session_id, f"❌ Quiz generation error: {str(e)}", "error", 100)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({
        "session_id": session_id,
        "message": "Quiz generation started",
        "parameters": {
            "repo_key": repo_key,
            "course_name": course_name,
            "chapter_ids": chapter_ids,
            "language": language,
            "question_count": question_count,
            "difficulty_proportions": difficulty_proportions
        }
    })


# ================== Local Audio Transcription Routes ==================

@app.route('/api/audio/list-subfolders', methods=['GET'])
def audio_list_subfolders():
    """List available audio subfolders in outputs/audios"""
    try:
        audios_base = Path('outputs/audios')
        if not audios_base.exists():
            return jsonify({
                'success': True,
                'subfolders': []
            })
        
        subfolders = []
        for folder in audios_base.iterdir():
            if folder.is_dir():
                # Count audio files
                audio_files = []
                for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg', '*.flac', '*.MP3', '*.WAV', '*.M4A']:
                    audio_files.extend(folder.glob(ext))
                
                subfolders.append({
                    'name': folder.name,
                    'file_count': len(audio_files)
                })
        
        return jsonify({
            'success': True,
            'subfolders': sorted(subfolders, key=lambda x: x['name'])
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/audio/list-files', methods=['GET'])
def audio_list_files():
    """List audio files in a specific subfolder"""
    subfolder = request.args.get('subfolder')
    if not subfolder:
        return jsonify({'error': 'subfolder parameter required'}), 400
    
    try:
        folder_path = Path('outputs/audios') / subfolder
        if not folder_path.exists():
            return jsonify({
                'success': False,
                'error': f'Subfolder not found: {subfolder}'
            }), 404
        
        # Get all audio files
        audio_files = []
        for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg', '*.flac', '*.MP3', '*.WAV', '*.M4A']:
            for audio_file in folder_path.glob(ext):
                file_size_mb = audio_file.stat().st_size / (1024 * 1024)
                audio_files.append({
                    'name': audio_file.name,
                    'size_mb': round(file_size_mb, 1),
                    'extension': audio_file.suffix.lower()
                })
        
        # Sort by name
        audio_files.sort(key=lambda x: x['name'].lower())
        
        return jsonify({
            'success': True,
            'files': audio_files,
            'total': len(audio_files)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/audio/transcribe-local', methods=['POST'])
def transcribe_local_audio():
    """Transcribe local audio files from outputs/audios"""
    data = request.json
    audio_subfolder = data.get('audio_subfolder')
    selected_files = data.get('selected_files', [])  # List of filenames
    output_subfolder = data.get('output_subfolder', None)
    format_type = data.get('format', 'txt')
    max_workers = data.get('max_workers', 4)
    
    if not audio_subfolder:
        return jsonify({'error': 'audio_subfolder parameter required'}), 400
    
    if not selected_files or len(selected_files) == 0:
        return jsonify({'error': 'selected_files must be a non-empty list'}), 400
    
    session_id = create_progress_queue()
    active_processes[session_id] = {'cancelled': False}
    
    def process():
        try:
            if active_processes.get(session_id, {}).get('cancelled', False):
                return
                
            send_progress(session_id, "🎤 Starting local audio transcription...", "processing", 5)
            
            # Validate audio folder
            audio_folder = Path('outputs/audios') / audio_subfolder
            if not audio_folder.exists():
                send_progress(session_id, f"❌ Audio folder not found: {audio_subfolder}", "error", 100)
                return
            
            # Get audio files to process
            audio_files = []
            for filename in selected_files:
                audio_path = audio_folder / filename
                if audio_path.exists():
                    audio_files.append(audio_path)
                else:
                    send_progress(session_id, f"⚠️ File not found: {filename}", "warning", 10)
            
            if not audio_files:
                send_progress(session_id, "❌ No valid audio files found", "error", 100)
                return
            
            send_progress(session_id, f"✅ Found {len(audio_files)} audio files to process", "processing", 15)
            
            # Set up output directory
            base_path = Path('outputs') / 'transcripts'
            if output_subfolder:
                output_path = base_path / output_subfolder
            else:
                output_path = base_path / audio_subfolder
            output_path.mkdir(parents=True, exist_ok=True)
            
            send_progress(session_id, f"📁 Saving transcripts to: {output_path.name}/", "processing", 20)
            send_progress(session_id, f"⚡ Using {max_workers} parallel workers", "processing", 22)
            
            # Initialize transcription service
            transcription_service = TranscriptionService()
            
            # Thread-safe counters
            successful = 0
            failed = 0
            skipped = 0
            total_words = 0
            stats_lock = threading.Lock()
            
            def process_audio_file(file_data):
                """Process a single audio file"""
                idx, audio_file = file_data
                
                # Check if cancelled
                if active_processes.get(session_id, {}).get('cancelled', False):
                    return {'status': 'cancelled'}
                
                # Check if already transcribed
                existing_files = list(output_path.glob(f"*{audio_file.stem}*"))
                if existing_files:
                    return {
                        'status': 'skipped',
                        'file': audio_file.name,
                        'message': f'Already transcribed: {existing_files[0].name}'
                    }
                
                try:
                    # Create individual transcription service for thread safety
                    audio_transcription = TranscriptionService()
                    
                    with stats_lock:
                        send_progress(session_id, f"🎤 [{idx}/{len(audio_files)}] Transcribing: {audio_file.name}", "processing")
                    
                    # Transcribe audio
                    transcript = audio_transcription.transcribe(audio_file)
                    
                    # Calculate stats
                    word_count = len(transcript.split())
                    
                    # Save transcript
                    timestamp = time.strftime('%Y%m%d_%H%M%S')
                    filename_base = f"{audio_file.stem}_{timestamp}"
                    
                    if format_type == 'txt':
                        transcript_file = output_path / f"{filename_base}.txt"
                        
                        metadata_header = f"""# Audio Transcript
File: {audio_file.name}
Transcribed: {time.strftime('%Y-%m-%d %H:%M:%S')}
Words: {word_count}

{'='*60}

"""
                        transcript_file.write_text(metadata_header + transcript, encoding='utf-8')
                    else:  # JSON format
                        transcript_file = output_path / f"{filename_base}.json"
                        transcript_data = {
                            'file': audio_file.name,
                            'transcript': transcript,
                            'word_count': word_count,
                            'transcribed_at': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                        with open(transcript_file, 'w', encoding='utf-8') as f:
                            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
                    
                    with stats_lock:
                        send_progress(session_id, f"✅ [{idx}/{len(audio_files)}] Completed: {audio_file.name} ({word_count} words)", "processing")
                    
                    return {
                        'status': 'success',
                        'file': audio_file.name,
                        'word_count': word_count
                    }
                    
                except Exception as e:
                    with stats_lock:
                        send_progress(session_id, f"❌ [{idx}/{len(audio_files)}] Error: {audio_file.name} - {str(e)}", "warning")
                    return {
                        'status': 'failed',
                        'file': audio_file.name,
                        'error': str(e)
                    }
            
            send_progress(session_id, "─" * 60, "processing", 25)
            send_progress(session_id, "🚀 Starting parallel transcription...", "processing", 30)
            
            # Process audio files in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(process_audio_file, (idx, audio_file)): (idx, audio_file)
                          for idx, audio_file in enumerate(audio_files, 1)}
                
                for future in as_completed(futures):
                    # Check if cancelled
                    if active_processes.get(session_id, {}).get('cancelled', False):
                        executor.shutdown(wait=False)
                        break
                    
                    result = future.result()
                    
                    with stats_lock:
                        if result['status'] == 'success':
                            successful += 1
                            total_words += result.get('word_count', 0)
                            percentage = 30 + ((successful + failed + skipped) / len(audio_files)) * 65
                            send_progress(session_id, f"✅ Progress: {successful}/{len(audio_files)} completed", "processing", percentage)
                        elif result['status'] == 'failed':
                            failed += 1
                        elif result['status'] == 'skipped':
                            skipped += 1
            
            if not active_processes.get(session_id, {}).get('cancelled', False):
                send_progress(session_id, "═" * 60, "processing", 95)
                summary = f"✅ Transcription Complete! "
                summary += f"Success: {successful} | "
                if skipped > 0:
                    summary += f"Skipped: {skipped} | "
                if failed > 0:
                    summary += f"Failed: {failed} | "
                summary += f"Total words: {total_words:,}"
                send_progress(session_id, summary, "success", 100)
                
        except Exception as e:
            send_progress(session_id, f"❌ Error: {str(e)}", "error", 100)
        finally:
            if session_id in active_processes:
                del active_processes[session_id]
    
    # Start processing in background
    thread = threading.Thread(target=process)
    thread.start()
    
    return jsonify({"session_id": session_id})

@app.route('/api/progress/<session_id>')
def progress_stream(session_id):
    """Server-Sent Events endpoint for progress updates"""
    def generate():
        if session_id not in progress_queues:
            yield f"data: {json.dumps({'error': 'Invalid session'})}\n\n"
            return
        
        q = progress_queues[session_id]
        
        # Send initial connection message
        yield f"data: {json.dumps({'message': 'Connected', 'status': 'connected'})}\n\n"
        
        while True:
            try:
                # Wait for messages with timeout
                message = q.get(timeout=30)
                yield f"data: {message}\n\n"
                
                # Check if this was the final message
                msg_data = json.loads(message)
                if msg_data.get('status') in ['success', 'error']:
                    # Clean up the queue after final message
                    del progress_queues[session_id]
                    break
                    
            except queue.Empty:
                # Send keepalive
                yield f"data: {json.dumps({'keepalive': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return Response(generate(), mimetype='text/event-stream')

# ================== Course Editor Routes ==================

@app.route('/course-editor')
def course_editor_page():
    """Serve the course editor page"""
    return render_template('course_editor.html')

@app.route('/api/editor/courses', methods=['GET'])
def editor_list_courses():
    """List all courses from both repositories for editing"""
    try:
        editor = CourseEditor()
        courses = editor.list_all_courses()
        
        return jsonify({
            'success': True,
            'courses': courses,
            'total': len(courses)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/course/<repo_key>/<course_name>', methods=['GET'])
def editor_load_course(repo_key, course_name):
    """Load course data for editing"""
    try:
        editor = CourseEditor()
        course_data = editor.load_course_data(repo_key, course_name)
        
        return jsonify({
            'success': True,
            'data': course_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/translate', methods=['POST'])
def editor_translate_content():
    """Translate course content to target languages"""
    try:
        data = request.json
        content = data.get('content')
        target_languages = data.get('target_languages', [])
        
        if not content or not target_languages:
            return jsonify({
                'success': False,
                'error': 'Missing content or target languages'
            }), 400
        
        editor = CourseEditor()
        translations = editor.translate_content(content, target_languages)
        
        return jsonify({
            'success': True,
            'translations': translations
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/save', methods=['POST'])
def editor_save_course():
    """Save course changes"""
    try:
        data = request.json
        repo_key = data.get('repo')
        course_name = data.get('course')
        new_index = data.get('new_index')
        metadata = data.get('metadata')
        content = data.get('content')
        
        if not all([repo_key, course_name, new_index, metadata, content]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        editor = CourseEditor()
        result = editor.save_course_data(repo_key, course_name, new_index, metadata, content)
        
        return jsonify({
            'success': result,
            'message': 'Course updated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/load', methods=['POST'])
def editor_load_course_v2():
    """Load course data for editing"""
    try:
        data = request.json
        repo_key = data.get('repo')
        course_name = data.get('course')
        
        if not repo_key or not course_name:
            return jsonify({
                'success': False,
                'error': 'Repository and course are required'
            }), 400
        
        editor = CourseEditor()
        course_data = editor.load_course_data(repo_key, course_name)
        
        return jsonify({
            'success': True,
            'data': course_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/save-metadata', methods=['POST'])
def editor_save_metadata():
    """Save only course metadata"""
    try:
        data = request.json
        repo_key = data.get('repo')
        course_name = data.get('course')
        new_index = data.get('new_index')
        metadata = data.get('metadata')
        
        if not all([repo_key, course_name, metadata]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        editor = CourseEditor()
        # Just save metadata without touching content
        result = editor.save_metadata(repo_key, course_name, new_index, metadata)
        
        return jsonify({
            'success': result,
            'message': 'Metadata saved successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/editor/save-field', methods=['POST'])
def editor_save_field():
    """Save and translate a specific field"""
    try:
        data = request.json
        repo_key = data.get('repo')
        course_name = data.get('course')
        field_name = data.get('field')
        field_value = data.get('value')
        languages = data.get('languages', [])
        
        if not all([repo_key, course_name, field_name]):
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
        
        editor = CourseEditor()
        
        # Translate ONLY the specific field to all languages
        target_languages = [lang for lang in languages if lang != 'en']
        translations_by_lang = {}
        
        if target_languages:
            if editor.client:
                # Use the optimized single-field translation
                field_translations = editor.translate_single_field(field_name, field_value, target_languages)
                
                # Convert to format expected by update_field
                for lang, translated_value in field_translations.items():
                    if field_name == 'objectives':
                        translations_by_lang[lang] = {
                            'objectives': translated_value if isinstance(translated_value, list) else []
                        }
                    else:
                        translations_by_lang[lang] = {
                            field_name: translated_value
                        }
            else:
                print("Warning: Anthropic client not configured, translations skipped")
        
        # Update only the specific field in each language file
        result = editor.update_field(repo_key, course_name, field_name, field_value, translations_by_lang)
        
        # Debug logging
        print(f"Field: {field_name}")
        print(f"Value type: {type(field_value)}")
        print(f"Target languages: {target_languages}")
        print(f"Translations received: {len(translations_by_lang)} languages")
        
        return jsonify({
            'success': result,
            'translated_count': len(translations_by_lang),
            'message': f'{field_name} saved and translated successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/course-editor')
def course_editor():
    """Render the improved course editor page"""
    return render_template('course_editor.html')

if __name__ == '__main__':
    app.run(debug=True, threaded=True, port=5000)