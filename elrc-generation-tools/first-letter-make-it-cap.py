#!/usr/bin/env python3
"""
Script to capitalize or lowercase the first letter of each line in LRC files.
Ignores metadata lines that start with brackets [].
Handles lines that start with non-letter characters like apostrophes.
"""

import argparse
import re
import sys
from pathlib import Path


def find_first_letter_index(line):
    """
    Find the index of the first letter in a line.
    Returns -1 if no letter is found.
    """
    for i, char in enumerate(line):
        if char.isalpha():
            return i
    return -1


def capitalize_first_letter(line):
    """
    Capitalize the first letter found in the line.
    Returns the modified line or original if no letter found.
    """
    first_letter_idx = find_first_letter_index(line)
    if first_letter_idx == -1:
        return line

    line_list = list(line)
    line_list[first_letter_idx] = line_list[first_letter_idx].upper()
    return ''.join(line_list)


def lowercase_first_letter(line):
    """
    Lowercase the first letter found in the line.
    Returns the modified line or original if no letter found.
    """
    first_letter_idx = find_first_letter_index(line)
    if first_letter_idx == -1:
        return line

    line_list = list(line)
    line_list[first_letter_idx] = line_list[first_letter_idx].lower()
    return ''.join(line_list)


def is_metadata_line(line):
    """
    Check if a line is an LRC metadata line (starts with []).
    """
    stripped = line.strip()
    return stripped.startswith('[') and ']' in stripped


def process_lrc_file(file_path, lowercase_mode=False):
    """
    Process an LRC file to capitalize or lowercase the first letter of each line.

    Args:
        file_path (str): Path to the LRC file
        lowercase_mode (bool): If True, lowercase first letter; if False, capitalize
    """
    try:
        # Read the file
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Process each line
        processed_lines = []
        for line in lines:
            # Keep metadata lines unchanged
            if is_metadata_line(line):
                processed_lines.append(line)
            else:
                # Remove trailing newline for processing, add it back later
                line_content = line.rstrip('\n\r')

                if lowercase_mode:
                    processed_line = lowercase_first_letter(line_content)
                else:
                    processed_line = capitalize_first_letter(line_content)

                # Add back the newline if it was there originally
                if line.endswith('\n'):
                    processed_line += '\n'
                elif line.endswith('\r\n'):
                    processed_line += '\r\n'

                processed_lines.append(processed_line)

        # Write back to the same file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(processed_lines)

        action = "lowercased" if lowercase_mode else "capitalized"
        print(f"Successfully {action} first letters in: {file_path}")

    except FileNotFoundError:
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    except PermissionError:
        print(f"Error: Permission denied: {file_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error processing file {file_path}: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main function to handle command line arguments and process the file."""
    parser = argparse.ArgumentParser(
        description="Capitalize or lowercase the first letter of each line in LRC files. "
                   "Ignores metadata lines that start with brackets []."
    )

    parser.add_argument(
        'file',
        help='Path to the LRC file to process'
    )

    parser.add_argument(
        '--lower',
        action='store_true',
        help='Lowercase the first letter instead of capitalizing it'
    )

    args = parser.parse_args()

    # Validate file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File does not exist: {args.file}", file=sys.stderr)
        sys.exit(1)

    # Process the file
    process_lrc_file(args.file, lowercase_mode=args.lower)


if __name__ == "__main__":
    main()