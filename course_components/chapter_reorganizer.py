"""
Chapter Reorganization Module
Handles moving and deleting chapters/parts in structured markdown files
"""

import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass


@dataclass
class Operation:
    """Represents a reorganization operation"""
    action: str  # 'move_chapter' or 'delete_part'
    source_id: Optional[str] = None  # chapter_id or part_id
    target_id: Optional[str] = None  # insert_after_chapter_id


class ChapterNotFoundError(Exception):
    """Raised when a chapter ID is not found in the content."""
    pass


class PartNotFoundError(Exception):
    """Raised when a part ID is not found in the content."""
    pass


class InvalidOperationError(Exception):
    """Raised when an operation is invalid (e.g., circular move)."""
    pass


class ChapterReorganizer:
    """Handles chapter and part reorganization in markdown files"""
    
    def __init__(self):
        pass
    
    def find_chapter_boundaries(self, content: str, chapter_id: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Find start and end positions of a chapter.
        
        Args:
            content: Full markdown file content
            chapter_id: UUID of the chapter (without angle brackets)
        
        Returns:
            Tuple of (start_position, end_position) or (None, None) if not found
        """
        # Pattern to find chapter start: ## Title\n<chapterId>uuid</chapterId>
        start_pattern = rf'^##\s+[^\n]+\s*\n\s*<chapterId>{re.escape(chapter_id)}</chapterId>'
        
        # Find the chapter start
        start_match = re.search(start_pattern, content, re.MULTILINE)
        if not start_match:
            return None, None
        
        start_pos = start_match.start()
        
        # Pattern to find chapter end (next chapter ## or next part # but not ##)
        # Use lookahead to find position without consuming it
        end_pattern = r'\n(?=##\s|\n#\s[^#])'
        
        # Search for end pattern after the chapter start
        end_match = re.search(end_pattern, content[start_pos:], re.MULTILINE)
        
        if end_match:
            end_pos = start_pos + end_match.start()
        else:
            # Chapter extends to end of file
            end_pos = len(content)
        
        return start_pos, end_pos
    
    def find_part_boundaries(self, content: str, part_id: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Find start and end positions of a part section.
        
        Args:
            content: Full markdown file content
            part_id: UUID of the part (without angle brackets)
        
        Returns:
            Tuple of (start_position, end_position) or (None, None) if not found
        """
        # Pattern to find part start: # Title\n<partId>uuid</partId>
        start_pattern = rf'^#\s+[^\n]+\s*\n\s*<partId>{re.escape(part_id)}</partId>'
        
        # Find the part start
        start_match = re.search(start_pattern, content, re.MULTILINE)
        if not start_match:
            return None, None
        
        start_pos = start_match.start()
        
        # Pattern to find part end (next part # but not ##)
        # Use lookahead to find position without consuming it
        end_pattern = r'\n(?=#\s[^#])'
        
        # Search for end pattern after the part start
        end_match = re.search(end_pattern, content[start_pos:], re.MULTILINE)
        
        if end_match:
            end_pos = start_pos + end_match.start()
        else:
            # Part extends to end of file
            end_pos = len(content)
        
        return start_pos, end_pos
    
    def extract_chapter_content(self, content: str, chapter_id: str) -> Optional[str]:
        """
        Extract the full content of a chapter.
        
        Args:
            content: Full markdown file content
            chapter_id: UUID of the chapter
        
        Returns:
            Chapter content as string, or None if not found
        """
        start_pos, end_pos = self.find_chapter_boundaries(content, chapter_id)
        if start_pos is None:
            return None
        
        return content[start_pos:end_pos]
    
    def extract_part_content(self, content: str, part_id: str) -> Optional[str]:
        """
        Extract the full content of a part.
        
        Args:
            content: Full markdown file content
            part_id: UUID of the part
        
        Returns:
            Part content as string, or None if not found
        """
        start_pos, end_pos = self.find_part_boundaries(content, part_id)
        if start_pos is None:
            return None
        
        return content[start_pos:end_pos]
    
    def delete_chapter(self, content: str, chapter_id: str) -> str:
        """
        Delete a chapter from the content.
        
        Args:
            content: Full markdown file content
            chapter_id: UUID of the chapter to delete
        
        Returns:
            Updated content with chapter removed
        
        Raises:
            ChapterNotFoundError: If chapter is not found
        """
        start_pos, end_pos = self.find_chapter_boundaries(content, chapter_id)
        if start_pos is None:
            raise ChapterNotFoundError(f"Chapter {chapter_id} not found")
        
        # Delete the chapter by slicing it out
        return content[:start_pos] + content[end_pos:]
    
    def delete_part(self, content: str, part_id: str) -> str:
        """
        Delete a part (including all its chapters) from the content.
        
        Args:
            content: Full markdown file content
            part_id: UUID of the part to delete
        
        Returns:
            Updated content with part removed
        
        Raises:
            PartNotFoundError: If part is not found
        """
        start_pos, end_pos = self.find_part_boundaries(content, part_id)
        if start_pos is None:
            raise PartNotFoundError(f"Part {part_id} not found")
        
        # Delete the part by slicing it out
        return content[:start_pos] + content[end_pos:]
    
    def move_chapter_after(self, content: str, source_chapter_id: str, target_chapter_id: str) -> str:
        """
        Move a chapter to appear after a target chapter.
        
        Args:
            content: Full markdown file content
            source_chapter_id: UUID of chapter to move
            target_chapter_id: UUID of chapter to insert after
        
        Returns:
            Updated content with chapter moved
        
        Raises:
            ChapterNotFoundError: If either chapter is not found
        """
        # Phase 1: Extract the chapter content to move
        chapter_content = self.extract_chapter_content(content, source_chapter_id)
        if chapter_content is None:
            raise ChapterNotFoundError(f"Source chapter {source_chapter_id} not found")
        
        # Validate target exists before deletion
        target_start, target_end = self.find_chapter_boundaries(content, target_chapter_id)
        if target_start is None:
            raise ChapterNotFoundError(f"Target chapter {target_chapter_id} not found")
        
        # Phase 2: Delete the source chapter
        content = self.delete_chapter(content, source_chapter_id)
        
        # Phase 3: Re-find target position (changed after deletion)
        target_start, target_end = self.find_chapter_boundaries(content, target_chapter_id)
        if target_start is None:
            raise ChapterNotFoundError(f"Target chapter {target_chapter_id} not found after deletion")
        
        # Phase 4: Insert after target chapter with proper spacing
        # Insert with exactly TWO newlines for separation
        new_content = content[:target_end] + '\n\n' + chapter_content + content[target_end:]
        
        return new_content
    
    def apply_operations(self, content: str, operations: List[Operation]) -> str:
        """
        Apply a list of reorganization operations to content.
        
        Operations are applied in order:
        1. All deletions (in reverse position order)
        2. All moves (processed carefully to maintain position integrity)
        
        Args:
            content: Full markdown file content
            operations: List of operations to apply
        
        Returns:
            Updated content with all operations applied
        """
        # Separate operations by type
        delete_ops = []
        move_ops = []
        
        for op in operations:
            if op.action == 'delete_part':
                delete_ops.append(op)
            elif op.action == 'move_chapter':
                move_ops.append(op)
        
        # Phase 1: Collect deletion positions and sort in reverse order
        deletion_positions = []
        for op in delete_ops:
            if op.source_id:
                start_pos, end_pos = self.find_part_boundaries(content, op.source_id)
                if start_pos is not None:
                    deletion_positions.append({
                        'type': 'part',
                        'id': op.source_id,
                        'start': start_pos,
                        'end': end_pos
                    })
        
        # Sort deletions in reverse order (high to low) to maintain position integrity
        deletion_positions.sort(key=lambda x: x['start'], reverse=True)
        
        # Phase 2: Apply deletions in reverse order
        for deletion in deletion_positions:
            content = content[:deletion['start']] + content[deletion['end']:]
        
        # Phase 3: Apply move operations sequentially
        # Each move will re-find positions as they change
        for op in move_ops:
            if op.source_id and op.target_id:
                content = self.move_chapter_after(content, op.source_id, op.target_id)
        
        return content
    
    def reorganize_file(self, file_path: Path, operations: List[Operation]) -> None:
        """
        Apply reorganization operations to a single file.
        
        Args:
            file_path: Path to markdown file
            operations: List of move/delete operations to perform
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ChapterNotFoundError: If a chapter is not found
            PartNotFoundError: If a part is not found
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Read file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Apply operations
        new_content = self.apply_operations(content, operations)
        
        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
    
    def reorganize_course(self, course_path: Path, operations: List[Operation], 
                         language_filter: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Apply reorganization operations to all markdown files in a course.
        
        Args:
            course_path: Path to course directory
            operations: List of operations to apply
            language_filter: Optional list of language codes to process (e.g., ['en', 'fr'])
                           If None, processes all markdown files
        
        Returns:
            Dictionary with results:
            {
                'success': bool,
                'files_processed': int,
                'files_failed': int,
                'errors': [list of error messages]
            }
        """
        if not course_path.exists() or not course_path.is_dir():
            raise ValueError(f"Invalid course path: {course_path}")
        
        results = {
            'success': True,
            'files_processed': 0,
            'files_failed': 0,
            'errors': []
        }
        
        # Find all markdown files
        md_files = list(course_path.glob('*.md'))
        
        # Filter by language if specified
        if language_filter:
            md_files = [f for f in md_files if f.stem in language_filter]
        
        # Exclude presentation.md
        md_files = [f for f in md_files if f.name != 'presentation.md']
        
        # Process each file
        for md_file in md_files:
            try:
                self.reorganize_file(md_file, operations)
                results['files_processed'] += 1
            except Exception as e:
                results['success'] = False
                results['files_failed'] += 1
                results['errors'].append(f"{md_file.name}: {str(e)}")
        
        return results
    
    def validate_operations(self, content: str, operations: List[Operation]) -> List[str]:
        """
        Validate operations before applying them.
        
        Args:
            content: Markdown content to validate against
            operations: List of operations to validate
        
        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []
        
        for i, op in enumerate(operations):
            if op.action == 'move_chapter':
                # Validate source chapter exists
                if op.source_id:
                    start, end = self.find_chapter_boundaries(content, op.source_id)
                    if start is None:
                        errors.append(f"Operation {i+1}: Source chapter {op.source_id} not found")
                else:
                    errors.append(f"Operation {i+1}: Missing source_id for move_chapter")
                
                # Validate target chapter exists
                if op.target_id:
                    start, end = self.find_chapter_boundaries(content, op.target_id)
                    if start is None:
                        errors.append(f"Operation {i+1}: Target chapter {op.target_id} not found")
                else:
                    errors.append(f"Operation {i+1}: Missing target_id for move_chapter")
                
            elif op.action == 'delete_part':
                # Validate part exists
                if op.source_id:
                    start, end = self.find_part_boundaries(content, op.source_id)
                    if start is None:
                        errors.append(f"Operation {i+1}: Part {op.source_id} not found")
                else:
                    errors.append(f"Operation {i+1}: Missing source_id for delete_part")
            else:
                errors.append(f"Operation {i+1}: Unknown action '{op.action}'")
        
        return errors
    
    def parse_course_structure(self, content: str) -> Dict[str, Any]:
        """
        Parse course structure to extract parts and chapters for UI.
        
        Args:
            content: Markdown content
        
        Returns:
            Dictionary with structure:
            {
                'parts': [
                    {
                        'id': 'uuid',
                        'title': 'Part Title',
                        'chapters': [
                            {'id': 'uuid', 'title': 'Chapter Title'},
                            ...
                        ]
                    },
                    ...
                ],
                'orphan_chapters': [  # Chapters not in any part
                    {'id': 'uuid', 'title': 'Chapter Title'},
                    ...
                ]
            }
        """
        structure = {
            'parts': [],
            'orphan_chapters': []
        }
        
        # Find all parts
        part_pattern = r'^#\s+([^\n]+)\s*\n\s*<partId>([^<]+)</partId>'
        part_matches = list(re.finditer(part_pattern, content, re.MULTILINE))
        
        # Find all chapters
        chapter_pattern = r'^##\s+([^\n]+)\s*\n\s*<chapterId>([^<]+)</chapterId>'
        chapter_matches = list(re.finditer(chapter_pattern, content, re.MULTILINE))
        
        # Process parts
        for i, part_match in enumerate(part_matches):
            part_title = part_match.group(1).strip()
            part_id = part_match.group(2).strip()
            part_start = part_match.start()
            
            # Determine part end (start of next part or end of content)
            if i + 1 < len(part_matches):
                part_end = part_matches[i + 1].start()
            else:
                part_end = len(content)
            
            # Find chapters within this part
            part_chapters = []
            for chapter_match in chapter_matches:
                chapter_pos = chapter_match.start()
                if part_start < chapter_pos < part_end:
                    chapter_title = chapter_match.group(1).strip()
                    chapter_id = chapter_match.group(2).strip()
                    part_chapters.append({
                        'id': chapter_id,
                        'title': chapter_title,
                        'position': chapter_pos
                    })
            
            # Sort chapters by position
            part_chapters.sort(key=lambda x: x['position'])
            
            # Remove position from output
            for chapter in part_chapters:
                del chapter['position']
            
            structure['parts'].append({
                'id': part_id,
                'title': part_title,
                'chapters': part_chapters
            })
        
        # Find orphan chapters (chapters before first part or after last part)
        if part_matches:
            first_part_start = part_matches[0].start()
            
            for chapter_match in chapter_matches:
                chapter_pos = chapter_match.start()
                
                # Check if chapter is before first part
                if chapter_pos < first_part_start:
                    chapter_title = chapter_match.group(1).strip()
                    chapter_id = chapter_match.group(2).strip()
                    structure['orphan_chapters'].append({
                        'id': chapter_id,
                        'title': chapter_title
                    })
        else:
            # No parts found, all chapters are orphans
            for chapter_match in chapter_matches:
                chapter_title = chapter_match.group(1).strip()
                chapter_id = chapter_match.group(2).strip()
                structure['orphan_chapters'].append({
                    'id': chapter_id,
                    'title': chapter_title
                })
        
        return structure
