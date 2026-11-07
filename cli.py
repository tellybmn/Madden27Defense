#!/usr/bin/env python3
"""Root shim so `python cli.py ...` works; real implementation is src/cli.py."""
import sys

from src.cli import main

if __name__ == "__main__":
    sys.exit(main())
