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

PLUS_DELIM_RE = re.compile(r'^[ \t]*\+\+\+[ \t]*$', re.M)


class CourseEditor:
    def __init__(self):
        """Initialize the course editor"""
        self.repositories = {
            "BEC_REPO": {
                "name": "Bitcoin Educational Content",
                "env_var": "BEC_REPO",
                "default_path": "../bitcoin-educational-content",
            },
            "PREMIUM_REPO": {
                "name": "Premium Content",
                "env_var": "PREMIUM_REPO",
                "default_path": "../planB-premium-content",
            },
        }

        # Initialize Claude API
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if self.anthropic_api_key:
            self.client = anthropic.Anthropic(
                api_key=self.anthropic_api_key,
                timeout=1800.0  # 30 minutes for long translations
            )
        else:
            self.client = None

    # ---------- Normalization and parsing helpers ----------

    def _normalize(self, s: str) -> str:
        """Normalize text to LF line endings and strip BOM."""
        if not isinstance(s, str):
            return s
        if s and s[0] == "\ufeff":
            s = s[1:]
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        return s

    def _split_front_matter(self, content: str):
        """
        Split leading YAML front matter and return (data_dict, body_str, fm_end_index).
        If no front matter, returns ({}, content, 0).
        """
        content = self._normalize(content)
        if not content.startswith("---"):
            return {}, content, 0
        m_start = re.match(r"^---[ \t]*\n", content)
        if not m_start:
            return {}, content, 0
        start = m_start.end()
        m_end = re.search(r"^\-\-\-[ \t]*\n?", content[start:], re.M)
        if not m_end:
            # malformed; treat as no front matter
            return {}, content, 0
        fm_end_line_end = start + m_end.end()  # index after closing '---\n'
        fm_text = content[start : start + m_end.start()]
        try:
            data = yaml.safe_load(fm_text) or {}
        except Exception:
            data = {}
        body = content[fm_end_line_end:]
        return data, body, fm_end_line_end

    def _split_description(self, body: str):
        """
        Split description and rest after +++ line.
        Returns (description_str, rest_after_plus_str, has_plus_bool).
        If +++ not found: returns (body.strip(), "", False).
        """
        body = self._normalize(body)
        m = PLUS_DELIM_RE.search(body)
        if not m:
            return body.strip(), "", False
        desc = body[: m.start()]
        rest = body[m.end() :]
        return desc.strip(), rest, True

    def _dump_front_matter(self, data: dict) -> str:
        """
        Dump YAML front matter using block scalars for multiline fields.
        """
        class LiteralStr(str):
            pass

        def literal_presenter(dumper, data):
            return dumper.represent_scalar(
                "tag:yaml.org,2002:str", data, style="|"
            )

        # register representer locally to avoid global side effects in other modules
        yaml.SafeDumper.add_representer(LiteralStr, literal_presenter)

        d = dict(data or {})
        for key in ("name", "goal"):
            v = d.get(key)
            if isinstance(v, str) and "\n" in v:
                d[key] = LiteralStr(v)
        if isinstance(d.get("objectives"), list):
            new_objs = []
            for x in d["objectives"]:
                if isinstance(x, str) and "\n" in x:
                    new_objs.append(LiteralStr(x))
                else:
                    new_objs.append(x)
            d["objectives"] = new_objs

        dumped = yaml.dump(
            d,
            Dumper=yaml.SafeDumper,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).rstrip()
        return f"---\n{dumped}\n---\n"

    # ---------- Repository and course listing ----------

    def _get_repo_path(self, repo_key: str) -> Optional[Path]:
        """Get the path for a repository"""
        if repo_key not in self.repositories:
            return None

        repo_info = self.repositories[repo_key]
        env_path = os.getenv(repo_info["env_var"])

        if env_path:
            path = Path(env_path)
            if not path.is_absolute():
                path = Path.cwd() / path
        else:
            path = Path.cwd() / repo_info["default_path"]

        if path.exists() and (path / "courses").exists():
            return path
        return None

    def list_all_courses(self) -> List[Dict[str, Any]]:
        """List all courses from both repositories"""
        courses = []

        for repo_key, repo_info in self.repositories.items():
            repo_path = self._get_repo_path(repo_key)
            if not repo_path:
                continue

            courses_dir = repo_path / "courses"
            if not courses_dir.exists():
                continue

            for course_dir in courses_dir.iterdir():
                if not course_dir.is_dir():
                    continue

                # Check if it's a valid course (has en.md or course.yml)
                if (course_dir / "course.yml").exists() or (course_dir / "en.md").exists():
                    courses.append(
                        {
                            "name": course_dir.name.upper(),
                            "path": course_dir.name,
                            "repo": repo_key,
                            "repo_name": repo_info["name"],
                        }
                    )

        return sorted(courses, key=lambda x: (x["repo"], x["name"]))

    def load_course_data(self, repo_key: str, course_name: str) -> Dict[str, Any]:
        """Load all course data including metadata and content for all languages"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")

        course_path = repo_path / "courses" / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")

        result = {"metadata": {}, "content": {}, "languages": []}

        # Load metadata from course.yml
        course_yml_path = course_path / "course.yml"
        if course_yml_path.exists():
            with open(course_yml_path, "r", encoding="utf-8") as f:
                yml_content = f.read()
                # Parse YAML
                try:
                    yml_data = yaml.safe_load(yml_content)
                    if yml_data:
                        result["metadata"] = {
                            "topic": yml_data.get("topic", ""),
                            "subtopic": yml_data.get("subtopic", ""),
                            "type": yml_data.get("type", ""),
                            "level": yml_data.get("level", ""),
                            "hours": yml_data.get("hours", 0),
                        }
                except Exception:
                    pass

        # Find all language files
        for file_path in course_path.iterdir():
            if (
                file_path.is_file()
                and file_path.suffix == ".md"
                and file_path.name != "presentation.md"
            ):
                lang = file_path.stem
                result["languages"].append(lang)

                # Parse the markdown file
                content = self._parse_markdown_file(file_path)
                result["content"][lang] = content

        result["languages"].sort()
        # Ensure 'en' is first if it exists
        if "en" in result["languages"]:
            result["languages"].remove("en")
            result["languages"].insert(0, "en")

        return result

    # ---------- File parsing ----------

    def _parse_markdown_file(self, file_path: Path) -> Dict[str, Any]:
        """Parse a course markdown file to extract metadata and description"""
        with open(file_path, "r", encoding="utf-8") as f:
            raw = self._normalize(f.read())

        data, body, _ = self._split_front_matter(raw)
        description, _, _has_plus = self._split_description(body)

        return {
            "name": data.get("name", "") or "",
            "goal": data.get("goal", "") or "",
            "objectives": data.get("objectives", []) or [],
            "description": description,
        }

    # ---------- Translation ----------

    def translate_content(
        self, content: Dict[str, Any], target_languages: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Translate course content to all target languages in one API call using Claude"""
        if not self.client:
            print("Warning: Anthropic API key not configured, skipping translation")
            # Return original content for all languages
            return {lang: content for lang in target_languages}

        # Skip if no languages to translate
        if not target_languages or (len(target_languages) == 1 and "en" in target_languages):
            return {"en": content} if "en" in target_languages else {}

        # Filter out English from target languages
        languages_to_translate = [lang for lang in target_languages if lang != "en"]

        if not languages_to_translate:
            return {"en": content} if "en" in target_languages else {}

        translations = {}

        try:
            # Sanitize content before sending
            sanitized_content = {
                "name": str(content.get("name", "")).replace("\x00", "").strip(),
                "goal": str(content.get("goal", "")).replace("\x00", "").strip(),
                "objectives": [
                    str(obj).replace("\x00", "").strip()
                    for obj in content.get("objectives", [])
                    if obj
                ],
                "description": str(content.get("description", "")).replace("\x00", "").strip(),
            }

            # Build language map for the prompt
            language_map = {
                lang: self._get_language_name(lang) for lang in languages_to_translate
            }

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
}}"""

            # Call Claude API once for all languages
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=50000,  # Increased for multiple languages
                temperature=0.3,
                system="You are a professional translator specializing in educational content about Bitcoin and cryptocurrency. Always return valid JSON with translations for ALL requested languages. Never use markdown formatting.",
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            translation_text = response.content[0].text.strip()

            # Remove any control characters from response
            translation_text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", translation_text)

            # Clean up the response - remove markdown if present
            if translation_text.startswith("```"):
                translation_text = re.sub(r"^```(?:json)?", "", translation_text)
                translation_text = re.sub(r"```$", "", translation_text).strip()

            # Try to parse the entire response as JSON
            try:
                all_translations = json.loads(translation_text)

                # Validate and sanitize each translation
                for lang in languages_to_translate:
                    if lang in all_translations:
                        translated = all_translations[lang]
                        # Sanitize the translated content
                        for key in ["name", "goal", "description"]:
                            if key in translated and translated[key]:
                                translated[key] = str(translated[key]).replace("\x00", "").strip()
                        if "objectives" in translated:
                            translated["objectives"] = [
                                str(obj).replace("\x00", "").strip()
                                for obj in translated["objectives"]
                            ]
                        translations[lang] = translated
                    else:
                        # Language missing from response, use original as fallback
                        print(f"Translation missing for {lang}, using original content")
                        translations[lang] = content

            except json.JSONDecodeError as je:
                print(f"JSON parsing error: {str(je)}")
                # Try to extract JSON from the response
                json_match = re.search(r"\{.*\}", translation_text, re.DOTALL)
                if json_match:
                    try:
                        all_translations = json.loads(json_match.group())
                        for lang in languages_to_translate:
                            if lang in all_translations:
                                translations[lang] = all_translations[lang]
                            else:
                                translations[lang] = content
                    except Exception:
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
        if "en" in target_languages:
            translations["en"] = content

        return translations

    def translate_single_field(
        self, field_name: str, field_value: Any, target_languages: List[str]
    ) -> Dict[str, Any]:
        """Translate a single field to all target languages with batching for large content"""
        if not self.client:
            print("Warning: Anthropic API key not configured, skipping translation")
            return {}

        # Filter out English from target languages
        languages_to_translate = [lang for lang in target_languages if lang != "en"]

        if not languages_to_translate:
            return {}

        # For descriptions with many languages, batch them to avoid token limits
        if field_name == "description" and len(languages_to_translate) > 8:
            return self._translate_field_batched(field_name, field_value, languages_to_translate)

        translations = {}

        try:
            # Build language map for the prompt
            language_map = {
                lang: self._get_language_name(lang) for lang in languages_to_translate
            }
            languages_list = ", ".join([f"{code} ({name})" for code, name in language_map.items()])

            # Prepare the content based on field type
            if field_name == "objectives" and isinstance(field_value, list):
                content_str = json.dumps(field_value, ensure_ascii=False, indent=2)
                field_type = "learning objectives (array)"
            else:
                content_str = str(field_value).strip()
                field_type = field_name

            # Create a single prompt for translating just this field
            if field_name == "description":
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
    "es": "descripción traducida con\\nsaltos de línea preservados"
}}"""
            elif field_name == "objectives":
                prompt = f"""Translate the following learning objectives from English to multiple languages.

Objectives to translate:
{content_str}

Target languages: {languages_list}

Return a JSON object where each language maps to an array of translated objectives:
{{
    "fr": ["Objectif 1", "Objectif 2"],
    "es": ["Objetivo 1", "Objetivo 2"]
}}"""
            else:
                prompt = f"""Translate the following {field_type} from English to multiple languages.

Content: {content_str}

Target languages: {languages_list}

Return a simple JSON object:
{{
    "fr": "traduction française",
    "es": "traducción española"
}}"""

            # Determine max_tokens based on field and number of languages
            if field_name == "description":
                max_tokens = 50000
            else:
                max_tokens = 50000

            # Call Claude API once for all languages
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=int(max_tokens),
                temperature=0.3,
                system=(
                    "You are a professional translator specializing in educational content about Bitcoin. "
                    "You MUST return ONLY valid JSON without any markdown code blocks. "
                    "For multi-line content, use \\n for line breaks within JSON strings. "
                    "Never use triple backticks or ```json markers."
                ),
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse response
            translation_text = response.content[0].text.strip()

            # Remove markdown code blocks if present
            if "```" in translation_text:
                pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
                match = re.search(pattern, translation_text, re.DOTALL)
                if match:
                    translation_text = match.group(1).strip()

            # Remove comments (// ...) from JSON
            translation_text = re.sub(r"//.*?(?=\n|$)", "", translation_text)

            # Parse JSON response
            try:
                all_translations = json.loads(translation_text)

                # Validate each translation
                for lang in languages_to_translate:
                    if lang in all_translations:
                        value = all_translations[lang]
                        # Sanitize based on field type
                        if field_name == "objectives" and isinstance(value, list):
                            translations[lang] = [str(obj).strip() for obj in value]
                        elif field_name in ("description", "goal"):
                            translations[lang] = str(value) if value else ""
                        else:
                            translations[lang] = str(value).strip() if value else ""
                    else:
                        print(f"Translation missing for {lang}")

            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                print(f"Response text: {translation_text[:500]}...")  # Log first 500 chars for debugging

                # Try to extract JSON from the response
                json_match = re.search(r"\{.*\}", translation_text, re.DOTALL)
                if json_match:
                    try:
                        all_translations = json.loads(json_match.group())
                        for lang in languages_to_translate:
                            if lang in all_translations:
                                translations[lang] = all_translations[lang]
                    except Exception:
                        print("Failed to parse extracted JSON")

        except Exception as e:
            print(f"Translation error for {field_name}: {str(e)}")

        return translations

    def _translate_field_batched(
        self, field_name: str, field_value: Any, target_languages: List[str], batch_size: int = 6
    ) -> Dict[str, Any]:
        """Translate a field in batches to avoid token limits"""
        all_translations = {}
        
        # Split languages into batches
        for i in range(0, len(target_languages), batch_size):
            batch = target_languages[i:i + batch_size]
            print(f"Translating batch {i//batch_size + 1} ({len(batch)} languages): {', '.join(batch)}")
            
            # Translate this batch
            batch_translations = {}
            try:
                language_map = {lang: self._get_language_name(lang) for lang in batch}
                languages_list = ", ".join([f"{code} ({name})" for code, name in language_map.items()])
                
                content_str = str(field_value).strip()
                
                prompt = f"""Translate the following course description from English to these specific languages.

Original description:
{content_str}

Target languages: {languages_list}

IMPORTANT: 
- Return ONLY a valid JSON object with ALL {len(batch)} languages
- Preserve ALL formatting: line breaks (\\n), paragraphs, markdown (bold **, headers #, etc)
- Each translation must maintain the exact same structure as the original
- Ensure proper JSON escaping of special characters
- Do NOT truncate translations - complete ALL of them

Return JSON with all {len(batch)} languages."""

                response = self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=50000,
                    temperature=0.3,
                    system=(
                        "You are a professional translator specializing in educational content about Bitcoin. "
                        "Return ONLY valid JSON. Use \\n for line breaks. Complete ALL translations fully."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                )

                translation_text = response.content[0].text.strip()
                
                # Clean up response
                if "```" in translation_text:
                    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
                    match = re.search(pattern, translation_text, re.DOTALL)
                    if match:
                        translation_text = match.group(1).strip()
                
                translation_text = re.sub(r"//.*?(?=\n|$)", "", translation_text)
                
                # Parse JSON
                batch_translations = json.loads(translation_text)
                
                # Add to all_translations
                for lang in batch:
                    if lang in batch_translations:
                        all_translations[lang] = batch_translations[lang]
                        print(f"✓ Translated {lang}")
                    else:
                        print(f"✗ Missing translation for {lang}")
                        
            except Exception as e:
                print(f"Error translating batch: {str(e)}")
                # Continue with next batch even if this one fails
                
        print(f"Completed: {len(all_translations)}/{len(target_languages)} languages translated")
        return all_translations

    def _get_field_example(self, field_name: str) -> str:
        """Get example JSON for different field types"""
        examples = {
            "name": '''{"fr": "Bitcoin pour les entreprises", "es": "Bitcoin para empresas"}''',
            "goal": '''{"fr": "Apprendre les bases...", "es": "Aprender los conceptos..."}''',
            "objectives": '''{"fr": ["Premier objectif", "Deuxième objectif"], "es": ["Primer objetivo", "Segundo objetivo"]}''',
            "description": '''{"fr": "Ce cours enseigne...", "es": "Este curso enseña..."}''',
        }
        return examples.get(
            field_name, '''{"fr": "Traduction française", "es": "Traducción española"}'''
        )

    def _get_language_name(self, code: str) -> str:
        """Convert language code to full language name"""
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

    # ---------- Save/update operations ----------

    def save_metadata(
        self, repo_key: str, course_name: str, new_index: str, metadata: Dict[str, Any]
    ) -> bool:
        """Save only course metadata without touching content"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")

        course_path = repo_path / "courses" / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")

        # Save metadata to course.yml
        course_yml_path = course_path / "course.yml"
        if course_yml_path.exists():
            with open(course_yml_path, "r", encoding="utf-8") as f:
                yml_content = f.read()
                yml_data = yaml.safe_load(yml_content) or {}

            # Update relevant fields
            yml_data["topic"] = metadata.get("topic", yml_data.get("topic", "bitcoin"))
            yml_data["subtopic"] = metadata.get("subtopic", yml_data.get("subtopic", ""))
            yml_data["type"] = metadata.get("type", yml_data.get("type", "theory"))
            yml_data["level"] = metadata.get("level", yml_data.get("level", "beginner"))
            yml_data["hours"] = metadata.get("hours", yml_data.get("hours", 0))

            # Write back
            with open(course_yml_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    yml_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )

        # Rename course folder if needed
        if new_index and new_index != course_name:
            new_course_path = repo_path / "courses" / new_index
            if new_course_path.exists():
                raise ValueError(f"Course {new_index} already exists")
            course_path.rename(new_course_path)

        return True

    def update_field(
        self,
        repo_key: str,
        course_name: str,
        field_name: str,
        english_value: Any,
        translations: Dict[str, Dict[str, Any]] = None,
    ) -> bool:
        """Update a specific field in all language files with auto-translation"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")

        course_path = repo_path / "courses" / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")

        # Update English file first
        en_file_path = course_path / "en.md"
        if en_file_path.exists():
            self._update_file_field(en_file_path, field_name, english_value)

        # Find ALL language files in the course folder (excluding presentation.md)
        all_lang_files = [f for f in course_path.glob("*.md") if f.name != "presentation.md"]
        target_languages = [f.stem for f in all_lang_files if f.stem != "en"]

        # Auto-translate if translations not provided
        if not translations and target_languages:
            print(f"Auto-translating {field_name} to {len(target_languages)} languages...")
            translations_dict = self.translate_single_field(field_name, english_value, target_languages)
        else:
            translations_dict = translations or {}

        # Update each non-English language file
        for lang_file_path in all_lang_files:
            lang = lang_file_path.stem
            
            if lang == "en":
                continue  # Already updated

            # Get translated value for this language
            if lang in translations_dict:
                # Handle both formats: direct value or nested dict
                if isinstance(translations_dict[lang], dict):
                    value = translations_dict[lang].get(field_name)
                else:
                    value = translations_dict[lang]
                
                if value is not None and (value != "" or field_name == "objectives"):
                    self._update_file_field(lang_file_path, field_name, value)
                    print(f"Updated {field_name} in {lang}")
                else:
                    print(f"No translation for {field_name} in {lang}, skipping")
            else:
                print(f"No translation found for {lang}, skipping")

        return True

    def _update_file_field(self, file_path: Path, field_name: str, value: Any) -> None:
        """Update a specific field in a markdown file"""
        with open(file_path, "r", encoding="utf-8") as f:
            raw = self._normalize(f.read())

        data, body, fm_end_idx = self._split_front_matter(raw)

        # Ensure data exists
        if not isinstance(data, dict):
            data = {}

        if field_name == "name":
            data["name"] = value or ""
        elif field_name == "goal":
            data["goal"] = value or ""
        elif field_name == "objectives":
            data["objectives"] = value if isinstance(value, list) else []
        elif field_name == "description":
            # Simple: description is between YAML end and +++ line
            desc, rest_after, has_plus = self._split_description(body)
            new_desc = str(value or "").strip()
            
            # Reconstruct body with new description
            if has_plus:
                new_body = f"{new_desc}\n+++\n{rest_after.lstrip()}"
            else:
                # No +++ found, just replace entire body with description + +++
                new_body = f"{new_desc}\n+++\n"
            
            fm = self._dump_front_matter(data)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(fm + new_body)
            return
        else:
            # Unknown field; no-op
            return

        # Rebuild with updated front matter and preserve body unchanged
        fm = self._dump_front_matter(data)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(fm + body)

    def save_course_data(
        self,
        repo_key: str,
        course_name: str,
        new_index: str,
        metadata: Dict[str, Any],
        content: Dict[str, Dict[str, Any]],
    ) -> bool:
        """Save course data back to files with automatic translation"""
        repo_path = self._get_repo_path(repo_key)
        if not repo_path:
            raise ValueError(f"Repository {repo_key} not found")

        course_path = repo_path / "courses" / course_name
        if not course_path.exists():
            raise ValueError(f"Course {course_name} not found")

        # Translate from English to other languages if possible
        if "en" in content and self.client:
            # Get list of languages that need translation
            languages_to_translate = [lang for lang in content.keys() if lang != "en"]

            if languages_to_translate:
                try:
                    translations = self.translate_content(
                        content["en"], languages_to_translate
                    )
                    # Update content with translations (only for those languages present)
                    for lang, translated_content in translations.items():
                        if lang in content:
                            content[lang] = translated_content
                except Exception as e:
                    print(
                        f"Translation failed: {str(e)}, falling back to original content"
                    )

        # Save metadata to course.yml
        course_yml_path = course_path / "course.yml"
        if course_yml_path.exists():
            with open(course_yml_path, "r", encoding="utf-8") as f:
                yml_content = f.read()
                yml_data = yaml.safe_load(yml_content) or {}

            # Update relevant fields
            yml_data["topic"] = metadata.get("topic", yml_data.get("topic", "bitcoin"))
            yml_data["subtopic"] = metadata.get("subtopic", yml_data.get("subtopic", ""))
            yml_data["type"] = metadata.get("type", yml_data.get("type", "theory"))
            yml_data["level"] = metadata.get("level", yml_data.get("level", "beginner"))
            yml_data["hours"] = metadata.get("hours", yml_data.get("hours", 0))

            # Write back
            with open(course_yml_path, "w", encoding="utf-8") as f:
                yaml.dump(
                    yml_data,
                    f,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                )

        # Save content for each language file by parsing and reconstructing
        for lang, lang_content in content.items():
            lang_file_path = course_path / f"{lang}.md"
            if not lang_file_path.exists():
                continue

            with open(lang_file_path, "r", encoding="utf-8") as f:
                raw = self._normalize(f.read())

            data, body, _ = self._split_front_matter(raw)

            # Update YAML fields from lang_content
            if "name" in lang_content:
                data["name"] = lang_content.get("name", data.get("name", ""))
            if "goal" in lang_content:
                data["goal"] = lang_content.get("goal", data.get("goal", ""))
            if "objectives" in lang_content and isinstance(
                lang_content.get("objectives"), list
            ):
                data["objectives"] = lang_content.get(
                    "objectives", data.get("objectives", [])
                )

            # Update description if provided (None means leave unchanged)
            if "description" in lang_content and lang_content["description"] is not None:
                new_desc = str(lang_content["description"])
                _, rest_after, has_plus = self._split_description(body)
                if has_plus:
                    body = f"{new_desc.strip()}\n+++\n{rest_after.lstrip()}"
                else:
                    body = f"{new_desc.strip()}\n+++\n{body}"

            fm = self._dump_front_matter(data)
            with open(lang_file_path, "w", encoding="utf-8") as f:
                f.write(fm + body)

        # Rename course folder if needed
        if new_index and new_index != course_name:
            new_course_path = repo_path / "courses" / new_index
            if new_course_path.exists():
                raise ValueError(f"Course {new_index} already exists")
            course_path.rename(new_course_path)

        return True
