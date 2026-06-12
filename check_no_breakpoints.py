#!/usr/bin/env python3
"""Check for breakpoint() calls in Python files."""
import sys
import re

def check_file(filename):
    """Check a file for breakpoint() calls."""
    with open(filename, "r") as f:
        for line_num, line in enumerate(f, 1):
            if re.search(r"^\s*breakpoint\(\)", line):
                return f"{filename}:{line_num}: Found breakpoint() call"
    return None

def main():
    files = sys.argv[1:]
    errors = []

    for filename in files:
        error = check_file(filename)
        if error:
            errors.append(error)

    if errors:
        for error in errors:
            print(error)
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
