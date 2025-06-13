#!/usr/bin/env python3
"""
Utility script to format existing transcript files with sentence-per-line formatting.
This applies the same formatting used in the updated TranscriptionService to old files.

Usage: python3 format_transcript.py <path_to_transcript_file_or_directory>

Examples:
    python3 format_transcript.py ./outputs/transcripts/his205/transcript.txt
    python3 format_transcript.py ./outputs/transcripts/his205
"""

import sys
import re
from pathlib import Path

def format_transcript_text(transcript: str) -> str:
    """
    Format transcript with one sentence per line for better readability.
    This is the same logic as TranscriptionService._format_transcript()
    
    Args:
        transcript: Raw transcript text
        
    Returns:
        Formatted transcript with sentences on separate lines
    """
    if not transcript or not transcript.strip():
        return transcript
    
    # Clean up the transcript
    text = transcript.strip()
    
    # First, try to split on sentence boundaries with proper punctuation
    # This pattern matches sentence-ending punctuation followed by whitespace and a capital letter
    sentence_endings = r'([.!?]+)\s+(?=[A-Z])'
    
    # Split and keep the delimiters
    parts = re.split(sentence_endings, text)
    
    sentences = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts) and re.match(r'^[.!?]+$', parts[i + 1]):
            # Current part + punctuation
            sentence = parts[i] + parts[i + 1]
            i += 2
        else:
            sentence = parts[i]
            i += 1
        
        sentence = sentence.strip()
        if sentence:
            sentences.append(sentence)
    
    # If we didn't get good sentence breaks, try simpler approaches
    if len(sentences) <= 1:
        # Fall back to splitting on periods followed by space
        if '. ' in text:
            parts = text.split('. ')
            sentences = []
            for i, part in enumerate(parts):
                part = part.strip()
                if part:
                    # Add period back except for the last part (which may already have ending punctuation)
                    if i < len(parts) - 1 and not part.endswith(('.', '!', '?')):
                        part += '.'
                    sentences.append(part)
        else:
            # If no good sentence breaks, keep as single block but clean it up
            sentences = [text]
    
    # Clean up sentences and remove empty ones
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence and len(sentence) > 1:  # Avoid single character lines
            cleaned_sentences.append(sentence)
    
    # Join sentences with newlines
    return '\n'.join(cleaned_sentences) if cleaned_sentences else text

def format_transcript_file(file_path: Path) -> bool:
    """
    Format a single transcript file.
    
    Args:
        file_path: Path to the transcript file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Read the original file
        print(f"📄 Processing: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if it's a transcript file with metadata header
        if content.startswith('# Video Transcript'):
            # Split header and transcript content
            lines = content.split('\n')
            header_end = -1
            for i, line in enumerate(lines):
                if line.strip() == '=' * 60:
                    header_end = i
                    break
            
            if header_end != -1:
                # Found metadata header, preserve it
                header_lines = lines[:header_end + 2]  # Include the separator and empty line
                transcript_content = '\n'.join(lines[header_end + 2:])
                
                # Format only the transcript content
                formatted_transcript = format_transcript_text(transcript_content)
                
                # Combine header with formatted transcript
                formatted_content = '\n'.join(header_lines) + formatted_transcript
            else:
                # No clear header found, format entire content
                formatted_content = format_transcript_text(content)
        else:
            # No metadata header, format entire content
            formatted_content = format_transcript_text(content)
        
        # Create backup of original
        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
        print(f"💾 Creating backup: {backup_path}")
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Write formatted content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)
        
        # Count sentences
        sentence_count = len(formatted_content.split('\n'))
        print(f"✅ Formatted successfully: {sentence_count} lines")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")
        return False

def main():
    """Main function to handle command line arguments and process files."""
    
    if len(sys.argv) != 2:
        print("Usage: python3 format_transcript.py <path_to_transcript_file_or_directory>")
        print("\nExamples:")
        print("  python3 format_transcript.py ./outputs/transcripts/his205/transcript.txt")
        print("  python3 format_transcript.py ./outputs/transcripts/his205")
        sys.exit(1)
    
    target_path = Path(sys.argv[1])
    
    if not target_path.exists():
        print(f"❌ Error: Path not found: {target_path}")
        sys.exit(1)
    
    print("🔧 Transcript Formatter")
    print("=" * 50)
    print(f"Target: {target_path.absolute()}")
    print()
    
    files_to_process = []
    
    if target_path.is_file():
        # Single file
        if target_path.suffix in ['.txt', '.md']:
            files_to_process.append(target_path)
        else:
            print(f"❌ Error: File must be .txt or .md, got: {target_path.suffix}")
            sys.exit(1)
    elif target_path.is_dir():
        # Directory - find all transcript files
        print("🔍 Scanning directory for transcript files...")
        files_to_process = list(target_path.glob('*.txt')) + list(target_path.glob('*.md'))
        
        if not files_to_process:
            print(f"❌ No .txt or .md files found in: {target_path}")
            sys.exit(1)
        
        print(f"📋 Found {len(files_to_process)} files to process")
    else:
        print(f"❌ Error: Path is neither file nor directory: {target_path}")
        sys.exit(1)
    
    print()
    
    # Process files
    successful = 0
    failed = 0
    
    for file_path in files_to_process:
        if format_transcript_file(file_path):
            successful += 1
        else:
            failed += 1
        print()
    
    # Summary
    print("=" * 50)
    print("📊 FORMATTING SUMMARY")
    print("=" * 50)
    print(f"✅ Successfully formatted: {successful} files")
    if failed > 0:
        print(f"❌ Failed: {failed} files")
    print(f"💾 Backup files created with .backup extension")
    print()
    print("🗑️  To clean up backup files later, run:")
    if target_path.is_dir():
        print(f"   find {target_path} -name '*.backup' -delete")
    else:
        print(f"   rm {target_path.with_suffix(target_path.suffix + '.backup')}")
    print()
    print("✨ All done!")

if __name__ == "__main__":
    main()