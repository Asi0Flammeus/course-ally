import uuid
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from course_components.anthropic_client import AnthropicClient

class QuizGenerator:
    """Generate quiz questions from chapter content using Claude."""
    
    def __init__(self):
        self.client = AnthropicClient()
    
    def generate_quiz_from_file(self, chapter_file: Path, chapter_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a quiz question from a chapter file.
        
        Args:
            chapter_file: Path to the chapter markdown file
            chapter_id: Optional chapter ID to associate with the quiz
            
        Returns:
            Dictionary containing quiz data
        """
        # Read chapter content
        try:
            chapter_content = chapter_file.read_text(encoding='utf-8')
        except Exception as e:
            raise Exception(f"Error reading chapter file: {e}")
        
        # Extract chapter ID from content if not provided
        if not chapter_id:
            chapter_id = self._extract_chapter_id(chapter_content)
        
        # Generate quiz using Claude
        quiz_data = self._generate_quiz_with_claude(chapter_content, chapter_file.stem)
        
        # Add metadata
        quiz_data['id'] = str(uuid.uuid4())
        quiz_data['chapterId'] = chapter_id
        quiz_data['difficulty'] = 'medium'  # Default difficulty
        quiz_data['duration'] = 15  # Default duration in seconds
        quiz_data['author'] = 'Course-Ally'
        quiz_data['original_language'] = 'en'
        
        return quiz_data
    
    def _extract_chapter_id(self, content: str) -> Optional[str]:
        """Extract chapter ID from chapter content."""
        lines = content.split('\n')
        for line in lines:
            if line.strip().startswith('<chapterId>') and line.strip().endswith('</chapterId>'):
                return line.strip().replace('<chapterId>', '').replace('</chapterId>', '')
        return None
    
    def _generate_quiz_with_claude(self, chapter_content: str, chapter_name: str) -> Dict[str, Any]:
        """Generate quiz questions using Claude."""
        
        prompt = f"""Based on the following chapter content, generate ONE multiple choice quiz question.

Chapter: {chapter_name}

Content:
{chapter_content}

Please generate:
1. A clear, specific question about a key concept from the chapter
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

Make sure the question tests understanding of important concepts, not just memorization of facts.
The wrong answers should be plausible but clearly incorrect to someone who understands the material.
Keep answers concise but complete."""

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
                    'last_contribution_date': None,
                    'urgency': 1,
                    'contributor_names': [],
                    'reward': 0.08
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
            print(f"\n❓ Question: {quiz_data['question']}")
            print(f"\n✅ Correct Answer: {quiz_data['answer']}")
            print(f"\n❌ Wrong Answers:")
            for i, wrong in enumerate(quiz_data['wrong_answers'], 1):
                print(f"   {i}. {wrong}")
            print(f"\n💡 Explanation: {quiz_data['explanation']}")
            print("\n" + "-"*60)