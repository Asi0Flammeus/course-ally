import sys
from course_components.cli import cli

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
    # Collect arguments for the selected command
    args = [cmd_name]
    if cmd_name == 'create-lecture':
        video_id = input("Enter YouTube video ID: ")
        args.append(video_id)
        sections = input("Number of sections [3]: ") or '3'
        args += ['--sections', sections]
        output = input("Output file path (leave blank for stdout): ")
        if output.strip():
            args += ['--output', output.strip()]
    # Execute the CLI command
    try:
        cli.main(args=args, standalone_mode=False)
    except SystemExit:
        pass

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

