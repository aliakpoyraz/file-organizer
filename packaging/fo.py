"""Single-binary entry point.

Running the binary with no arguments opens the interactive menu; with
arguments it behaves like the full ``file-organizer`` CLI (organize, watch,
undo, ...). This lets one frozen executable cover every use case.
"""

import sys


def main() -> None:
    if len(sys.argv) == 1:
        from file_organizer.interactive import main as interactive_main
        interactive_main()
    else:
        from file_organizer.cli import main as cli_main
        cli_main()


if __name__ == "__main__":
    main()
