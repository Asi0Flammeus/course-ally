import sys
from pathlib import Path
from course_components.cli import cli
from typing import Optional, List

def interactive_menu() -> None:
    """
    Interactive menu to select and run available CLI features.
    """
    commands = list(cli.commands.keys())
    
    print("Available features:")
    for idx, name in enumerate(commands, start=1):
        cmd = cli.commands[name]
        help_text = cmd.help or ''
        print(f"{idx}. {name} - {help_text}")
    
    choice = input("Enter the number of the feature: ")
    try:
        sel = int(choice)
    except ValueError:
        print("Invalid choice.")
        sys.exit(1)
    
    if sel < 1 or sel > len(commands):
        print("Invalid choice.")
        sys.exit(1)
    
    cmd_name = commands[sel - 1]
    
    if cmd_name == 'create-lecture':
        # Collect command arguments
        video_id = input("Enter YouTube video ID: ")
        sections = input("Number of sections [3]: ") or '3'
        output = input("Output file path (leave blank for stdout): ")
        
        # Build command arguments list
        args = [cmd_name, video_id]  # Start with command and video ID
        
        if sections != '3':  # Only add if different from default
            args.extend(['-s', sections])
        if output.strip():
            args.extend(['-o', output.strip()])
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif cmd_name == 'extract-playlist-transcripts':
        # Collect command arguments
        playlist_url = input("Enter YouTube playlist URL: ")
        output_dir = input("Output directory [transcripts]: ") or 'transcripts'
        format_choice = input("Output format (txt/json) [txt]: ") or 'txt'
        
        # Build command arguments list
        args = [cmd_name, playlist_url]
        
        if output_dir != 'transcripts':
            args.extend(['-d', output_dir])
        if format_choice != 'txt':
            args.extend(['-f', format_choice])
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        # Handle other commands if needed
        cli.main(args=[cmd_name], standalone_mode=False)

def main() -> None:
    """
    Entry point for the Course Components CLI.
    If no arguments are provided, launch interactive menu.
    """
    if len(sys.argv) == 1:
        interactive_menu()
    else:
        cli()

if __name__ == '__main__':  # pragma: no cover
    main()

