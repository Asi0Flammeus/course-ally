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
    
    choice = input("Enter the number of the feature: ").strip()
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
        video_id = input("Enter YouTube video ID: ").strip()
        sections = input("Number of sections [3]: ").strip() or '3'
        output = input("Output file path (leave blank for stdout): ").strip()
        
        # Build command arguments list
        args = [cmd_name, video_id]  # Start with command and video ID
        
        if sections != '3':  # Only add if different from default
            args.extend(['-s', sections])
        if output:
            args.extend(['-o', output])
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif cmd_name == 'extract-playlist-transcripts':
        # Collect command arguments
        youtube_url = input("Enter YouTube URL (video or playlist): ").strip()
        subfolder = input("Optional subfolder name (leave blank for none): ").strip()
        format_choice = input("Output format (txt/json) [txt]: ").strip() or 'txt'
        max_workers = input("Maximum parallel workers [4]: ").strip() or '4'
        
        # Build command arguments list
        args = [cmd_name, youtube_url]
        
        if subfolder:
            args.extend(['-s', subfolder])
        if format_choice != 'txt':
            args.extend(['-f', format_choice])
        if max_workers != '4':
            args.extend(['-w', max_workers])
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif cmd_name == 'extract-playlist-links':
        # Collect command arguments
        playlist_url = input("Enter YouTube playlist URL: ").strip()
        subfolder = input("Optional subfolder name (leave blank for none): ").strip()
        live_format = input("Use live embed format? (y/N): ").strip().lower().startswith('y')
        
        # Build command arguments list
        args = [cmd_name, playlist_url]
        
        if subfolder:
            args.extend(['-s', subfolder])
        if live_format:
            args.append('-l')
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif cmd_name == 'create-chapters':
        # Collect command arguments
        print("Create chapters from transcript files")
        
        subfolder = input("Optional subfolder name in outputs/chapters/ (leave blank for auto): ").strip()
        max_workers = input("Maximum parallel workers [2]: ").strip() or '2'
        chapter_title = input("Custom chapter title (for single files, leave blank for auto): ").strip()
        
        # Build command arguments list
        args = [cmd_name]
        
        if subfolder:
            args.extend(['-s', subfolder])
        if max_workers != '2':
            args.extend(['-w', max_workers])
        if chapter_title:
            args.extend(['-t', chapter_title])
            
        # Execute the CLI command
        try:
            cli.main(args=args, standalone_mode=False)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    elif cmd_name == 'create-quiz':
        # Collect command arguments
        print("Create quiz questions from chapter files")
        
        subfolder = input("Optional subfolder name in outputs/quizz/ (leave blank for auto): ").strip()
        max_workers = input("Maximum parallel workers [2]: ").strip() or '2'
        
        # Build command arguments list
        args = [cmd_name]
        
        if subfolder:
            args.extend(['-s', subfolder])
        if max_workers != '2':
            args.extend(['-w', max_workers])
            
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

