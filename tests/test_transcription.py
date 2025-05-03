import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from course_components.transcription import TranscriptionService

class TestTranscriptionService(unittest.TestCase):
    @patch('course_components.transcription.openai.Audio.transcribe')
    def test_transcribe_success(self, mock_transcribe):
        mock_transcribe.return_value = {'text': 'dummy transcript'}
        service = TranscriptionService(api_key='test_key')
        # Create a dummy file
        temp_file = Path('temp_audio.mp3')
        temp_file.write_bytes(b'')
        result = service.transcribe(temp_file)
        self.assertEqual(result, 'dummy transcript')
        temp_file.unlink()

    def test_transcribe_file_not_found(self):
        service = TranscriptionService(api_key='test_key')
        with self.assertRaises(ValueError):
            service.transcribe('nonexistent.mp3')

if __name__ == '__main__':
    unittest.main()