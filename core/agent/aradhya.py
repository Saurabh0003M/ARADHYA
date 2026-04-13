"""Compatibility wrapper for the modern Aradhya shell and CLI."""

from __future__ import annotations

import sys


def main() -> None:
    if "--cli" in sys.argv:
        from src.aradhya.main import main as cli_main

        cli_main()
        return

    try:
        from src.aradhya.floating_shell import main as shell_main

        shell_main()
    except Exception as error:  # pragma: no cover - defensive launcher fallback
        if "--shell" in sys.argv:
            raise
        print(f"Aradhya > Floating shell unavailable ({error}). Falling back to CLI.")
        from src.aradhya.main import main as cli_main

        cli_main()


if __name__ == "__main__":
    main()
