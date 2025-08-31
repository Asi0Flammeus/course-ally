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
                    
                    courses.append({
                        'name': course_dir.name,
                        'title': title,
                        'description': description,
                        'path': str(course_dir),
                        'languages': metadata.get('languages', ['en']),
                        'metadata': metadata
                    })
                except Exception as e:
                    # Course has invalid metadata, include with basic info
                    courses.append({
                        'name': course_dir.name,
                        'title': course_dir.name,
                        'description': f'Error reading metadata: {str(e)}',
                        'path': str(course_dir),
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
        """Extract chapters from markdown content"""
        chapters = []
        lines = content.split('\n')
        
        # Find all ## headings and look for chapterId within the next few lines
        for i, line in enumerate(lines):
            if line.startswith('## '):
                title = line[3:].strip()  # Remove '## ' prefix
                chapter_id = None
                
                # Look for <chapterId> within the next 5 lines
                for j in range(i + 1, min(i + 6, len(lines))):
                    if '<chapterId>' in lines[j] and '</chapterId>' in lines[j]:
                        # Extract chapter ID from the line
                        start = lines[j].find('<chapterId>') + len('<chapterId>')
                        end = lines[j].find('</chapterId>')
                        chapter_id = lines[j][start:end].strip()
                        break
                
                if chapter_id:
                    chapters.append({
                        'title': title,
                        'chapter_id': chapter_id,
                        'order': len(chapters)
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
                
            if progress_callback:
                progress_callback(f"Found {len(selected_chapters)} chapters", "processing", 20)
            yield {
                "status": "processing", 
                "message": f"Found {len(selected_chapters)} chapters", 
                "percentage": 20,
                "data": {"chapters_found": len(selected_chapters)}
            }
            
            # Calculate difficulty distribution
            difficulties = self._balance_difficulty(question_count, difficulty_proportions)
            
            if progress_callback:
                progress_callback(f"Generating {question_count} questions with balanced difficulty", "processing", 30)
            yield {
                "status": "processing",
                "message": f"Generating {question_count} questions with balanced difficulty",
                "percentage": 30,
                "data": {
                    "difficulty_distribution": {
                        "easy": difficulties.count('easy'),
                        "intermediate": difficulties.count('intermediate'),
                        "hard": difficulties.count('hard')
                    }
                }
            }
            
            # Generate questions
            all_questions = []
            questions_per_chapter = max(1, question_count // len(selected_chapters))
            
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
                
                # Determine how many questions to generate for this chapter
                remaining_questions = question_count - len(all_questions)
                remaining_chapters = len(selected_chapters) - i
                
                if remaining_chapters == 1:
                    # Last chapter gets all remaining questions
                    chapter_question_count = remaining_questions
                else:
                    chapter_question_count = min(questions_per_chapter, remaining_questions)
                
                # Generate questions for this chapter
                chapter_difficulties = difficulties[len(all_questions):len(all_questions) + chapter_question_count]
                
                for q_idx, difficulty in enumerate(chapter_difficulties):
                    question_percentage = chapter_start_percentage + (q_idx / len(chapter_difficulties)) * (chapter_end_percentage - chapter_start_percentage)
                    
                    try:
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
                                'generated_at': datetime.now().isoformat()
                            }
                            
                            all_questions.append(enhanced_question)
                            
                            if progress_callback:
                                progress_callback(f"Generated question {len(all_questions)}/{question_count}", "processing", question_percentage)
                            yield {
                                "status": "processing",
                                "message": f"Generated question {len(all_questions)}/{question_count}",
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
                if len(all_questions) >= question_count:
                    break
            
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
            
            if progress_callback:
                progress_callback("Saving quiz files...", "processing", 90)
            yield {"status": "processing", "message": "Saving quiz files...", "percentage": 90}
            
            # Save quiz files
            output_path = self._save_quiz_files(
                quiz_metadata=quiz_metadata,
                questions=all_questions,
                repo_key=repo_key,
                course_name=course_name,
                language=language
            )
            
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
                    "output_path": str(output_path),
                    "files_created": [
                        str(output_path / f"{course_name}_quiz_metadata.yml"),
                        str(output_path / f"{course_name}_quiz_questions.yml")
                    ]
                }
            }
            
        except Exception as e:
            error_msg = f"Quiz generation failed: {str(e)}"
            if progress_callback:
                progress_callback(error_msg, "error", 100)
            yield {"status": "error", "message": error_msg, "percentage": 100}
    
    def _save_quiz_files(
        self,
        quiz_metadata: Dict[str, Any],
        questions: List[Dict[str, Any]],
        repo_key: str,
        course_name: str,
        language: str
    ) -> Path:
        """Save quiz files in the proper directory structure"""
        
        # Create output directory structure
        base_path = Path('outputs') / 'quizz' / repo_key.lower() / course_name
        if language != 'en':
            base_path = base_path / language
            
        base_path.mkdir(parents=True, exist_ok=True)
        
        # Save metadata file
        metadata_file = base_path / f"{course_name}_quiz_metadata.yml"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            yaml.dump(quiz_metadata, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # Save questions file
        questions_file = base_path / f"{course_name}_quiz_questions.yml"
        with open(questions_file, 'w', encoding='utf-8') as f:
            yaml.dump({'questions': questions}, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return base_path