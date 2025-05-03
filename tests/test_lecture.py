import unittest
from unittest.mock import patch

from course_components.lecture import LectureGenerator

class TestLectureGenerator(unittest.TestCase):
    @patch('course_components.lecture.openai.ChatCompletion.create')
    def test_generate_outline_json(self, mock_create):
        # Mock JSON array response
        mock_create.return_value = {
            'choices': [
                {'message': {'content': '["Intro", "Main", "Conclusion"]'}}
            ]
        }
        gen = LectureGenerator()
        outline = gen.generate_outline('dummy transcript', num_sections=3)
        self.assertEqual(outline, ['Intro', 'Main', 'Conclusion'])

    @patch('course_components.lecture.openai.ChatCompletion.create')
    def test_generate_outline_fallback(self, mock_create):
        # Mock plain text response
        content = '- Intro\n- Main\n- Conclusion'
        mock_create.return_value = {'choices': [{'message': {'content': content}}]}
        gen = LectureGenerator()
        outline = gen.generate_outline('dummy transcript', num_sections=3)
        self.assertEqual(outline, ['Intro', 'Main', 'Conclusion'])

    @patch('course_components.lecture.openai.ChatCompletion.create')
    def test_generate_markdown(self, mock_create):
        # First call for outline
        outline_resp = {'choices': [{'message': {'content': '["Sec1", "Sec2"]'}}]}
        # Next calls for each section
        section1 = {'choices': [{'message': {'content': 'Content1'}}]}
        section2 = {'choices': [{'message': {'content': 'Content2'}}]}
        mock_create.side_effect = [outline_resp, section1, section2]
        gen = LectureGenerator()
        markdown = gen.generate_markdown('dummy transcript', num_sections=2)
        expected = '## Sec1\n\nContent1\n\n## Sec2\n\nContent2'
        self.assertEqual(markdown, expected)

if __name__ == '__main__':
    unittest.main()