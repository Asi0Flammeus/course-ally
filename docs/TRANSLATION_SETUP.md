# Course Editor Translation Setup

## Overview
The course editor now includes automatic translation functionality using Claude AI. When you modify course content in English, it automatically translates the changes to all other languages present in the course folder.

## Setup

### 1. API Key Configuration
Add your Anthropic API key to the `.env` file:

```bash
ANTHROPIC_API_KEY=your_api_key_here
```

To get an API key:
1. Go to https://console.anthropic.com/
2. Create an account or sign in
3. Navigate to API Keys section
4. Create a new API key
5. Copy and paste it into your `.env` file

### 2. Install Dependencies
The required package is already in `requirements.txt`:

```bash
pip install -r requirements.txt
```

## How It Works

### Automatic Translation on Save
When you save changes in the course editor:

1. **English as Source**: The system uses English (`en`) content as the source for translations
2. **Automatic Detection**: It detects which languages are present in the course folder
3. **Translation Process**: Claude AI translates the modified content to all target languages
4. **Preserves Structure**: The translation maintains:
   - Course metadata (name, goal, objectives)
   - Description content
   - Technical terminology accuracy

### Translation Fields
The following fields are automatically translated:
- **name**: Course title
- **goal**: Course learning goal
- **objectives**: List of learning objectives
- **description**: Course description text

### Manual Override
If you manually edit content in a non-English language file, those changes are preserved unless you modify the English version again.

## Testing

Run the test script to verify translation is working:

```bash
python test_translation.py
```

Expected output:
```
🧪 Course Translation Test
========================================
✅ Anthropic API configured

📝 Testing translation to: fr, es, de
Original content (English):
  Name: Bitcoin for Businesses
  Goal: Learn the payment and treasury basics to onboard...

✅ Translation successful!

🌍 French:
  Name: Bitcoin pour les entreprises
  Goal: Apprendre les bases des paiements et de la trésorerie...
  Objectives: 3 items

🌍 Spanish:
  Name: Bitcoin para empresas
  Goal: Aprender los conceptos básicos de pagos y tesorería...
  Objectives: 3 items

🌍 German:
  Name: Bitcoin für Unternehmen
  Goal: Lernen Sie die Grundlagen von Zahlungen und Treasury...
  Objectives: 3 items

✅ All tests passed!
```

## Troubleshooting

### API Key Not Working
- Verify the key is correctly set in `.env`
- Check that the `.env` file is in the project root
- Ensure the key has valid credits

### Translation Not Happening
- Check console/terminal for error messages
- Verify English content exists as source
- Ensure target language files exist in the course folder

### Fallback Behavior
If translation fails for any reason:
- The original content is preserved
- An error message is logged to console
- The save operation continues without blocking

## Supported Languages
The system supports translation to all languages that have existing `.md` files in the course folder, including:
- French (fr)
- Spanish (es) 
- German (de)
- Italian (it)
- Portuguese (pt)
- Russian (ru)
- Japanese (ja)
- Korean (ko)
- Chinese Simplified (zh-Hans)
- Chinese Traditional (zh-Hant)
- Arabic (ar)
- And many more...

## Cost Considerations
- Claude 3 Haiku model is used for efficiency
- Typical translation cost: ~$0.001 per course edit
- Only modified content is translated to minimize API calls

## Future Enhancements
Planned improvements:
- [ ] Caching to avoid re-translating unchanged content
- [ ] Batch translation for multiple courses
- [ ] Translation quality review interface
- [ ] Custom terminology glossaries
- [ ] Language-specific formatting rules