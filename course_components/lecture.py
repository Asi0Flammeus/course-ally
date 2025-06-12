from typing import List
import json
from openai import OpenAI
from dotenv import load_dotenv
import os

class LectureGenerator:
    """
    Generates lecture outlines and full lectures in markdown format using OpenAI's GPT API.
    """
    def __init__(self, model: str = "gpt-3.5-turbo") -> None:
        """
        Initializes the lecture generator.

        Args:
            model: OpenAI chat model identifier.
        """
        # Load environment variables
        load_dotenv()
        
        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate_outline(self, transcript: str, num_sections: int = 3) -> List[str]:
        """
        Generates section titles for the lecture outline based on the transcript.

        Args:
            transcript: Full transcript text.
            num_sections: Number of main sections to generate.

        Returns:
            A list of section title strings.
        """
        prompt = (
            f"Based on the following transcript, create a lecture outline with "
            f"{num_sections} sub sections.\n\n"
            f"Transcript:\n{transcript}"
        )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content
        try:
            sections = json.loads(content)
            if not isinstance(sections, list):
                raise ValueError("Outline JSON is not a list")
            return sections
        except json.JSONDecodeError:
            # Fallback: parse lines starting with hyphens or numbers
            lines = []
            for line in content.splitlines():
                line = line.strip().lstrip("- ").lstrip("0123456789. ")
                if line:
                    lines.append(line)
            return lines

    def generate_lecture(self, transcript: str, section_titles: List[str]) -> str:
        """
        Generates the full lecture content for each section.

        Args:
            transcript: Full transcript text.
            section_titles: List of section titles.

        Returns:
            Markdown string of the lecture with section headings.
        """
        markdown_parts: List[str] = []
        for title in section_titles:
            prompt = (
                f"Using the following transcript, write a detailed lecture section titled '{title}'."\
                f"\n\nTranscript:\n{transcript}"
            )
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.choices[0].message.content
            # Append section with markdown heading
            markdown_parts.append(f"## {title}\n\n{content}")
        
        # Combine all sections
        return "\n\n".join(markdown_parts)

    def generate_markdown(self, transcript: str, num_sections: int = 3) -> str:
        """
        Generates the complete lecture in markdown format from transcript.

        Args:
            transcript: Full transcript text.
            num_sections: Number of main sections in the outline.

        Returns:
            The lecture as a markdown-formatted string.
        """
        titles = self.generate_outline(transcript, num_sections=num_sections)
        lecture_md = self.generate_lecture(transcript, titles)
        return lecture_md

