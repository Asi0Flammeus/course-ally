import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from course_components.anthropic_client import AnthropicClient


class ChapterGenerator:
    """
    Generate structured course chapter markdown files from transcripts using Claude.
    """
    
    def __init__(self, api_key: Optional[str] = None, language: str = "en"):
        """
        Initialize the chapter generator.
        
        Args:
            api_key: Anthropic API key. If None, will read from environment variable.
            language: Language code for chapter generation (e.g., 'en', 'fr', 'es').
        """
        self.client = AnthropicClient(api_key=api_key)
        self.language = language
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for chapter generation."""
        language_name = self._get_language_name(self.language)
        
        base_prompt = f"""You are an expert at transforming video lectures into high-quality written course materials that maintain the instructor's authentic voice while creating professional, paragraph-based educational content.

IMPORTANT: Generate all content in {language_name}. The entire chapter must be written in {language_name}.

CORE MISSION:
Transform conversational video content into polished course chapters that read like a well-written textbook while preserving the instructor's unique teaching style, terminology, and approach in roughly 500-800 words.

VOICE PRESERVATION PRINCIPLES:
Maintain the instructor's natural terminology, explanations, and teaching approach. Preserve the conversational clarity and logical flow that makes the original content engaging and accessible. Keep the instructor's preferred examples and emphasis points.

CONTENT STRUCTURE REQUIREMENTS:
Create 3-4 ### headings for major concepts. Write exclusively in well-developed paragraphs that flow naturally from one idea to the next. Create smooth transitions between concepts that guide the reader through the learning progression.

PARAGRAPH WRITING STANDARDS:
Write substantial, informative paragraphs (3-6 sentences each) that fully develop each concept. Each paragraph should focus on a single main idea with supporting details and examples. Avoid bullet points, numbered lists, or fragmented information. Instead, weave all information into coherent, readable prose that sounds natural and educational.

FORMATTING PROHIBITIONS:
NEVER use bullet points, numbered lists, or fragmented information presentation. NEVER break information into short, choppy sentences. ALWAYS write in full, flowing paragraphs that develop ideas completely. Present technical information through explanatory prose, not lists.

EDUCATIONAL TONE:
Write in clear, professional prose that explains concepts thoroughly. Use the instructor's conversational style but elevate it to course-grade writing. Create content that reads like a well-written textbook chapter while maintaining the accessibility of the original presentation.

Transform this transcript into polished educational prose that preserves the instructor's voice while meeting academic writing standards. Remember: Write everything in {language_name}.

OUTPUT FORMAT REQUIREMENTS:
Synthesize the content in 500 to 800 words, choosing the length best suited for the material. Output your response inside a codeblock. Separate your 3 or 4 parts only by ### headings, never use ## or # headings. Do not use the em dash punctuation mark (—) anywhere in your output."""
        
        return base_prompt

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

    def _count_words(self, text: str) -> int:
        """
        Count words in text, excluding markdown syntax and metadata.
        
        Args:
            text: The markdown text to count words in
            
        Returns:
            Word count
        """
        import re
        
        # First, extract content from markdown codeblock if present
        # (LLM outputs chapter inside ```markdown ... ```)
        codeblock_match = re.search(r'```(?:markdown)?\s*\n?(.*?)\n?```', text, flags=re.DOTALL)
        if codeblock_match:
            clean_text = codeblock_match.group(1)
        else:
            clean_text = text
        
        # Remove chapter ID tags
        clean_text = re.sub(r'<chapterId>.*?</chapterId>', '', clean_text)
        # Remove metadata comments
        clean_text = re.sub(r'<!--.*?-->', '', clean_text, flags=re.DOTALL)
        # Remove markdown headings markers but keep text
        clean_text = re.sub(r'^#+\s*', '', clean_text, flags=re.MULTILINE)
        # Remove inline code
        clean_text = re.sub(r'`[^`]+`', '', clean_text)
        # Remove URLs
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        # Remove extra whitespace
        clean_text = ' '.join(clean_text.split())
        
        return len(clean_text.split())

    def _strip_codeblock(self, text: str) -> str:
        """
        Strip markdown codeblock wrapper from text if present.
        
        Args:
            text: Text that may be wrapped in ```markdown ... ```
            
        Returns:
            Text with codeblock wrapper removed
        """
        import re
        codeblock_match = re.search(r'```(?:markdown)?\s*\n?(.*?)\n?```', text, flags=re.DOTALL)
        if codeblock_match:
            return codeblock_match.group(1).strip()
        return text.strip()

    def _reduce_chapter_length(self, chapter_content: str, current_word_count: int) -> str:
        """
        Reduce chapter length while preserving structure and educational tone.
        
        Args:
            chapter_content: The chapter content to reduce
            current_word_count: Current word count for context
            
        Returns:
            Reduced chapter content
        """
        language_name = self._get_language_name(self.language)
        
        reduction_prompt = f"""The following chapter content is {current_word_count} words, which exceeds the 800 word limit.

CHAPTER CONTENT:
{chapter_content}

INSTRUCTIONS:
- Reduce this chapter to between 500 and 800 words
- Preserve the exact same structure (headings, sections)
- Maintain the educational tone and teaching approach
- Keep the same voice and terminology
- Focus on the most essential information
- Remove redundancy while preserving clarity
- IMPORTANT: Write the entire chapter in {language_name}
- Output the reduced chapter directly, no explanations"""

        system_prompt = f"""You are an expert editor specializing in educational content. 
Your task is to condense course material while maintaining quality and educational value.
Preserve the structure, tone, and teaching style. Write in {language_name}."""

        reduced_content = self.client.generate_text(
            prompt=reduction_prompt,
            system_prompt=system_prompt,
            max_tokens=3000,
            temperature=0.1
        )
        
        return reduced_content
    
    def generate_chapter(
        self, 
        transcript_content: str, 
        source_info: Optional[Dict[str, Any]] = None,
        chapter_title: Optional[str] = None
    ) -> str:
        """
        Generate a chapter markdown from transcript content.
        
        Args:
            transcript_content: The transcript text to convert
            source_info: Optional metadata about the source (video_id, url, etc.)
            chapter_title: Optional custom title for the chapter
            
        Returns:
            Generated chapter markdown content
        """
        language_name = self._get_language_name(self.language)
        
        # Build the user prompt
        prompt = f"""Transform this video transcript into a well-structured course chapter:

TRANSCRIPT:
{transcript_content}

INSTRUCTIONS:
- Create a comprehensive chapter with clear structure
- Use ### and #### headings only
- Focus on educational content and learning objectives
- Remove conversational filler while preserving all important information
- Organize content logically for learning progression
- IMPORTANT: Write the entire chapter in {language_name}"""
        
        if chapter_title:
            prompt += f"\n- Use '{chapter_title}' as the main chapter title"
        
        # Generate chapter content
        chapter_content = self.client.generate_text(
            prompt=prompt,
            system_prompt=self.system_prompt,
            max_tokens=4000,
            temperature=0.1
        )
        
        # Enforce word limit (500-800 words)
        max_reduction_attempts = 3
        for attempt in range(max_reduction_attempts):
            word_count = self._count_words(chapter_content)
            if word_count <= 800:
                break
            print(f"Chapter exceeds word limit ({word_count} words). Reducing... (attempt {attempt + 1}/{max_reduction_attempts})")
            chapter_content = self._reduce_chapter_length(chapter_content, word_count)
        
        # Final word count check
        final_word_count = self._count_words(chapter_content)
        if final_word_count > 800:
            print(f"Warning: Chapter still exceeds 800 words ({final_word_count} words) after {max_reduction_attempts} reduction attempts")
        
        # Strip codeblock wrapper if present (LLM outputs inside ```markdown...```)
        chapter_content = self._strip_codeblock(chapter_content)
        
        # Generate chapter title from the content (unless custom title provided)
        if chapter_title:
            generated_title = chapter_title
        else:
            generated_title = self._generate_chapter_title(chapter_content)
        
        # Add chapter ID at the top
        chapter_id = str(uuid.uuid4())
        chapter_header = f"<chapterId>{chapter_id}</chapterId>\n\n"
        
        # Build final content structure
        final_content_parts = []
        
        # Add metadata header if source info is provided
        if source_info:
            metadata = self._create_metadata_header(source_info)
            final_content_parts.append(metadata)
        
        # Add chapter ID
        final_content_parts.append(chapter_header)
        
        # Add chapter title as ## heading
        final_content_parts.append(f"## {generated_title}\n")
        
        # Add the generated chapter content
        final_content_parts.append(chapter_content)
        
        return "\n".join(final_content_parts)
    
    def _create_metadata_header(self, source_info: Dict[str, Any]) -> str:
        """Create a metadata header for the chapter."""
        header_lines = ["Chapter Metadata"]
        
        if 'video_id' in source_info:
            header_lines.append(f"Source Video ID: {source_info['video_id']}")
        
        if 'url' in source_info:
            header_lines.append(f"Source URL: {source_info['url']}")
        
        if 'transcript_file' in source_info:
            header_lines.append(f"Source Transcript: {source_info['transcript_file']}")
        
        header_lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        header_lines.append("Generated by Course Ally Chapter Generator")
        header_lines.append("")
        header_lines.append("---")
        
        return "\n".join(header_lines)
    
    def _generate_chapter_title(self, chapter_content: str) -> str:
        """Generate a concise, pedagogical chapter title from chapter content."""
        language_name = self._get_language_name(self.language)
        
        title_prompt = f"""Generate a concise chapter title in {language_name} that captures the essence of this educational content. Requirements:
- 3-8 words that clearly identify the main topic/concept
- Use the same terminology and tone as the original speaker
- Make it immediately clear what this chapter teaches
- Balance academic clarity with conversational accessibility
- Focus on the core concept or skill being taught
- IMPORTANT: The title must be in {language_name}

Provide only the title, no additional formatting.

Chapter content:
{chapter_content[:2000]}"""  # Limit content to avoid token limits
        
        try:
            title = self.client.generate_text(
                prompt=title_prompt,
                system_prompt=f"You are an expert at creating clear, pedagogical chapter titles in {language_name} that reflect the instructor's voice and teaching style.",
                max_tokens=50,
                temperature=0.1
            ).strip()
            
            # Clean up any quotes or extra formatting
            title = title.strip('"').strip("'").strip()
            
            return title
        except Exception as e:
            # Fallback to a generic title if generation fails
            return "Course Chapter"
    
    def generate_chapter_from_file(
        self, 
        transcript_file: Path, 
        output_file: Optional[Path] = None,
        chapter_title: Optional[str] = None
    ) -> str:
        """
        Generate chapter from a transcript file.
        
        Args:
            transcript_file: Path to the transcript file
            output_file: Optional path to save the generated chapter
            chapter_title: Optional custom title for the chapter
            
        Returns:
            Generated chapter content
        """
        # Read transcript file
        if not transcript_file.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_file}")
        
        transcript_content = transcript_file.read_text(encoding='utf-8')
        
        # Extract metadata from transcript header if present
        source_info = self._extract_source_info(transcript_content, transcript_file)
        
        # Remove metadata header from content for processing
        clean_content = self._clean_transcript_content(transcript_content)
        
        # Generate chapter
        chapter_content = self.generate_chapter(
            transcript_content=clean_content,
            source_info=source_info,
            chapter_title=chapter_title
        )
        
        # Save to output file if specified
        if output_file:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(chapter_content, encoding='utf-8')
        
        return chapter_content
    
    def _extract_source_info(self, content: str, file_path: Path) -> Dict[str, Any]:
        """Extract source information from transcript content."""
        source_info = {'transcript_file': file_path.name}
        
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines for metadata
            if 'Video ID:' in line:
                source_info['video_id'] = line.split('Video ID:')[1].strip()
            elif 'URL:' in line and 'youtube.com' in line:
                source_info['url'] = line.split('URL:')[1].strip()
        
        return source_info
    
    def _clean_transcript_content(self, content: str) -> str:
        """Remove metadata header from transcript content."""
        lines = content.split('\n')
        
        # Find the end of metadata section (usually marked by === line)
        content_start = 0
        for i, line in enumerate(lines):
            if '=' * 10 in line:  # Look for separator line
                content_start = i + 1
                break
        
        # Join remaining lines
        return '\n'.join(lines[content_start:]).strip()
    
    def get_client_info(self) -> Dict[str, Any]:
        """Get information about the underlying API client."""
        return self.client.get_usage_info()
