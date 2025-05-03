# Course Components CLI

This project provides a command-line interface (CLI) to generate course components—starting with lectures—from YouTube videos using OpenAI's APIs.

## Requirements

1. Python 3.8 or higher
2. An OpenAI API key set in the environment: `export OPENAI_API_KEY=your_api_key`
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Ensure `pytube` is installed (included in `requirements.txt`).
4. (Optional) Install the yt-dlp tool if not already installed:
   ```bash
   pip install yt-dlp
   ```

## Usage

Generate a lecture in Markdown format from a YouTube video ID:

```bash
python main.py create-lecture <VIDEO_ID> [OPTIONS]
```

Alternatively, run without arguments to select features interactively:

- ```bash
python main.py
```

Options:
- `<VIDEO_ID>`: YouTube video identifier (e.g., `dQw4w9WgXcQ`).
- `--output, -o`: (Optional) Path to save the generated Markdown file. Defaults to printing to stdout.
- `--sections, -s`: Number of main sections in the lecture outline. Defaults to 3.

Example:
```bash
python main.py create-lecture dQw4w9WgXcQ -o lecture.md -s 4
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.


You can tip me via LN through this [link](https://getalby.com/p/asi0).

## License

This project is licensed under the MIT License. See `license.md` for details.


