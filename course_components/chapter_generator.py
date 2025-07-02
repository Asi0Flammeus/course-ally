import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from course_components.anthropic_client import AnthropicClient


class ChapterGenerator:
    """
    Generate structured course chapter markdown files from transcripts using Claude.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the chapter generator.
        
        Args:
            api_key: Anthropic API key. If None, will read from environment variable.
        """
        self.client = AnthropicClient(api_key=api_key)
        self.system_prompt = self._get_system_prompt()
    
    def _get_system_prompt(self) -> str:
        """Get the system prompt for chapter generation."""
        return """You are an expert at transforming video lectures into high-quality written course materials that maintain the instructor's authentic voice while creating professional, paragraph-based educational content.

CORE MISSION:
Transform conversational video content into polished course chapters that read like a well-written textbook while preserving the instructor's unique teaching style, terminology, and approach.

VOICE PRESERVATION PRINCIPLES:
Maintain the instructor's natural terminology, explanations, and teaching approach. Preserve the conversational clarity and logical flow that makes the original content engaging and accessible. Keep the instructor's preferred examples and emphasis points.

CONTENT STRUCTURE REQUIREMENTS:
Use ### headings for major concepts and #### headings for detailed subtopics. Write exclusively in well-developed paragraphs that flow naturally from one idea to the next. Create smooth transitions between concepts that guide the reader through the learning progression.

PARAGRAPH WRITING STANDARDS:
Write substantial, informative paragraphs (3-6 sentences each) that fully develop each concept. Each paragraph should focus on a single main idea with supporting details and examples. Avoid bullet points, numbered lists, or fragmented information. Instead, weave all information into coherent, readable prose that sounds natural and educational.

FORMATTING PROHIBITIONS:
NEVER use bullet points, numbered lists, or fragmented information presentation. NEVER break information into short, choppy sentences. ALWAYS write in full, flowing paragraphs that develop ideas completely. Present technical information through explanatory prose, not lists.

EDUCATIONAL TONE:
Write in clear, professional prose that explains concepts thoroughly. Use the instructor's conversational style but elevate it to course-grade writing. Create content that reads like a well-written textbook chapter while maintaining the accessibility of the original presentation.

Transform this transcript into polished educational prose that preserves the instructor's voice while meeting academic writing standards."""
    
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
        # Build the user prompt
        prompt = f"""Transform this video transcript into a well-structured course chapter:

TRANSCRIPT:
{transcript_content}

INSTRUCTIONS:
- Create a comprehensive chapter with clear structure
- Use ### and #### headings only
- Focus on educational content and learning objectives
- Remove conversational filler while preserving all important information
- Organize content logically for learning progression"""
        
        if chapter_title:
            prompt += f"\n- Use '{chapter_title}' as the main chapter title"
        
        # Generate chapter content
        chapter_content = self.client.generate_text(
            prompt=prompt,
            system_prompt=self.system_prompt,
            max_tokens=4000,
            temperature=0.1
        )
        
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
        title_prompt = f"""Generate a concise chapter title that captures the essence of this educational content. Requirements:
- 3-8 words that clearly identify the main topic/concept
- Use the same terminology and tone as the original speaker
- Make it immediately clear what this chapter teaches
- Balance academic clarity with conversational accessibility
- Focus on the core concept or skill being taught

Provide only the title, no additional formatting.

Chapter content:
{chapter_content[:2000]}"""  # Limit content to avoid token limits
        
        try:
            title = self.client.generate_text(
                prompt=title_prompt,
                system_prompt="You are an expert at creating clear, pedagogical chapter titles that reflect the instructor's voice and teaching style.",
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