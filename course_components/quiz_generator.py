import uuid
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from course_components.anthropic_client import AnthropicClient

class QuizGenerator:
    """Generate quiz questions from chapter content using Claude."""
    
    def __init__(self):
        self.client = AnthropicClient()
        self.author = None
        self.contributor_names = None
    
    def collect_metadata(self) -> None:
        """Collect author and contributor information from user."""
        if not self.author:
            print("\n" + "="*50)
            print("📝 QUIZ METADATA COLLECTION")
            print("="*50)
            
            # Get author
            while True:
                author = input("Enter author name: ").strip()
                if author:
                    self.author = author
                    break
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
        
        # Extract chapter ID from content if not provided
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
        """Extract chapter ID from chapter content."""
        lines = content.split('\n')
        for line in lines:
            if line.strip().startswith('<chapterId>') and line.strip().endswith('</chapterId>'):
                return line.strip().replace('<chapterId>', '').replace('</chapterId>', '')
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

        prompt = f"""Based on the following chapter content, generate ONE multiple choice quiz question at {difficulty.upper()} difficulty level.

This is question #{question_number} of 4 for the {difficulty} difficulty level, so make it unique from other questions.

Chapter: {chapter_name}
Difficulty: {difficulty}

Content:
{chapter_content}

DIFFICULTY REQUIREMENTS for {difficulty.upper()}:{difficulty_instructions[difficulty]}

Please generate:
1. A clear, specific question appropriate for {difficulty} level
2. One correct answer
3. Three plausible but incorrect answers
4. A brief explanation of why the correct answer is right

Format your response as JSON with this structure:
{{
    "question": "Your question here",
    "answer": "Correct answer",
    "wrong_answers": [
        "Wrong answer 1",
        "Wrong answer 2", 
        "Wrong answer 3"
    ],
    "explanation": "Brief explanation of the correct answer"
}}

IMPORTANT:
- Ensure this question is at {difficulty} difficulty level
- Make it different from other {difficulty} questions for this chapter
- The wrong answers should be plausible but clearly incorrect to someone who understands the material
- Keep answers concise but complete"""

        try:
            response = self.client.generate_text(prompt)
            
            # Try to parse JSON response
            import json
            # Extract JSON from response if it's wrapped in markdown
            if '```json' in response:
                start = response.find('```json') + 7
                end = response.find('```', start)
                json_str = response[start:end].strip()
            elif '```' in response:
                start = response.find('```') + 3
                end = response.find('```', start)
                json_str = response[start:end].strip()
            else:
                json_str = response.strip()
            
            quiz_data = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['question', 'answer', 'wrong_answers', 'explanation']
            for field in required_fields:
                if field not in quiz_data:
                    raise ValueError(f"Missing required field: {field}")
            
            if len(quiz_data['wrong_answers']) != 3:
                raise ValueError("Must have exactly 3 wrong answers")
                
            return quiz_data
            
        except Exception as e:
            raise Exception(f"Error generating quiz with Claude: {e}")
    
    def save_quiz_files(self, quiz_data: Dict[str, Any], output_dir: Path, quiz_number: str) -> None:
        """
        Save quiz files in the required format.
        
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
        with open(question_file, 'w', encoding='utf-8') as f:
            yaml.dump(question_data, f, default_flow_style=False, allow_unicode=True)
        
        # Create en.yml (English content)
        en_data = {
            'question': quiz_data['question'],
            'answer': quiz_data['answer'],
            'wrong_answers': quiz_data['wrong_answers'],
            'explanation': quiz_data['explanation'],
            'reviewed': False  # Set to False initially
        }
        
        en_file = quiz_dir / 'en.yml'
        with open(en_file, 'w', encoding='utf-8') as f:
            yaml.dump(en_data, f, default_flow_style=False, allow_unicode=True)
        
        print(f"✅ Quiz files saved to {quiz_dir}")
    
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
        
        while True:
            choice = input("\nOptions:\n1. Accept question\n2. Edit question\n3. Edit correct answer\n4. Edit wrong answers\n5. Edit explanation\n6. Regenerate question\n\nChoice: ").strip()
            
            if choice == '1':
                print("✅ Question accepted!")
                return quiz_data
            elif choice == '2':
                new_question = input(f"\nCurrent: {quiz_data['question']}\nNew question: ").strip()
                if new_question:
                    quiz_data['question'] = new_question
                    print("✅ Question updated!")
            elif choice == '3':
                new_answer = input(f"\nCurrent: {quiz_data['answer']}\nNew correct answer: ").strip()
                if new_answer:
                    quiz_data['answer'] = new_answer
                    print("✅ Correct answer updated!")
            elif choice == '4':
                print("\nCurrent wrong answers:")
                for i, wrong in enumerate(quiz_data['wrong_answers'], 1):
                    print(f"   {i}. {wrong}")
                
                for i in range(3):
                    new_wrong = input(f"\nWrong answer {i+1} (current: {quiz_data['wrong_answers'][i]}): ").strip()
                    if new_wrong:
                        quiz_data['wrong_answers'][i] = new_wrong
                print("✅ Wrong answers updated!")
            elif choice == '5':
                new_explanation = input(f"\nCurrent: {quiz_data['explanation']}\nNew explanation: ").strip()
                if new_explanation:
                    quiz_data['explanation'] = new_explanation
                    print("✅ Explanation updated!")
            elif choice == '6':
                print("🔄 This would regenerate the question (not implemented in this validation)")
                continue
            else:
                print("❌ Invalid choice. Please select 1-6.")
                continue
            
            # Show updated question
            print("\n" + "="*60)
            print("📝 UPDATED QUIZ QUESTION")
            print("="*60)
            print(f"🎯 Difficulty: {quiz_data.get('difficulty', 'Unknown').upper()}")
            print(f"\n❓ Question: {quiz_data['question']}")
            print(f"\n✅ Correct Answer: {quiz_data['answer']}")
            print(f"\n❌ Wrong Answers:")
            for i, wrong in enumerate(quiz_data['wrong_answers'], 1):
                print(f"   {i}. {wrong}")
            print(f"\n💡 Explanation: {quiz_data['explanation']}")
            print("\n" + "-"*60)