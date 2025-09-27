"""
Quiz Workflow Manager - Multi-repository quiz generation service

This module provides a comprehensive quiz workflow that integrates with multiple
course repositories (BEC_REPO and PREMIUM_REPO) to generate quiz questions
with difficulty balancing and proper YAML formatting.
"""

import os
import re
import yaml
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Generator
from datetime import datetime
import uuid
from dataclasses import dataclass

try:
    from .quiz_generator import QuizGenerator
    from .utils import detect_youtube_url_type
except ImportError:
    # Handle direct import case
    from quiz_generator import QuizGenerator
    from utils import detect_youtube_url_type


@dataclass
class ChapterInfo:
    """Information about a course chapter"""
    title: str
    chapter_id: str
    content: str
    file_path: Path
    order: int


@dataclass
class CourseInfo:
    """Information about a course"""
    name: str
    title: str
    description: str
    path: Path
    chapters: List[ChapterInfo]
    languages: List[str]
    metadata: Dict[str, Any]


@dataclass
class RepositoryInfo:
    """Information about a repository"""
    key: str
    name: str
    path: Path
    configured: bool
    exists: bool
    valid: bool


class QuizWorkflowManager:
    """Manages multi-repository quiz generation workflow"""
    
    SUPPORTED_LANGUAGES = ['en', 'es', 'fr', 'de', 'pt', 'it', 'ja', 'ko', 'zh']
    DEFAULT_DIFFICULTY_PROPORTIONS = {
        'easy': 0.3,
        'intermediate': 0.5, 
        'hard': 0.2
    }
    
    def __init__(self):
        """Initialize the quiz workflow manager"""
        self.repositories = {
            'BEC_REPO': {
                'name': 'Bitcoin Educational Content',
                'env_var': 'BEC_REPO',
                'default_path': '../bitcoin-educational-content'
            },
            'PREMIUM_REPO': {
                'name': 'Premium Content',
                'env_var': 'PREMIUM_REPO', 
                'default_path': '../premium-content'
            }
        }
        self.quiz_generator = None
        self._repo_cache = {}
        
    def _get_repo_path(self, repo_key: str) -> Optional[Path]:
        """Get the path for a repository"""
        if repo_key not in self.repositories:
            return None
            
        repo_info = self.repositories[repo_key]
        env_path = os.getenv(repo_info['env_var'])
        
        if env_path:
            # Handle both absolute and relative paths
            path = Path(env_path)
            if not path.is_absolute():
                # If relative, make it relative to the current working directory
                path = Path.cwd() / path
        else:
            # Use default path (relative to current directory)
            path = Path.cwd() / repo_info['default_path']
            
        # Check if path exists and has courses directory
        if path.exists() and (path / 'courses').exists():
            return path
        return None
    
    def list_repositories(self) -> List[RepositoryInfo]:
        """List available repositories with their status"""
        repos = []
        
        for repo_key, repo_config in self.repositories.items():
            # Get environment variable value
            env_path = os.getenv(repo_config['env_var'])
            configured = bool(env_path)
            
            # Get actual repository path
            path = self._get_repo_path(repo_key)
            
            # Determine display path
            if env_path:
                display_path = Path(env_path)
            else:
                display_path = Path(repo_config['default_path'])
            
            # Check if repository is valid (exists and has courses)
            valid = path is not None
            
            repos.append(RepositoryInfo(
                key=repo_key,
                name=repo_config['name'],
                path=display_path,
                configured=configured,
                exists=valid,  # If path is not None, it exists and has courses
                valid=valid
            ))
            
        return repos
    
    def list_courses(self, repo_key: str) -> List[Dict[str, Any]]:
        """List courses in a repository"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            return []
            
        courses = []
        courses_dir = repo_path / 'courses'
        
        if not courses_dir.exists():
            return []
            
        for course_dir in courses_dir.iterdir():
            if not course_dir.is_dir():
                continue
                
            # Look for course.yml or course.yaml
            course_yml = None
            for filename in ['course.yml', 'course.yaml']:
                yml_path = course_dir / filename
                if yml_path.exists():
                    course_yml = yml_path
                    break
                    
            if course_yml:
                try:
                    with open(course_yml, 'r', encoding='utf-8') as f:
                        metadata = yaml.safe_load(f) or {}
                    
                    # Use uppercase course name as title if no title in metadata
                    title = metadata.get('title', course_dir.name.upper())
                    
                    # Get topic and level for description
                    topic = metadata.get('topic', 'general')
                    level = metadata.get('level', 'unknown')
                    hours = metadata.get('hours', 'N/A')
                    description = metadata.get('description', f'{topic.capitalize()} course - {level} level - {hours} hours')
                    
                    # Count chapters for the default language (first available)
                    chapter_count = 0
                    languages = metadata.get('languages', ['en'])
                    if languages:
                        # Try to count chapters in the first available language file
                        for lang in languages:
                            lang_file = course_dir / f'{lang}.md'
                            if lang_file.exists():
                                try:
                                    content = lang_file.read_text(encoding='utf-8')
                                    chapters = self._extract_chapters_from_content(content, lang_file)
                                    chapter_count = len(chapters)
                                    break
                                except:
                                    pass
                    
                    courses.append({
                        'name': course_dir.name,
                        'title': title,
                        'description': description,
                        'path': str(course_dir),
                        'chapters': chapter_count,
                        'languages': languages,
                        'metadata': metadata
                    })
                except Exception as e:
                    # Course has invalid metadata, include with basic info
                    courses.append({
                        'name': course_dir.name,
                        'title': course_dir.name,
                        'description': f'Error reading metadata: {str(e)}',
                        'path': str(course_dir),
                        'chapters': 0,
                        'languages': ['en'],
                        'metadata': {}
                    })
            else:
                # Course without metadata
                courses.append({
                    'name': course_dir.name,
                    'title': course_dir.name,
                    'description': 'No course metadata found',
                    'path': str(course_dir),
                    'chapters': 0,
                    'languages': ['en'],
                    'metadata': {}
                })
                
        return sorted(courses, key=lambda x: x['name'])
    
    def list_chapters(self, repo_key: str, course_name: str, language: str = 'en') -> List[Dict[str, Any]]:
        """List chapters in a course for a specific language"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            return []
            
        # The language file is in the course folder: courses/{course_name}/{language}.md
        course_path = repo_path / 'courses' / course_name
        language_file = course_path / f'{language}.md'
        
        if not language_file.exists():
            # Fallback to English if requested language doesn't exist
            language_file = course_path / 'en.md'
            if not language_file.exists():
                return []
            
        chapters = []
        
        try:
            content = language_file.read_text(encoding='utf-8')
            chapters = self._extract_chapters_from_content(content, language_file)
        except Exception as e:
            print(f"Error reading {language_file}: {e}")
            return []
                
        return sorted(chapters, key=lambda x: x.get('order', 999))
    
    def list_languages(self, repo_key: str, course_name: str) -> List[str]:
        """List available languages for a course - based on {lang}.md files"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            return ['en']
            
        course_path = repo_path / 'courses' / course_name
        if not course_path.exists():
            return ['en']
            
        languages = []
        
        # Look for markdown files with language codes
        for md_file in course_path.glob('*.md'):
            # Extract language code from filename (e.g., 'en.md' -> 'en')
            lang_code = md_file.stem
            
            # Check if it's a valid language code (2-10 characters)
            # This allows codes like 'en', 'zh-Hans', 'nb-NO', 'sr-Latn'
            # Basic validation: starts with letter, contains only letters, hyphens, underscores
            if lang_code and (2 <= len(lang_code) <= 10) and lang_code[0].isalpha():
                languages.append(lang_code)
        
        # If no languages found, default to English
        if not languages:
            languages = ['en']
                    
        return sorted(languages)
    
    def _extract_chapters_from_content(self, content: str, file_path: Path) -> List[Dict[str, Any]]:
        """Extract chapters from markdown content - content is from <chapterId> line to next ##"""
        chapters = []
        lines = content.split('\n')
        
        # Find all ## headings and look for chapterId within the next few lines
        for i, line in enumerate(lines):
            if line.startswith('## '):
                title = line[3:].strip()  # Remove '## ' prefix
                chapter_id = None
                chapter_id_line = None
                
                # Look for <chapterId> within the next 5 lines
                for j in range(i + 1, min(i + 6, len(lines))):
                    if '<chapterId>' in lines[j] and '</chapterId>' in lines[j]:
                        # Extract chapter ID from the line
                        start = lines[j].find('<chapterId>') + len('<chapterId>')
                        end = lines[j].find('</chapterId>')
                        chapter_id = lines[j][start:end].strip()
                        chapter_id_line = j
                        break
                
                if chapter_id and chapter_id_line:
                    # Find where this chapter's content ends (next ## or end of file)
                    content_start = chapter_id_line  # Start from the chapterId line
                    content_end = len(lines)  # Default to end of file
                    
                    # Look for the next ## heading
                    for k in range(chapter_id_line + 1, len(lines)):
                        if lines[k].startswith('## '):
                            content_end = k
                            break
                    
                    # Extract chapter content (from chapterId line to next ##)
                    chapter_lines = lines[content_start:content_end]
                    chapter_content = '\n'.join(chapter_lines).strip()
                    
                    chapters.append({
                        'title': title,
                        'chapter_id': chapter_id,
                        'order': len(chapters),
                        'content': chapter_content,
                        'file_path': str(file_path) if file_path else None,
                        'word_count': len(chapter_content.split())
                    })
        
        return chapters
    
    def _initialize_quiz_generator(self, author: str = 'Course Ally', contributors: List[str] = None) -> QuizGenerator:
        """Initialize quiz generator with metadata"""
        if not self.quiz_generator:
            self.quiz_generator = QuizGenerator()
            
        self.quiz_generator.author = author
        self.quiz_generator.contributor_names = contributors or []
        
        return self.quiz_generator
    
    def _balance_difficulty(self, question_count: int, difficulty_proportions: Dict[str, float] = None) -> List[str]:
        """Calculate difficulty distribution for questions"""
        if not difficulty_proportions:
            difficulty_proportions = self.DEFAULT_DIFFICULTY_PROPORTIONS
            
        difficulties = []
        
        easy_count = max(1, round(question_count * difficulty_proportions['easy']))
        hard_count = max(1, round(question_count * difficulty_proportions['hard']))
        intermediate_count = question_count - easy_count - hard_count
        
        # Ensure we have at least one of each if question count allows
        if question_count >= 3:
            easy_count = max(1, easy_count)
            hard_count = max(1, hard_count)
            intermediate_count = max(1, intermediate_count)
            
            # Adjust if total exceeds question count
            total = easy_count + intermediate_count + hard_count
            if total > question_count:
                # Reduce intermediate first, then easy, then hard
                excess = total - question_count
                if intermediate_count > excess:
                    intermediate_count -= excess
                else:
                    easy_count = max(1, easy_count - (excess - max(0, intermediate_count - 1)))
                    intermediate_count = max(1, intermediate_count)
                    
        difficulties.extend(['easy'] * easy_count)
        difficulties.extend(['intermediate'] * intermediate_count) 
        difficulties.extend(['hard'] * hard_count)
        
        return difficulties[:question_count]
    
    def _get_next_quiz_number(self, repo_key: str, course_name: str) -> str:
        """Get the next available 3-digit quiz folder number"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            return "001"
            
        quizz_path = repo_path / 'courses' / course_name / 'quizz'
        
        if not quizz_path.exists():
            return "001"
        
        # Find existing numbered folders
        existing_numbers = []
        for item in quizz_path.iterdir():
            if item.is_dir() and item.name.isdigit() and len(item.name) == 3:
                existing_numbers.append(int(item.name))
        
        if not existing_numbers:
            return "001"
        
        # Return the next number after the highest existing one
        next_num = max(existing_numbers) + 1
        return f"{next_num:03d}"
    
    def _save_quiz_question(self, repo_key: str, course_name: str, question_data: Dict[str, Any], language: str = 'en') -> str:
        """Save a quiz question to the repository structure"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")
        
        # Create quizz directory if it doesn't exist
        quizz_path = repo_path / 'courses' / course_name / 'quizz'
        quizz_path.mkdir(parents=True, exist_ok=True)
        
        # Get the next available folder number
        folder_num = self._get_next_quiz_number(repo_key, course_name)
        question_dir = quizz_path / folder_num
        question_dir.mkdir(exist_ok=True)
        
        # Save metadata (question.yml)
        metadata_file = question_dir / 'question.yml'
        with open(metadata_file, 'w', encoding='utf-8') as f:
            f.write(f"id: {question_data.get('id', str(uuid.uuid4()))}\n")
            f.write(f"chapterId: {question_data.get('chapter_id', '')}\n")
            f.write(f"difficulty: {question_data.get('difficulty', 'intermediate')}\n")
            f.write(f"duration: {question_data.get('duration', 30)}\n")
            f.write(f"author: {question_data.get('author', 'Course Ally')}\n")
            f.write(f"original_language: en\n")
            f.write(f"proofreading:\n")
            f.write(f"  - language: en\n")
            f.write(f"    last_contribution_date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"    urgency: 1\n")
            f.write(f"    contributor_names:\n")
            
            # Add contributor names if available
            contributor = question_data.get('author', 'Course Ally')
            f.write(f"    - {contributor}\n")
            
            f.write(f"    reward: 1\n")
        
        # Save content ({language}.yml) with proper field order and formatting
        content_file = question_dir / f'{language}.yml'
        with open(content_file, 'w', encoding='utf-8') as f:
            # Write fields in the desired order
            # Question - single line
            question = question_data.get('question', '')
            f.write(f"question: {question}\n")
            
            # Answer - single line
            answer = question_data.get('answer', '')
            f.write(f"answer: {answer}\n")
            
            # Wrong answers - one per line with 2-space indentation
            f.write("wrong_answers:\n")
            wrong_answers = question_data.get('wrong_answers', [])
            for wrong_answer in wrong_answers:
                # Escape quotes if needed
                if "'" in wrong_answer and '"' not in wrong_answer:
                    f.write(f'  - "{wrong_answer}"\n')
                elif '"' in wrong_answer and "'" not in wrong_answer:
                    f.write(f"  - '{wrong_answer}'\n")
                elif "'" in wrong_answer and '"' in wrong_answer:
                    # Use literal style for complex quotes
                    escaped = wrong_answer.replace("'", "''")
                    f.write(f"  - '{escaped}'\n")
                else:
                    f.write(f"  - {wrong_answer}\n")
            
            # Explanation - use literal style for multi-line
            explanation = question_data.get('explanation', '')
            if '\n' in explanation or len(explanation) > 80:
                # Use literal style for multi-line explanations
                f.write("explanation: |\n")
                for line in explanation.split('\n'):
                    f.write(f"  {line}\n")
            else:
                # Single line explanation
                if "'" in explanation and '"' not in explanation:
                    f.write(f'explanation: "{explanation}"\n')
                elif '"' in explanation and "'" not in explanation:
                    f.write(f"explanation: '{explanation}'\n")
                else:
                    f.write(f"explanation: {explanation}\n")
        
        return folder_num
    
    def generate_quiz(
        self,
        repo_key: str,
        course_name: str,
        chapter_ids: List[str],
        language: str = 'en',
        question_count: int = 5,
        difficulty_proportions: Dict[str, float] = None,
        author: str = 'Course Ally',
        contributors: List[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generate quiz questions with progress updates
        
        Args:
            repo_key: Repository key (BEC_REPO, PREMIUM_REPO)
            course_name: Name of the course
            chapter_ids: List of chapter IDs to include
            language: Language code (default 'en')
            question_count: Total number of questions to generate
            difficulty_proportions: Dict with easy/intermediate/hard proportions
            author: Quiz author name
            contributors: List of contributor names
            progress_callback: Function to call with progress updates
            
        Yields:
            Dict with status, message, percentage, and data
        """
        try:
            if progress_callback:
                progress_callback("Initializing quiz generator...", "processing", 5)
            yield {"status": "processing", "message": "Initializing quiz generator...", "percentage": 5}
            
            # Initialize quiz generator
            generator = self._initialize_quiz_generator(author, contributors)
            
            if progress_callback:
                progress_callback("Loading course chapters...", "processing", 10)
            yield {"status": "processing", "message": "Loading course chapters...", "percentage": 10}
            
            # Get all chapters for the course
            all_chapters = self.list_chapters(repo_key, course_name, language)
            
            # Filter to requested chapter IDs
            selected_chapters = [ch for ch in all_chapters if ch['chapter_id'] in chapter_ids]
            
            if not selected_chapters:
                error_msg = f"No chapters found for IDs: {chapter_ids}"
                if progress_callback:
                    progress_callback(error_msg, "error", 100)
                yield {"status": "error", "message": error_msg, "percentage": 100}
                return
                
            # Check if chapters have content - if not, this indicates we need different approach
            chapters_with_content = [ch for ch in selected_chapters if ch.get('content') and len(ch['content']) > 100]
            
            if not chapters_with_content:
                # Fallback: try to generate from existing quiz files only
                if progress_callback:
                    progress_callback("No chapter content available - using existing quiz files only", "processing", 25)
                yield {
                    "status": "processing", 
                    "message": "No chapter content available - using existing quiz files only", 
                    "percentage": 25,
                    "data": {"fallback_mode": True}
                }
                selected_chapters = selected_chapters  # Use chapters without content for existing quiz loading
            else:
                selected_chapters = chapters_with_content
                
            if progress_callback:
                progress_callback(f"Found {len(selected_chapters)} chapters", "processing", 20)
            yield {
                "status": "processing", 
                "message": f"Found {len(selected_chapters)} chapters", 
                "percentage": 20,
                "data": {"chapters_found": len(selected_chapters)}
            }
            
            # Calculate difficulty distribution for ALL questions (question_count * chapters)
            total_questions = question_count * len(selected_chapters)
            difficulties = self._balance_difficulty(total_questions, difficulty_proportions)
            
            if progress_callback:
                progress_callback(f"Generating {total_questions} questions ({question_count} per chapter) with balanced difficulty", "processing", 30)
            yield {
                "status": "processing",
                "message": f"Generating {total_questions} questions ({question_count} per chapter) with balanced difficulty",
                "percentage": 30,
                "data": {
                    "difficulty_distribution": {
                        "easy": difficulties.count('easy'),
                        "intermediate": difficulties.count('intermediate'),
                        "hard": difficulties.count('hard')
                    }
                }
            }
            
            # Generate questions - question_count for EACH chapter
            all_questions = []
            questions_per_chapter = question_count  # Generate requested number for each chapter
            
            for i, chapter in enumerate(selected_chapters):
                chapter_start_percentage = 30 + (i / len(selected_chapters)) * 50
                chapter_end_percentage = 30 + ((i + 1) / len(selected_chapters)) * 50
                
                if progress_callback:
                    progress_callback(f"Processing chapter: {chapter['title']}", "processing", chapter_start_percentage)
                yield {
                    "status": "processing",
                    "message": f"Processing chapter: {chapter['title']}",
                    "percentage": chapter_start_percentage,
                    "data": {"current_chapter": chapter['title']}
                }
                
                # Each chapter gets the requested number of questions
                chapter_question_count = questions_per_chapter
                
                # Get difficulties for this chapter
                chapter_start_idx = i * questions_per_chapter
                chapter_end_idx = chapter_start_idx + chapter_question_count
                chapter_difficulties = difficulties[chapter_start_idx:chapter_end_idx]
                
                # Get quizz path for incremental saving
                repo_path = self._get_repo_path(repo_key)
                quizz_path = repo_path / 'courses' / course_name / 'quizz'
                quizz_path.mkdir(parents=True, exist_ok=True)
                
                # Generate new questions for each difficulty with incremental saving
                for q_idx, difficulty in enumerate(chapter_difficulties):
                    question_percentage = chapter_start_percentage + (q_idx / len(chapter_difficulties)) * (chapter_end_percentage - chapter_start_percentage)
                    
                    try:
                        # Check if we have chapter content for generation
                        has_content = 'content' in chapter and chapter['content'] and len(chapter['content']) > 100
                        
                        if not has_content:
                            # Skip generation but continue with existing questions if available
                            existing_questions = generator._load_existing_questions_for_chapter(quizz_path, chapter['chapter_id'])
                            if len(existing_questions) == 0:
                                if progress_callback:
                                    progress_callback(f"Skipping chapter {chapter['title']} - no content or existing questions", "warning", question_percentage)
                                yield {
                                    "status": "warning",
                                    "message": f"Skipping chapter {chapter['title']} - no content or existing questions",
                                    "percentage": question_percentage
                                }
                            continue
                            
                        # Load existing questions for this chapter to avoid duplicates
                        existing_questions = generator._load_existing_questions_for_chapter(quizz_path, chapter['chapter_id'])
                        
                        if progress_callback:
                            existing_count = len(existing_questions)
                            if existing_count > 0:
                                progress_callback(f"Found {existing_count} existing questions for chapter {chapter['chapter_id']}", "processing", question_percentage)
                        
                        # Generate quiz with duplicate avoidance
                        question_data = generator._generate_quiz_with_claude_avoiding_duplicates(
                            chapter['content'],
                            chapter['title'], 
                            difficulty,
                            existing_questions
                        )
                        
                        if question_data:
                            # Add metadata to question
                            enhanced_question = {
                                **question_data,
                                'id': str(uuid.uuid4()),
                                'chapter_id': chapter['chapter_id'],
                                'chapter_title': chapter['title'],
                                'difficulty': difficulty,
                                'question_number': len(all_questions) + 1,
                                'duration': generator._get_duration_for_difficulty(difficulty),
                                'generated_at': datetime.now().isoformat(),
                                'source': 'generated'
                            }
                            
                            # Save immediately to avoid loss and enable duplicate detection
                            folder_num = self._save_quiz_question(
                                repo_key=repo_key,
                                course_name=course_name,
                                question_data={
                                    'id': enhanced_question.get('id'),
                                    'chapter_id': enhanced_question.get('chapter_id'),
                                    'difficulty': enhanced_question.get('difficulty'),
                                    'duration': enhanced_question.get('duration'),
                                    'author': author,
                                    'question': enhanced_question.get('question'),
                                    'answer': enhanced_question.get('answer'),
                                    'wrong_answers': enhanced_question.get('wrong_answers'),
                                    'explanation': enhanced_question.get('explanation')
                                },
                                language=language
                            )
                            
                            enhanced_question['saved_folder'] = folder_num
                            all_questions.append(enhanced_question)
                            
                            if progress_callback:
                                progress_callback(f"Generated and saved question {len(all_questions)}/{total_questions} to folder {folder_num}", "processing", question_percentage)
                            yield {
                                "status": "processing",
                                "message": f"Generated and saved question {len(all_questions)}/{total_questions} to folder {folder_num}",
                                "percentage": question_percentage,
                                "data": {"questions_generated": len(all_questions), "saved_to": folder_num}
                            }
                        else:
                            if progress_callback:
                                progress_callback(f"Failed to generate question {len(all_questions) + 1}", "warning", question_percentage)
                            yield {
                                "status": "warning",
                                "message": f"Failed to generate question {len(all_questions) + 1}",
                                "percentage": question_percentage
                            }
                            
                    except Exception as e:
                        error_msg = f"Error generating question: {str(e)}"
                        if progress_callback:
                            progress_callback(error_msg, "warning", question_percentage)
                        yield {
                            "status": "warning",
                            "message": error_msg,
                            "percentage": question_percentage
                        }
                        continue
                            
                        question_data = generator._generate_quiz_with_claude(
                            chapter['content'],
                            chapter['title'], 
                            difficulty,
                            len(all_questions) + 1
                        )
                        
                        if question_data:
                            # Add metadata to question
                            enhanced_question = {
                                **question_data,
                                'id': str(uuid.uuid4()),
                                'chapter_id': chapter['chapter_id'],
                                'chapter_title': chapter['title'],
                                'difficulty': difficulty,
                                'question_number': len(all_questions) + 1,
                                'duration': generator._get_duration_for_difficulty(difficulty),
                                'generated_at': datetime.now().isoformat(),
                                'source': 'generated'
                            }
                            
                            all_questions.append(enhanced_question)
                            
                            if progress_callback:
                                progress_callback(f"Generated question {len(all_questions)}/{total_questions}", "processing", question_percentage)
                            yield {
                                "status": "processing",
                                "message": f"Generated question {len(all_questions)}/{total_questions}",
                                "percentage": question_percentage,
                                "data": {"questions_generated": len(all_questions)}
                            }
                        else:
                            if progress_callback:
                                progress_callback(f"Failed to generate question {len(all_questions) + 1}", "warning", question_percentage)
                            yield {
                                "status": "warning",
                                "message": f"Failed to generate question {len(all_questions) + 1}",
                                "percentage": question_percentage
                            }
                            
                    except Exception as e:
                        error_msg = f"Error generating question: {str(e)}"
                        if progress_callback:
                            progress_callback(error_msg, "warning", question_percentage)
                        yield {
                            "status": "warning",
                            "message": error_msg,
                            "percentage": question_percentage
                        }
                        continue
                
                # Break if we have enough questions
                # Don't break early - continue generating for all chapters
            
            if not all_questions:
                error_msg = "No questions were generated successfully"
                if progress_callback:
                    progress_callback(error_msg, "error", 100)
                yield {"status": "error", "message": error_msg, "percentage": 100}
                return
            
            if progress_callback:
                progress_callback("Formatting quiz data...", "processing", 85)
            yield {"status": "processing", "message": "Formatting quiz data...", "percentage": 85}
            
            # Create quiz metadata
            quiz_metadata = {
                'title': f"{course_name.replace('_', ' ').title()} Quiz",
                'description': f"Quiz generated from {len(selected_chapters)} chapters",
                'author': author,
                'contributors': contributors or [],
                'language': language,
                'repository': repo_key,
                'course': course_name,
                'chapters': [ch['chapter_id'] for ch in selected_chapters],
                'question_count': len(all_questions),
                'difficulty_distribution': {
                    'easy': sum(1 for q in all_questions if q.get('difficulty') == 'easy'),
                    'intermediate': sum(1 for q in all_questions if q.get('difficulty') == 'intermediate'),
                    'hard': sum(1 for q in all_questions if q.get('difficulty') == 'hard')
                },
                'generated_at': datetime.now().isoformat(),
                'generator_version': '2.0.0'
            }
            
            # Questions already saved incrementally, no need to save again
            if progress_callback:
                progress_callback("All questions have been saved incrementally", "processing", 95)
            
            yield {
                        "status": "warning",
                        "message": error_msg,
                        "percentage": 95
                    }
            
            success_msg = f"Successfully generated {len(all_questions)} questions"
            if progress_callback:
                progress_callback(success_msg, "success", 100)
            yield {
                "status": "success",
                "message": success_msg,
                "percentage": 100,
                "data": {
                    "quiz_metadata": quiz_metadata,
                    "questions_generated": len(all_questions),
                    "saved_folders": saved_folders,
                    "repository_path": str(self._get_repo_path(repo_key) / 'courses' / course_name / 'quizz')
                }
            }
            
        except Exception as e:
            error_msg = f"Quiz generation failed: {str(e)}"
            if progress_callback:
                progress_callback(error_msg, "error", 100)
            yield {"status": "error", "message": error_msg, "percentage": 100}
    
