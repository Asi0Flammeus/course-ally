# Course Editor Feature

## Overview
The Course Editor is a web-based tool for batch editing course information across multiple languages with automatic translation support.

## Features

### 1. Course Selection
- **Mixed Repository Support**: Browse and edit courses from both open-source and premium repositories
- **Visual Course Grid**: Easy-to-navigate card layout showing all available courses
- **Repository Tags**: Clear identification of course source (Open Source vs Premium)

### 2. Metadata Editing (No Translation Required)
- **Course Index**: Rename course folder
- **Topic**: Select from predefined categories (Bitcoin, Business, Mining, etc.)
- **Subtopic**: Specify course subtopic
- **Type**: Theory or Practice
- **Level**: Beginner, Intermediate, Expert, or Wizard
- **Hours**: Estimated completion time

### 3. Translatable Content
- **Course Name**: Main title of the course
- **Goal**: Course learning goal
- **Objectives**: Individual learning objectives (add/remove dynamically)
- **Description**: Detailed course description (markdown supported)

### 4. Translation Features
- **Auto-Translation**: One-click translation to all available languages using OpenAI GPT-4
- **Language Tabs**: Easy switching between different language versions
- **Reference Language**: Always uses English (en.md) as the source for translations
- **Preserve Formatting**: Maintains markdown structure during translation

### 5. File Management
- **Smart Save**: Updates both course.yml and all language .md files
- **Course Renaming**: Safely rename course folders with automatic path updates
- **Batch Updates**: Edit multiple language versions simultaneously

## Usage

### Accessing the Editor
1. Navigate to the main application page
2. Click on the "Course Editor" feature card
3. Or directly visit `/course-editor` endpoint

### Editing a Course
1. **Select a Course**: Click on any course card from the grid
2. **Edit Metadata**: Update course settings that don't require translation
3. **Edit Content**: Switch between language tabs to edit translatable content
4. **Auto-Translate**: Click "Auto-Translate to All Languages" to generate translations
5. **Save Changes**: Click "Save All Changes" to update all files

### Translation Workflow
1. Edit the English content first (it serves as the reference)
2. Click the translation button to generate content for all other languages
3. Review and adjust translations as needed
4. Save all changes at once

## Technical Details

### File Structure
```
courses/
├── btc101/
│   ├── course.yml      # Course metadata
│   ├── en.md          # English content (reference)
│   ├── fr.md          # French translation
│   ├── es.md          # Spanish translation
│   └── ...            # Other language files
```

### Metadata Structure (course.yml)
- `topic`: Main subject category
- `subtopic`: Specific topic within category
- `type`: Learning type (theory/practice)
- `level`: Difficulty level
- `hours`: Estimated duration

### Content Structure (language.md)
```markdown
---
name: Course Name
goal: Learning goal
objectives:
  - Objective 1
  - Objective 2
---

Course description content here...

+++
```

## API Endpoints

### GET `/api/editor/courses`
List all available courses from both repositories

### GET `/api/editor/course/<repo_key>/<course_name>`
Load complete course data including all languages

### POST `/api/editor/translate`
Translate course content to specified languages

### POST `/api/editor/save`
Save all course changes to files

## Requirements

### Environment Variables
- `OPENAI_API_KEY`: Required for auto-translation feature
- `BEC_REPO`: Path to Bitcoin Educational Content repository
- `PREMIUM_REPO`: Path to Premium Content repository

### Dependencies
- Flask
- PyYAML
- OpenAI Python SDK
- Python 3.7+

## Error Handling
- Repository path validation
- Course existence checks
- Translation fallbacks for API failures
- File write permission verification

## Future Enhancements
- Bulk editing multiple courses
- Translation quality scoring
- Version control integration
- Collaborative editing features
- Translation memory for consistent terminology