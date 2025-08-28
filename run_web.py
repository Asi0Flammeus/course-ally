#!/usr/bin/env python3
"""
Course Ally Web Application
Run this script to start the web interface on localhost:5000
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Check for required environment variables
if not os.getenv('ANTHROPIC_API_KEY'):
    print("⚠️  Warning: ANTHROPIC_API_KEY not found in environment.")
    print("   Chapter and quiz generation features will not work.")
    print("   Set it in your .env file or environment variables.")
    print()
else:
    print("✅ ANTHROPIC_API_KEY loaded successfully")
    print()

# Check for required dependencies
try:
    import flask
    import flask_cors
except ImportError:
    print("❌ Missing web dependencies. Please install them:")
    print("   pip install -r requirements-web.txt")
    sys.exit(1)

# Create required directories
directories = [
    'outputs/transcripts',
    'outputs/playlist_to_md', 
    'outputs/chapters',
    'outputs/quizz'
]

for dir_path in directories:
    Path(dir_path).mkdir(parents=True, exist_ok=True)

# Start the application
if __name__ == '__main__':
    print("🚀 Starting Course Ally Web Application...")
    print("📍 Open your browser at: http://localhost:5000")
    print("🛑 Press Ctrl+C to stop the server")
    print()
    
    from app import app
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)