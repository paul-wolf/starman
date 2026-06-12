#!/usr/bin/env python3
"""Check for forbidden imports in Python files."""
import sys
import re

FORBIDDEN_PATTERNS = [
    # Add patterns as needed, e.g.:
    # (r'from\s+some_module', 'Do not import from some_module'),
]

def check_file(filename):
    with open(filename, "r") as f:
        content = f.read()

    errors = []
    for pattern, message in FORBIDDEN_PATTERNS:
        if re.search(pattern, content):
            errors.append(f"{filename}: {message}")

    return errors

def main():
    files = sys.argv[1:]
    all_errors = []

    for filename in files:
        all_errors.extend(check_file(filename))

    if all_errors:
        for error in all_errors:
            print(error)
        sys.exit(1)

    sys.exit(0)

if __name__ == "__main__":
    main()
