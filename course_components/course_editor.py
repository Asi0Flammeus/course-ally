"""
Course Editor Module
Handles batch editing of course information with translation support
"""

import os
import re
import yaml
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
import anthropic
from dotenv import load_dotenv

load_dotenv()

class CourseEditor:
    def __init__(self):
        """Initialize the course editor"""
        self.repositories = {
            'BEC_REPO': {
                'name': 'Bitcoin Educational Content',
                'env_var': 'BEC_REPO',
                'default_path': '../bitcoin-educational-content'
            },
            'PREMIUM_REPO': {
                'name': 'Premium Content',
                'env_var': 'PREMIUM_REPO', 
                'default_path': '../planB-premium-content'
            }
        }
        
        # Initialize Claude API
        self.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
        if self.anthropic_api_key:
            self.client = anthropic.Anthropic(api_key=self.anthropic_api_key)
        else:
            self.client = None
    
    def _get_repo_path(self, repo_key: str) -> Optional[Path]:
        """Get the path for a repository"""
        if repo_key not in self.repositories:
            return None
            
        repo_info = self.repositories[repo_key]
        env_path = os.getenv(repo_info['env_var'])
        
        if env_path:
            path = Path(env_path)
            if not path.is_absolute():
                path = Path.cwd() / path
        else:
            path = Path.cwd() / repo_info['default_path']
            
        if path.exists() and (path / 'courses').exists():
            return path
        return None
    
    def list_all_courses(self) -> List[Dict[str, Any]]:
        """List all courses from both repositories"""
        courses = []
        
        for repo_key, repo_info in self.repositories.items():
            repo_path = self._get_repo_path(repo_key)
            if not repo_path:
                continue
            
            courses_dir = repo_path / 'courses'
            if not courses_dir.exists():
                continue
            
            for course_dir in courses_dir.iterdir():
                if not course_dir.is_dir():
                    continue
                
                # Check if it's a valid course (has en.md or course.yml)
                if (course_dir / 'course.yml').exists() or (course_dir / 'en.md').exists():
                    courses.append({
                        'name': course_dir.name.upper(),
                        'path': course_dir.name,
                        'repo': repo_key,
                        'repo_name': repo_info['name']
                    })
        
        return sorted(courses, key=lambda x: (x['repo'], x['name']))
    
    def load_course_data(self, repo_key: str, course_name: str) -> Dict[str, Any]:
        """Load all course data including metadata and content for all languages"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")
        
        course_path = repo_path / 'courses' / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")
        
        result = {
            'metadata': {},
            'content': {},
            'languages': []
        }
        
        # Load metadata from course.yml
        course_yml_path = course_path / 'course.yml'
        if course_yml_path.exists():
            with open(course_yml_path, 'r', encoding='utf-8') as f:
                yml_content = f.read()
                # Parse YAML
                try:
                    yml_data = yaml.safe_load(yml_content)
                    if yml_data:
                        result['metadata'] = {
                            'topic': yml_data.get('topic', ''),
                            'subtopic': yml_data.get('subtopic', ''),
                            'type': yml_data.get('type', ''),
                            'level': yml_data.get('level', ''),
                            'hours': yml_data.get('hours', 0)
                        }
                except:
                    pass
        
        # Find all language files
        for file_path in course_path.iterdir():
            if file_path.is_file() and file_path.suffix == '.md' and file_path.name != 'presentation.md':
                lang = file_path.stem
                result['languages'].append(lang)
                
                # Parse the markdown file
                content = self._parse_markdown_file(file_path)
                result['content'][lang] = content
        
        result['languages'].sort()
        # Ensure 'en' is first if it exists
        if 'en' in result['languages']:
            result['languages'].remove('en')
            result['languages'].insert(0, 'en')
        
        return result
    
    def _parse_markdown_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a course markdown file to extract metadata and description"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        result = {
            'name': '',
            'goal': '',
            'objectives': [],
            'description': ''
        }
        
        # Extract front matter
        front_matter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if front_matter_match:
            front_matter = front_matter_match.group(1)
            
            # Parse YAML front matter
            try:
                fm_data = yaml.safe_load(front_matter)
                if fm_data:
                    result['name'] = fm_data.get('name', '')
                    result['goal'] = fm_data.get('goal', '')
                    result['objectives'] = fm_data.get('objectives', [])
            except:
                # Fallback parsing
                for line in front_matter.split('\n'):
                    if line.startswith('name:'):
                        result['name'] = line[5:].strip()
                    elif line.startswith('goal:'):
                        result['goal'] = line[5:].strip()
                    elif line.startswith('  -'):
                        result['objectives'].append(line[3:].strip())
        
        # Extract description (content between --- and +++)
        description_match = re.search(r'---\s*\n.*?\n---\s*\n(.*?)\n\+\+\+', content, re.DOTALL)
        if description_match:
            result['description'] = description_match.group(1).strip()
        
        return result
    
    def translate_content(self, content: Dict[str, Any], target_languages: List[str]) -> Dict[str, Dict[str, Any]]:
        """Translate course content to all target languages in one API call using Claude"""
        if not self.client:
            print("Warning: Anthropic API key not configured, skipping translation")
            # Return original content for all languages
            return {lang: content for lang in target_languages}
        
        # Skip if no languages to translate
        if not target_languages or (len(target_languages) == 1 and 'en' in target_languages):
            return {'en': content} if 'en' in target_languages else {}
        
        # Filter out English from target languages
        languages_to_translate = [lang for lang in target_languages if lang != 'en']
        
        if not languages_to_translate:
            return {'en': content} if 'en' in target_languages else {}
        
        translations = {}
        
        try:
            # Sanitize content before sending
            sanitized_content = {
                'name': str(content.get('name', '')).replace('\x00', '').strip(),
                'goal': str(content.get('goal', '')).replace('\x00', '').strip(),
                'objectives': [str(obj).replace('\x00', '').strip() for obj in content.get('objectives', []) if obj],
                'description': str(content.get('description', '')).replace('\x00', '').strip()
            }
            
            # Build language map for the prompt
            language_map = {lang: self._get_language_name(lang) for lang in languages_to_translate}
            
            # Create a single prompt for all languages
            prompt = f"""Translate the following Bitcoin educational course content from English to multiple languages.

Content to translate:
- Name: {sanitized_content['name']}
- Goal: {sanitized_content['goal']}
- Objectives: {json.dumps(sanitized_content['objectives'], ensure_ascii=False)}
- Description: {sanitized_content['description']}

Target languages: {', '.join([f"{code} ({name})" for code, name in language_map.items()])}

IMPORTANT: Return ONLY a valid JSON object with ALL translations. Each language should have the complete translated content. Ensure accurate, professional translations that maintain educational context and technical accuracy. Bitcoin-specific terms should be translated appropriately for each target language.

Return format:
{{
    "language_code": {{
        "name": "translated name",
        "goal": "translated goal",
        "objectives": ["objective 1", "objective 2", ...],
        "description": "translated description"
    }},
    ...
}}

Example:
{{
    "fr": {{
        "name": "Bitcoin pour les entreprises",
        "goal": "Apprendre les bases...",
        "objectives": ["Premier objectif", "Deuxième objectif"],
        "description": "Ce cours..."
    }},
    "es": {{
        "name": "Bitcoin para empresas",
        "goal": "Aprender los conceptos básicos...",
        "objectives": ["Primer objetivo", "Segundo objetivo"],
        "description": "Este curso..."
    }}
}}"""
            
            # Call Claude API once for all languages
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4000,  # Increased for multiple languages
                temperature=0.3,
                system="You are a professional translator specializing in educational content about Bitcoin and cryptocurrency. Always return valid JSON with translations for ALL requested languages. Never use markdown formatting.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            translation_text = response.content[0].text.strip()
            
            # Remove any control characters from response
            import re
            translation_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', translation_text)
            
            # Clean up the response - remove markdown if present
            if translation_text.startswith('```'):
                translation_text = re.sub(r'^```(?:json)?', '', translation_text)
                translation_text = re.sub(r'```$', '', translation_text).strip()
            
            # Try to parse the entire response as JSON
            try:
                all_translations = json.loads(translation_text)
                
                # Validate and sanitize each translation
                for lang in languages_to_translate:
                    if lang in all_translations:
                        translated = all_translations[lang]
                        # Sanitize the translated content
                        for key in ['name', 'goal', 'description']:
                            if key in translated and translated[key]:
                                translated[key] = str(translated[key]).replace('\x00', '').strip()
                        if 'objectives' in translated:
                            translated['objectives'] = [
                                str(obj).replace('\x00', '').strip() 
                                for obj in translated['objectives']
                            ]
                        translations[lang] = translated
                    else:
                        # Language missing from response, use original as fallback
                        print(f"Translation missing for {lang}, using original content")
                        translations[lang] = content
                        
            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {str(je)}")
                # Try to extract JSON from the response
                json_match = re.search(r'\{.*\}', translation_text, re.DOTALL)
                if json_match:
                    try:
                        all_translations = json.loads(json_match.group())
                        for lang in languages_to_translate:
                            if lang in all_translations:
                                translations[lang] = all_translations[lang]
                            else:
                                translations[lang] = content
                    except:
                        # Fallback: Use original content for all languages
                        for lang in languages_to_translate:
                            translations[lang] = content
                else:
                    # Complete fallback
                    for lang in languages_to_translate:
                        translations[lang] = content
                        
        except Exception as e:
            print(f"Translation error: {str(e)}")
            # Use original content as fallback for all languages
            for lang in languages_to_translate:
                translations[lang] = content
        
        # Include English if it was in the original request
        if 'en' in target_languages:
            translations['en'] = content
            
        return translations

    def translate_single_field(self, field_name: str, field_value: Any, target_languages: List[str]) -> Dict[str, Any]:
        """Translate a single field to all target languages in one API call"""
        if not self.client:
            print("Warning: Anthropic API key not configured, skipping translation")
            return {}
        
        # Filter out English from target languages
        languages_to_translate = [lang for lang in target_languages if lang != 'en']
        
        if not languages_to_translate:
            return {}
        
        translations = {}
        
        try:
            # Build language map for the prompt
            language_map = {lang: self._get_language_name(lang) for lang in languages_to_translate}
            languages_list = ', '.join([f"{code} ({name})" for code, name in language_map.items()])
            
            # Prepare the content based on field type
            if field_name == 'objectives' and isinstance(field_value, list):
                content_str = json.dumps(field_value, ensure_ascii=False, indent=2)
                field_type = "learning objectives (array)"
            else:
                content_str = str(field_value).strip()
                field_type = field_name
            
            # Create a single prompt for translating just this field
            if field_name == 'description':
                prompt = f"""Translate the following course description from English to multiple languages.

Original description:
{content_str}

Target languages: {languages_list}

IMPORTANT: 
- Return ONLY a valid JSON object
- Preserve ALL formatting: line breaks (\\n), paragraphs, markdown (bold **, headers #, etc)
- Each translation must maintain the exact same structure as the original
- Ensure proper JSON escaping of special characters

Return this exact JSON structure:
{{
    "fr": "translated description with\\nline breaks preserved",
    "es": "descripción traducida con\\nsaltos de línea preservados",
    // ... other languages
}}"""
            elif field_name == 'objectives':
                prompt = f"""Translate the following learning objectives from English to multiple languages.

Objectives to translate:
{content_str}

Target languages: {languages_list}

Return a JSON object where each language maps to an array of translated objectives:
{{
    "fr": ["Objectif 1", "Objectif 2", ...],
    "es": ["Objetivo 1", "Objetivo 2", ...],
    // ... other languages
}}"""
            else:
                prompt = f"""Translate the following {field_type} from English to multiple languages.

Content: {content_str}

Target languages: {languages_list}

Return a simple JSON object:
{{
    "fr": "traduction française",
    "es": "traducción española",
    // ... other languages
}}"""
            
            # Call Claude API once for all languages
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4000,  # Increased for longer content
                temperature=0.3,
                system="You are a professional translator specializing in educational content about Bitcoin. You MUST return ONLY valid JSON without any markdown code blocks. For multi-line content, use \\n for line breaks within JSON strings. Never use triple backticks or ```json markers.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            translation_text = response.content[0].text.strip()
            
            # Clean the response text
            import re
            
            # Remove markdown code blocks if present
            if '```' in translation_text:
                # Try to extract JSON from markdown
                pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
                match = re.search(pattern, translation_text, re.DOTALL)
                if match:
                    translation_text = match.group(1).strip()
            
            # Remove comments (// ...) from JSON
            translation_text = re.sub(r'//.*?(?=\n|$)', '', translation_text)
            
            # Parse JSON response
            try:
                all_translations = json.loads(translation_text)
                
                # Validate each translation
                for lang in languages_to_translate:
                    if lang in all_translations:
                        value = all_translations[lang]
                        # Sanitize based on field type
                        if field_name == 'objectives' and isinstance(value, list):
                            translations[lang] = [str(obj).strip() for obj in value]
                        elif field_name == 'description' or field_name == 'goal':
                            # Preserve multi-line format for descriptions and goals
                            translations[lang] = str(value) if value else ''
                        else:
                            translations[lang] = str(value).strip() if value else ''
                    else:
                        print(f"Translation missing for {lang}")
                        
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                print(f"Response text: {translation_text[:500]}...")  # Log first 500 chars for debugging
                
                # Try to extract JSON from the response
                json_match = re.search(r'\{.*\}', translation_text, re.DOTALL)
                if json_match:
                    try:
                        all_translations = json.loads(json_match.group())
                        for lang in languages_to_translate:
                            if lang in all_translations:
                                translations[lang] = all_translations[lang]
                    except:
                        print("Failed to parse extracted JSON")
                        
        except Exception as e:
            print(f"Translation error for {field_name}: {str(e)}")
        
        return translations
    
    def _get_field_example(self, field_name: str) -> str:
        """Get example JSON for different field types"""
        examples = {
            'name': '''{"fr": "Bitcoin pour les entreprises", "es": "Bitcoin para empresas"}''',
            'goal': '''{"fr": "Apprendre les bases...", "es": "Aprender los conceptos..."}''',
            'objectives': '''{"fr": ["Premier objectif", "Deuxième objectif"], "es": ["Primer objetivo", "Segundo objetivo"]}''',
            'description': '''{"fr": "Ce cours enseigne...", "es": "Este curso enseña..."}'''
        }
        return examples.get(field_name, '''{"fr": "Traduction française", "es": "Traducción española"}''')
    
    def _get_language_name(self, code: str) -> str:
        """Convert language code to full language name"""
        language_map = {
            'en': 'English',
            'fr': 'French',
            'es': 'Spanish',
            'de': 'German',
            'it': 'Italian',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'ja': 'Japanese',
            'ko': 'Korean',
            'zh-Hans': 'Simplified Chinese',
            'zh-Hant': 'Traditional Chinese',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'cs': 'Czech',
            'nl': 'Dutch',
            'pl': 'Polish',
            'tr': 'Turkish',
            'vi': 'Vietnamese',
            'id': 'Indonesian',
            'fi': 'Finnish',
            'sv': 'Swedish',
            'nb-NO': 'Norwegian',
            'et': 'Estonian',
            'fa': 'Persian',
            'rn': 'Kirundi',
            'si': 'Sinhala',
            'sw': 'Swahili',
            'sr-Latn': 'Serbian (Latin)'
        }
        return language_map.get(code, code)
    
    def save_metadata(self, repo_key: str, course_name: str, new_index: str, 
                     metadata: Dict[str, Any]) -> bool:
        """Save only course metadata without touching content"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")
        
        course_path = repo_path / 'courses' / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")
        
        # Save metadata to course.yml
        course_yml_path = course_path / 'course.yml'
        if course_yml_path.exists():
            with open(course_yml_path, 'r', encoding='utf-8') as f:
                yml_content = f.read()
                yml_data = yaml.safe_load(yml_content) or {}
            
            # Update relevant fields
            yml_data['topic'] = metadata.get('topic', yml_data.get('topic', 'bitcoin'))
            yml_data['subtopic'] = metadata.get('subtopic', yml_data.get('subtopic', ''))
            yml_data['type'] = metadata.get('type', yml_data.get('type', 'theory'))
            yml_data['level'] = metadata.get('level', yml_data.get('level', 'beginner'))
            yml_data['hours'] = metadata.get('hours', yml_data.get('hours', 0))
            
            # Write back
            with open(course_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(yml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # Rename course folder if needed
        if new_index and new_index != course_name:
            new_course_path = repo_path / 'courses' / new_index
            if new_course_path.exists():
                raise ValueError(f"Course {new_index} already exists")
            course_path.rename(new_course_path)
        
        return True
    
    def update_field(self, repo_key: str, course_name: str, field_name: str, 
                    english_value: Any, translations: Dict[str, Dict[str, Any]]) -> bool:
        """Update a specific field in all language files"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")
        
        course_path = repo_path / 'courses' / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")
        
        # Update English file first
        en_file_path = course_path / 'en.md'
        if en_file_path.exists():
            self._update_file_field(en_file_path, field_name, english_value)
        
        # Find ALL language files in the course folder
        all_lang_files = list(course_path.glob("*.md"))
        
        # Update each language file
        for lang_file_path in all_lang_files:
            if lang_file_path.name == 'presentation.md':
                continue  # Skip presentation file
                
            lang = lang_file_path.stem
            
            # Skip English as we already updated it
            if lang == 'en':
                continue
            
            # Get the translated value for this language
            value = None
            if lang in translations:
                translated_content = translations[lang]
                # Extract the specific field from translation
                if field_name == 'objectives':
                    value = translated_content.get('objectives', [])
                else:
                    value = translated_content.get(field_name, '')
            
            # If we have a translation, update the file
            if value:
                self._update_file_field(lang_file_path, field_name, value)
            else:
                print(f"No translation found for {lang}, skipping update")
        
        return True
    
    def _update_file_field(self, file_path: Path, field_name: str, value: Any) -> None:
        """Update a specific field in a markdown file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse front matter
        front_matter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not front_matter_match:
            return
        
        front_matter = front_matter_match.group(1)
        rest_of_content = content[front_matter_match.end():]
        
        # Parse YAML front matter
        try:
            fm_data = yaml.safe_load(front_matter) or {}
        except:
            return
        
        # Update the specific field
        if field_name == 'name':
            fm_data['name'] = value
        elif field_name == 'goal':
            # For multi-line goals, ensure proper YAML formatting
            fm_data['goal'] = value
        elif field_name == 'objectives':
            fm_data['objectives'] = value if isinstance(value, list) else []
        elif field_name == 'description':
            # Description is in the body, not front matter
            # Find the section between --- and +++
            description_pattern = r'^(.*?)(\n\+\+\+)'
            match = re.search(description_pattern, rest_of_content, re.DOTALL)
            if match:
                # Replace everything before +++ with new description
                rest_of_content = value + match.group(2) + rest_of_content[match.end():]
            else:
                # If no +++ found, add it
                rest_of_content = value + '\n\n+++\n' + rest_of_content
        
        # Rebuild front matter with proper YAML formatting
        new_front_matter = "---\n"
        
        # Write each field properly
        if 'name' in fm_data and fm_data['name']:
            # Handle multi-line strings properly in YAML
            if '\n' in str(fm_data['name']):
                new_front_matter += f"name: |\n  {fm_data['name'].replace(chr(10), chr(10) + '  ')}\n"
            else:
                new_front_matter += f"name: {fm_data['name']}\n"
                
        if 'goal' in fm_data and fm_data['goal']:
            # Handle multi-line goals
            if '\n' in str(fm_data['goal']):
                new_front_matter += f"goal: |\n  {fm_data['goal'].replace(chr(10), chr(10) + '  ')}\n"
            else:
                new_front_matter += f"goal: {fm_data['goal']}\n"
                
        if 'objectives' in fm_data and fm_data['objectives']:
            new_front_matter += "objectives:\n"
            for obj in fm_data['objectives']:
                # Handle multi-line objectives
                obj_str = str(obj)
                if '\n' in obj_str:
                    new_front_matter += f"  - |\n    {obj_str.replace(chr(10), chr(10) + '    ')}\n"
                else:
                    new_front_matter += f"  - {obj_str}\n"
                    
        new_front_matter += "---\n"
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_front_matter + rest_of_content)

    def save_course_data(self, repo_key: str, course_name: str, new_index: str, 
                        metadata: Dict[str, Any], content: Dict[str, Dict[str, Any]]) -> bool:
        """Save course data back to files with automatic translation"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")
        
        course_path = repo_path / 'courses' / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")
        
        # Check if we have English content as the source for translation
        if 'en' in content and self.client:
            # Get list of languages that need translation
            languages_to_translate = [lang for lang in content.keys() if lang != 'en']
            
            if languages_to_translate:
                # Translate English content to other languages
                try:
                    translations = self.translate_content(content['en'], languages_to_translate)
                    # Update content with translations
                    for lang, translated_content in translations.items():
                        if lang in content:
                            content[lang] = translated_content
                except Exception as e:
                    print(f"Translation failed: {str(e)}, falling back to original content")
        
        # Save metadata to course.yml
        course_yml_path = course_path / 'course.yml'
        if course_yml_path.exists():
            with open(course_yml_path, 'r', encoding='utf-8') as f:
                yml_content = f.read()
                yml_data = yaml.safe_load(yml_content) or {}
            
            # Update relevant fields
            yml_data['topic'] = metadata.get('topic', yml_data.get('topic', 'bitcoin'))
            yml_data['subtopic'] = metadata.get('subtopic', yml_data.get('subtopic', ''))
            yml_data['type'] = metadata.get('type', yml_data.get('type', 'theory'))
            yml_data['level'] = metadata.get('level', yml_data.get('level', 'beginner'))
            yml_data['hours'] = metadata.get('hours', yml_data.get('hours', 0))
            
            # Write back
            with open(course_yml_path, 'w', encoding='utf-8') as f:
                yaml.dump(yml_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # Save content for each language
        for lang, lang_content in content.items():
            lang_file_path = course_path / f"{lang}.md"
            if lang_file_path.exists():
                # Read existing content
                with open(lang_file_path, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                
                # Update front matter
                new_front_matter = f"""---
name: {lang_content['name']}
goal: {lang_content['goal']}
objectives:"""
                
                for obj in lang_content['objectives']:
                    new_front_matter += f"\n  - {obj}"
                
                new_front_matter += "\n---"
                
                # Update description if it exists
                if lang_content['description']:
                    # Find and replace the description section
                    description_pattern = r'(---\s*\n.*?\n---\s*\n)(.*?)(\n\+\+\+)'
                    replacement = r'\1' + lang_content['description'] + r'\3'
                    new_content = re.sub(description_pattern, replacement, existing_content, count=1, flags=re.DOTALL)
                    
                    # Replace front matter
                    front_matter_pattern = r'^---\s*\n.*?\n---'
                    new_content = re.sub(front_matter_pattern, new_front_matter, new_content, count=1, flags=re.DOTALL)
                else:
                    # Just replace front matter
                    front_matter_pattern = r'^---\s*\n.*?\n---'
                    new_content = re.sub(front_matter_pattern, new_front_matter, existing_content, count=1, flags=re.DOTALL)
                
                # Write back
                with open(lang_file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
        
        # Rename course folder if needed
        if new_index != course_name:
            new_course_path = repo_path / 'courses' / new_index
            if new_course_path.exists():
                raise ValueError(f"Course {new_index} already exists")
            course_path.rename(new_course_path)
        
        return True