import yaml
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import anthropic
import os
from dotenv import load_dotenv
import re

load_dotenv()

class QuizGenerator:
    """Generator for creating quiz questions from chapter content using Claude."""
    
    def __init__(self, language: str = "en"):
        """Initialize the quiz generator with Claude API.
        
        Args:
            language: Language code for quiz generation (e.g., 'en', 'fr', 'es').
        """
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.author = None
        self.contributor_names = []
        self.language = language

    def _get_language_name(self, code: str) -> str:
        """Convert language code to full language name."""
        language_map = {
            "en": "English",
            "fr": "French",
            "es": "Spanish",
            "de": "German",
            "it": "Italian",
            "pt": "Portuguese",
            "ru": "Russian",
            "ja": "Japanese",
            "ko": "Korean",
            "zh-Hans": "Simplified Chinese",
            "zh-Hant": "Traditional Chinese",
            "ar": "Arabic",
            "hi": "Hindi",
            "cs": "Czech",
            "nl": "Dutch",
            "pl": "Polish",
            "tr": "Turkish",
            "vi": "Vietnamese",
            "id": "Indonesian",
            "fi": "Finnish",
            "sv": "Swedish",
            "nb-NO": "Norwegian",
            "et": "Estonian",
            "fa": "Persian",
            "rn": "Kirundi",
            "si": "Sinhala",
            "sw": "Swahili",
            "sr-Latn": "Serbian (Latin)",
        }
        return language_map.get(code, code)
    
    def collect_metadata(self) -> None:
        """Collect author and contributor information interactively."""
        print("\n" + "="*50)
        print("📝 QUIZ METADATA COLLECTION")
        print("="*50)
        
        # Get author name
        while not self.author:
            author_input = input("\nEnter author name (required): ").strip()
            if author_input:
                self.author = author_input
            else:
                print("❌ Author name cannot be empty")
        
        # Get contributor names
        print("\nEnter contributor names (comma-separated, or press Enter to skip):")
        contributor_input = input("Contributors: ").strip()
        
        if contributor_input:
            # Split by comma and clean up names
            self.contributor_names = [name.strip() for name in contributor_input.split(',') if name.strip()]
        else:
            self.contributor_names = []
        
        print(f"\n✅ Author: {self.author}")
        print(f"✅ Contributors: {self.contributor_names if self.contributor_names else 'None'}")
        print("="*50)
    
    def generate_quizzes_from_file(self, chapter_file: Path, chapter_id: Optional[str] = None, quizz_output_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """
        Generate multiple quiz questions from a chapter file (4 easy, 4 intermediate, 4 hard).
        Uses incremental generation with immediate saving to avoid duplicates.
        
        Args:
            chapter_file: Path to the chapter markdown file
            chapter_id: Optional chapter ID to associate with the quiz
            quizz_output_path: Optional path to quizz directory for incremental saving
            
        Returns:
            List of dictionaries containing quiz data
        """
        # Read chapter content
        try:
            chapter_content = chapter_file.read_text(encoding='utf-8')
        except Exception as e:
            raise Exception(f"Error reading chapter file: {e}")
        
        # Extract chapter ID from content using <chapterId> tag
        if not chapter_id:
            chapter_id = self._extract_chapter_id(chapter_content)
        
        all_quizzes = []
        difficulties = ['easy', 'intermediate', 'hard']
        questions_per_difficulty = 4
        
        for difficulty in difficulties:
            for i in range(questions_per_difficulty):
                try:
                    if quizz_output_path:
                        # Use incremental generation with duplicate avoidance
                        quiz_data = self.generate_quiz_incrementally(
                            chapter_file,
                            quizz_output_path,
                            difficulty,
                            chapter_id
                        )
                    else:
                        # Fallback to old method if no output path provided
                        # Load existing questions to avoid duplicates even in fallback mode
                        existing_questions = []
                        quiz_data = self._generate_quiz_with_claude_avoiding_duplicates(
                            chapter_content, 
                            chapter_file.stem, 
                            difficulty,
                            existing_questions
                        )
                        
                        # Add metadata
                        quiz_data['id'] = str(uuid.uuid4())
                        quiz_data['chapterId'] = chapter_id
                        quiz_data['difficulty'] = difficulty
                        quiz_data['duration'] = self._get_duration_for_difficulty(difficulty)
                        quiz_data['author'] = self.author or 'Course-Ally'
                        quiz_data['original_language'] = 'en'
                    
                    all_quizzes.append(quiz_data)
                    print(f"✅ Generated and saved {difficulty} question {i+1}/4 for chapter {chapter_id}")
                    
                except Exception as e:
                    print(f"⚠️  Warning: Failed to generate {difficulty} question {i+1}: {e}")
                    continue
        
        return all_quizzes

    def generate_quiz_incrementally(self, chapter_file: Path, quizz_output_path: Path, difficulty: str, chapter_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a single quiz question incrementally, checking for existing questions to avoid duplicates.
        
        Args:
            chapter_file: Path to the chapter markdown file
            quizz_output_path: Path to the quizz directory where questions are saved
            difficulty: Difficulty level ('easy', 'intermediate', 'hard')
            chapter_id: Optional chapter ID to associate with the quiz
            
        Returns:
            Dictionary containing the generated quiz data
        """
        # Read chapter content
        try:
            chapter_content = chapter_file.read_text(encoding='utf-8')
        except Exception as e:
            raise Exception(f"Error reading chapter file: {e}")
        
        # Extract chapter ID from content using <chapterId> tag
        if not chapter_id:
            chapter_id = self._extract_chapter_id(chapter_content)
        
        # Load existing questions for this chapter to avoid duplicates
        existing_questions = self._load_existing_questions_for_chapter(quizz_output_path, chapter_id, self.language)
        
        # Generate quiz using Claude with existing questions context
        quiz_data = self._generate_quiz_with_claude_avoiding_duplicates(
            chapter_content, 
            chapter_file.stem, 
            difficulty, 
            existing_questions
        )
        
        # Add metadata
        quiz_data['id'] = str(uuid.uuid4())
        quiz_data['chapterId'] = chapter_id
        quiz_data['difficulty'] = difficulty
        quiz_data['duration'] = self._get_duration_for_difficulty(difficulty)
        quiz_data['author'] = self.author or 'Course-Ally'
        quiz_data['original_language'] = 'en'
        
        # Get next quiz number and save immediately
        existing_quizzes = [d for d in quizz_output_path.iterdir() if d.is_dir() and d.name.isdigit()]
        existing_numbers = [int(d.name) for d in existing_quizzes]
        next_number = max(existing_numbers, default=0) + 1
        quiz_number_str = f"{next_number:03d}"
        
        # Save the quiz immediately
        self.save_quiz_files(quiz_data, quizz_output_path, quiz_number_str)
        
        return quiz_data
    
    def _get_duration_for_difficulty(self, difficulty: str) -> int:
        """Get duration in seconds based on difficulty."""
        durations = {
            'easy': 15,
            'intermediate': 30,
            'hard': 45
        }
        return durations.get(difficulty, 30)
    
    def _extract_chapter_id(self, content: str) -> Optional[str]:
        """Extract chapter ID from chapter content using <chapterId> tag."""
        # Look for <chapterId>...</chapterId> pattern
        match = re.search(r'<chapterId>\s*([^<]+?)\s*</chapterId>', content)
        if match:
            return match.group(1).strip()
        return None

    def _load_existing_questions_for_chapter(self, quizz_path: Path, chapter_id: str, language: str = 'en') -> List[Dict[str, str]]:
        """
        Load existing questions for a specific chapter from the quizz directory.
        
        Args:
            quizz_path: Path to the quizz directory
            chapter_id: The chapter ID to filter questions by
            language: Language code to load questions from (default 'en')
            
        Returns:
            List of dictionaries containing question text and difficulty level
        """
        existing_questions = []
        
        if not quizz_path.exists():
            return existing_questions
            
        # Iterate through all quiz folders (numbered directories)
        for quiz_folder in quizz_path.iterdir():
            if not quiz_folder.is_dir() or not quiz_folder.name.isdigit():
                continue
                
            # Read question.yml to get chapter ID and difficulty
            question_yml = quiz_folder / 'question.yml'
            if not question_yml.exists():
                continue
                
            try:
                with open(question_yml, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Extract chapterId and difficulty
                chapter_match = re.search(r'^chapterId:\s*(.+)$', content, re.MULTILINE)
                difficulty_match = re.search(r'^difficulty:\s*(.+)$', content, re.MULTILINE)
                
                if not chapter_match or chapter_match.group(1).strip() != chapter_id:
                    continue
                    
                difficulty = difficulty_match.group(1).strip() if difficulty_match else 'unknown'
                
                # Try to read the language-specific file first, then fall back to en.yml
                lang_yml = quiz_folder / f'{language}.yml'
                if not lang_yml.exists():
                    # Fall back to English if target language doesn't exist
                    lang_yml = quiz_folder / 'en.yml'
                    if not lang_yml.exists():
                        continue
                    
                with open(lang_yml, 'r', encoding='utf-8') as f:
                    lang_content = f.read()
                    
                # Extract question text
                question_match = re.search(r'^question:\s*(.+)$', lang_content, re.MULTILINE)
                if question_match:
                    question_text = question_match.group(1).strip()
                    existing_questions.append({
                        'question': question_text,
                        'difficulty': difficulty
                    })
                    
            except Exception as e:
                print(f"⚠️  Warning: Error reading quiz {quiz_folder.name}: {e}")
                continue
                
        return existing_questions
    
    def _generate_quiz_with_claude(self, chapter_content: str, chapter_name: str, difficulty: str, question_number: int) -> Dict[str, Any]:
        """Generate quiz questions using Claude."""
        
        language_name = self._get_language_name(self.language)
        
        difficulty_instructions = {
            'easy': """
- Focus on basic concepts and definitions
- Test recall of fundamental information
- Use straightforward language
- Target key terms and simple relationships""",
            'intermediate': """
- Test understanding of relationships between concepts
- Require application of knowledge to scenarios
- Focus on processes and procedures
- Test comprehension beyond basic recall""",
            'hard': """
- Test analysis and synthesis of complex concepts
- Require critical thinking and evaluation
- Focus on edge cases and nuanced understanding
- Test ability to apply knowledge to novel situations"""
        }
        
        prompt = f"""Based on the following chapter content, create a {difficulty} multiple-choice quiz question #{question_number}.

IMPORTANT: Generate the question, all answers, and explanation in {language_name}. The entire quiz content MUST be in {language_name}.

Chapter: {chapter_name}

Content:
{chapter_content}

Requirements for {difficulty} difficulty:
{difficulty_instructions[difficulty]}

Generate a quiz question with:
1. A clear, single-line question (no line breaks) - in {language_name}
2. One correct answer (single line) - in {language_name}
3. Three wrong answers that are plausible but clearly incorrect (each on single line) - in {language_name}
4. A 50-word explanation that provide argument why it's true, or reformulate the concept to ease the understanding - in {language_name}

IMPORTANT:
- ALL content must be in {language_name}
- Keep question and answers on single lines (no line breaks within them)
- Wrong answers should be believable but definitively incorrect
- Correct and wrong answer should be roughly the same length
- Explanation should thoroughly explain why the correct answer is right and others are wrong
- For the chapter content provided, focus on key concepts that appear in the material
- The question should be self-sufficient and MUST NOT have reference to the chapter itself, like "seen in the current chapter"

Return ONLY a JSON object in this exact format:
{{
    "question": "Your single-line question here in {language_name}?",
    "answer": "The correct answer in {language_name}",
    "wrong_answers": [
        "First wrong answer in {language_name}",
        "Second wrong answer in {language_name}",
        "Third wrong answer in {language_name}"
    ],
    "explanation": "Detailed explanation in {language_name}. Can be multiple sentences and paragraphs."
}}
"""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=20000,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
                
                # Clean up any line breaks in question and answers
                quiz_data['question'] = ' '.join(quiz_data['question'].split())
                quiz_data['answer'] = ' '.join(quiz_data['answer'].split())
                quiz_data['wrong_answers'] = [' '.join(ans.split()) for ans in quiz_data['wrong_answers']]
                
                return quiz_data
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            print(f"⚠️  Error generating quiz: {e}")
            # Return a fallback quiz
            return {
                "question": f"What is a key concept from {chapter_name}?",
                "answer": "The main concept discussed in the chapter",
                "wrong_answers": [
                    "An unrelated concept",
                    "A different topic",
                    "An incorrect statement"
                ],
                "explanation": "This is a placeholder question. The actual content should be based on the chapter material."
            }

    def _generate_quiz_with_claude_avoiding_duplicates(self, chapter_content: str, chapter_name: str, difficulty: str, existing_questions: List[Dict[str, str]]) -> Dict[str, Any]:
        """Generate quiz questions using Claude while avoiding duplicates."""
        
        language_name = self._get_language_name(self.language)
        
        difficulty_instructions = {
            'easy': """
- Focus on basic concepts and definitions
- Test recall of fundamental information
- Use straightforward language
- Target key terms and simple relationships""",
            'intermediate': """
- Test understanding of relationships between concepts
- Require application of knowledge to scenarios
- Focus on processes and procedures
- Test comprehension beyond basic recall""",
            'hard': """
- Test analysis and synthesis of complex concepts
- Require critical thinking and evaluation
- Focus on edge cases and nuanced understanding
- Test ability to apply knowledge to novel situations"""
        }
        
        # Format existing questions for the prompt
        existing_questions_text = ""
        if existing_questions:
            questions_by_difficulty = {}
            for q in existing_questions:
                diff = q['difficulty']
                if diff not in questions_by_difficulty:
                    questions_by_difficulty[diff] = []
                questions_by_difficulty[diff].append(q['question'])
            
            existing_questions_text = "\n\nEXISTING QUESTIONS FOR THIS CHAPTER (AVOID CREATING SIMILAR OR IDENTICAL QUESTIONS):\n"
            for diff_level, questions in questions_by_difficulty.items():
                existing_questions_text += f"\n{diff_level.capitalize()} difficulty:\n"
                for i, question in enumerate(questions, 1):
                    existing_questions_text += f"  {i}. {question}\n"
        
        prompt = f"""Based on the following chapter content, create a {difficulty} multiple-choice quiz question.

IMPORTANT: Generate the question, all answers, and explanation in {language_name}. The entire quiz content MUST be in {language_name}.

Chapter: {chapter_name}

Content:
{chapter_content}

Requirements for {difficulty} difficulty:
{difficulty_instructions[difficulty]}
{existing_questions_text}

Generate a quiz question with:
1. A clear, single-line question (no line breaks) - in {language_name}
2. One correct answer (single line) - in {language_name}
3. Three wrong answers that are plausible but clearly incorrect (each on single line) - in {language_name}
4. A 50-word explanation that provide argument why it's true, or reformulate the concept to ease the understanding - in {language_name}

IMPORTANT:
- ALL content must be in {language_name}
- Keep question and answers on single lines (no line breaks within them)
- Wrong answers should be believable but definitively incorrect
- Correct and wrong answer should be roughly the same length
- Explanation should thoroughly explain why the correct answer is right and others are wrong
- For the chapter content provided, focus on key concepts that appear in the material
- The question should be self-sufficient and MUST NOT have reference to the chapter itself, like "seen in the current chapter"
- AVOID creating questions similar to the existing questions listed above
- Create a UNIQUE question that tests a different aspect of the material

Return ONLY a JSON object in this exact format:
{{
    "question": "Your single-line question here in {language_name}?",
    "answer": "The correct answer in {language_name}",
    "wrong_answers": [
        "First wrong answer in {language_name}",
        "Second wrong answer in {language_name}",
        "Third wrong answer in {language_name}"
    ],
    "explanation": "Detailed explanation in {language_name}. Can be multiple sentences and paragraphs."
}}
"""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=20000,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                quiz_data = json.loads(json_match.group())
                
                # Clean up any line breaks in question and answers
                quiz_data['question'] = ' '.join(quiz_data['question'].split())
                quiz_data['answer'] = ' '.join(quiz_data['answer'].split())
                quiz_data['wrong_answers'] = [' '.join(ans.split()) for ans in quiz_data['wrong_answers']]
                
                return quiz_data
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            print(f"⚠️  Error generating quiz: {e}")
            # Return a fallback quiz
            return {
                "question": f"What is a key concept from {chapter_name}?",
                "answer": "The main concept discussed in the chapter",
                "wrong_answers": [
                    "An unrelated concept",
                    "A different topic",
                    "An incorrect statement"
                ],
                "explanation": "This is a placeholder question. The actual content should be based on the chapter material."
            }
    
    def save_quiz_files(self, quiz_data: Dict[str, Any], output_dir: Path, quiz_number: str) -> None:
        """
        Save quiz files in the required format with proper YAML formatting.
        
        Args:
            quiz_data: Quiz data dictionary
            output_dir: Output directory for quiz files
            quiz_number: Quiz number (e.g., "001")
        """
        quiz_dir = output_dir / quiz_number
        quiz_dir.mkdir(parents=True, exist_ok=True)
        
        # Create question.yml (metadata)
        today_date = datetime.now().strftime('%Y-%m-%d')
        
        question_data = {
            'id': quiz_data['id'],
            'chapterId': quiz_data['chapterId'],
            'difficulty': quiz_data['difficulty'],
            'duration': quiz_data['duration'],
            'author': quiz_data['author'],
            'original_language': quiz_data['original_language'],
            'proofreading': [
                {
                    'language': 'en',
                    'last_contribution_date': today_date,
                    'urgency': 1,
                    'contributor_names': self.contributor_names or [],
                    'reward': 1
                }
            ]
        }
        
        question_file = quiz_dir / 'question.yml'
        
        # Custom YAML writing to control date format
        with open(question_file, 'w', encoding='utf-8') as f:
            f.write(f"id: {question_data['id']}\n")
            f.write(f"chapterId: {question_data['chapterId']}\n")
            f.write(f"difficulty: {question_data['difficulty']}\n")
            f.write(f"duration: {question_data['duration']}\n")
            f.write(f"author: {question_data['author']}\n")
            f.write(f"original_language: {question_data['original_language']}\n")
            f.write("proofreading:\n")
            for proof in question_data['proofreading']:
                f.write(f"  - language: {proof['language']}\n")
                f.write(f"    last_contribution_date: {proof['last_contribution_date']}\n")
                f.write(f"    urgency: {proof['urgency']}\n")
                f.write("    contributor_names:\n")
                if proof['contributor_names']:
                    for contributor in proof['contributor_names']:
                        f.write(f"      - {contributor}\n")
                else:
                    f.write("      []\n")
                f.write(f"    reward: {proof['reward']}\n")
        
        # Create en.yml with proper formatting
        en_file = quiz_dir / 'en.yml'
        
        # Write the YAML manually to ensure proper formatting
        with open(en_file, 'w', encoding='utf-8') as f:
            # Write in the desired order: question, answer, wrong_answers, explanation
            
            # Question - single line
            question = quiz_data['question']
            f.write(f"question: {question}\n")
            
            # Answer - single line  
            answer = quiz_data['answer']
            f.write(f"answer: {answer}\n")
            
            # Wrong answers - one per line with 2-space indentation
            f.write("wrong_answers:\n")
            for wrong_answer in quiz_data['wrong_answers']:
                # Handle special characters in answers
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
            explanation = quiz_data['explanation']
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
        
        print(f"✅ Quiz files saved to {quiz_dir}")
    
    def _yaml_escape_string(self, text: str) -> str:
        """
        Escape a string for YAML if necessary.
        Returns quoted string if it contains special characters.
        """
        # Remove any line breaks and extra spaces
        text = ' '.join(text.split())
        
        # Check if string needs quoting
        special_chars = [':', '{', '}', '[', ']', ',', '&', '*', '#', '?', '|', '-', '<', '>', '=', '!', '%', '@', '\\']
        needs_quotes = any(char in text for char in special_chars) or text.startswith('"') or text.startswith("'")
        
        if needs_quotes:
            # Escape any quotes in the string and wrap in double quotes
            text = text.replace('"', '\\"')
            return f'"{text}"'
        return text
    
    def save_multiple_quizzes(self, quizzes: List[Dict[str, Any]], output_dir: Path, chapter_name: str) -> None:
        """
        Save multiple quiz files for a chapter.
        
        Args:
            quizzes: List of quiz data dictionaries
            output_dir: Output directory for quiz files
            chapter_name: Name of the chapter for logging
        """
        # Get existing quiz numbers to continue incrementally
        existing_quizzes = [d for d in output_dir.iterdir() if d.is_dir() and d.name.isdigit()]
        existing_numbers = [int(d.name) for d in existing_quizzes]
        
        # Start from the next available number
        if existing_numbers:
            start_number = max(existing_numbers) + 1
        else:
            start_number = 1
        
        print(f"📝 Starting quiz numbering from {start_number:03d} (found {len(existing_quizzes)} existing quizzes)")
        
        for i, quiz_data in enumerate(quizzes):
            quiz_number = f"{start_number + i:03d}"
            self.save_quiz_files(quiz_data, output_dir, quiz_number)
            print(f"   📋 Saved {quiz_data['difficulty']} question as {quiz_number}")
    
    def validate_quiz_interactively(self, quiz_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Present quiz to user for validation and allow modifications.
        
        Args:
            quiz_data: Original quiz data
            
        Returns:
            Validated and potentially modified quiz data
        """
        print("\n" + "="*60)
        print("📝 QUIZ QUESTION REVIEW")
        print("="*60)
        print(f"🎯 Difficulty: {quiz_data.get('difficulty', 'Unknown').upper()}")
        
        print(f"\n❓ Question: {quiz_data['question']}")
        print(f"\n✅ Correct Answer: {quiz_data['answer']}")
        print(f"\n❌ Wrong Answers:")
        for i, wrong in enumerate(quiz_data['wrong_answers'], 1):
            print(f"   {i}. {wrong}")
        print(f"\n💡 Explanation: {quiz_data['explanation']}")
        
        print("\n" + "-"*60)
        print("Options:")
        print("1. Accept as is")
        print("2. Edit question")
        print("3. Edit correct answer")
        print("4. Edit wrong answers")
        print("5. Edit explanation")
        print("6. Reject (skip this question)")
        
        choice = input("\nYour choice [1]: ").strip() or '1'
        
        if choice == '1':
            return quiz_data
        elif choice == '2':
            new_question = input("Enter new question: ").strip()
            if new_question:
                quiz_data['question'] = new_question
            return self.validate_quiz_interactively(quiz_data)
        elif choice == '3':
            new_answer = input("Enter new correct answer: ").strip()
            if new_answer:
                quiz_data['answer'] = new_answer
            return self.validate_quiz_interactively(quiz_data)
        elif choice == '4':
            print("Enter 3 wrong answers (press Enter to keep current):")
            new_wrong = []
            for i in range(3):
                current = quiz_data['wrong_answers'][i] if i < len(quiz_data['wrong_answers']) else ""
                wrong = input(f"Wrong answer {i+1} [{current}]: ").strip()
                new_wrong.append(wrong if wrong else current)
            quiz_data['wrong_answers'] = new_wrong
            return self.validate_quiz_interactively(quiz_data)
        elif choice == '5':
            print("Enter new explanation (press Enter twice to finish):")
            lines = []
            while True:
                line = input()
                if not line and lines and not lines[-1]:
                    break
                lines.append(line)
            if lines:
                quiz_data['explanation'] = '\n'.join(lines).strip()
            return self.validate_quiz_interactively(quiz_data)
        elif choice == '6':
            return None
        else:
            return quiz_data
