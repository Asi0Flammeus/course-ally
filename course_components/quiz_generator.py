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
    
    def __init__(self):
        """Initialize the quiz generator with Claude API."""
        self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        self.author = None
        self.contributor_names = []
    
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
    
    def generate_quizzes_from_file(self, chapter_file: Path, chapter_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Generate multiple quiz questions from a chapter file (4 easy, 4 intermediate, 4 hard).
        
        Args:
            chapter_file: Path to the chapter markdown file
            chapter_id: Optional chapter ID to associate with the quiz
            
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
                    # Generate quiz using Claude
                    quiz_data = self._generate_quiz_with_claude(chapter_content, chapter_file.stem, difficulty, i + 1)
                    
                    # Add metadata
                    quiz_data['id'] = str(uuid.uuid4())
                    quiz_data['chapterId'] = chapter_id
                    quiz_data['difficulty'] = difficulty
                    quiz_data['duration'] = self._get_duration_for_difficulty(difficulty)
                    quiz_data['author'] = self.author or 'Course-Ally'
                    quiz_data['original_language'] = 'en'
                    
                    all_quizzes.append(quiz_data)
                    
                except Exception as e:
                    print(f"⚠️  Warning: Failed to generate {difficulty} question {i+1}: {e}")
                    continue
        
        return all_quizzes
    
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
    
    def _generate_quiz_with_claude(self, chapter_content: str, chapter_name: str, difficulty: str, question_number: int) -> Dict[str, Any]:
        """Generate quiz questions using Claude."""
        
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

Chapter: {chapter_name}

Content:
{chapter_content[:8000]}  # Limit content to avoid token limits

Requirements for {difficulty} difficulty:
{difficulty_instructions[difficulty]}

Generate a quiz question with:
1. A clear, single-line question (no line breaks)
2. One correct answer (single line)
3. Three wrong answers that are plausible but clearly incorrect (each on single line)
4. A detailed explanation that teaches the concept (can be multiple paragraphs)

IMPORTANT:
- Keep question and answers on single lines (no line breaks within them)
- Wrong answers should be believable but definitively incorrect
- Explanation should thoroughly explain why the correct answer is right and others are wrong
- For the chapter content provided, focus on key concepts that appear in the material

Return ONLY a JSON object in this exact format:
{{
    "question": "Your single-line question here?",
    "answer": "The correct answer",
    "wrong_answers": [
        "First wrong answer",
        "Second wrong answer",
        "Third wrong answer"
    ],
    "explanation": "Detailed explanation here. Can be multiple sentences and paragraphs."
}}
"""
        
        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1000,
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
            # Write in the desired order with proper formatting
            f.write(f"question: {self._yaml_escape_string(quiz_data['question'])}\n")
            f.write(f"answer: {self._yaml_escape_string(quiz_data['answer'])}\n")
            f.write("wrong_answers:\n")
            for wrong_answer in quiz_data['wrong_answers']:
                f.write(f"  - {self._yaml_escape_string(wrong_answer)}\n")
            
            # Write explanation with multi-line format
            f.write("explanation: |\n")
            explanation_lines = quiz_data['explanation'].split('\n')
            for line in explanation_lines:
                f.write(f"  {line}\n")
            
            f.write("reviewed: false\n")
        
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