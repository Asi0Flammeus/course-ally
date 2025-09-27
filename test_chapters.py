#!/usr/bin/env python3
"""Test chapter extraction"""

from pathlib import Path
from dotenv import load_dotenv
from course_components.quiz_workflow import QuizWorkflowManager

load_dotenv()

manager = QuizWorkflowManager()

# Test for BTC101 in English
chapters = manager.list_chapters('BEC_REPO', 'btc101', 'en')
print(f"Chapters for btc101 (English): {len(chapters)} found")
if chapters:
    for i, chapter in enumerate(chapters[:3]):  # Show first 3
        print(f"  {i+1}. {chapter.get('title', 'No title')}")
        print(f"     ID: {chapter.get('chapter_id', 'No ID')}")

# Test for BTC101 in French
chapters = manager.list_chapters('BEC_REPO', 'btc101', 'fr')
print(f"\nChapters for btc101 (French): {len(chapters)} found")
if chapters:
    for i, chapter in enumerate(chapters[:3]):  # Show first 3
        print(f"  {i+1}. {chapter.get('title', 'No title')}")
        print(f"     ID: {chapter.get('chapter_id', 'No ID')}")