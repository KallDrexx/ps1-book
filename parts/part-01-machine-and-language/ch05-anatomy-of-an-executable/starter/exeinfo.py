#!/usr/bin/env python3
"""exeinfo.py -- inspect a PSX-EXE (chapter 5, part a).

usage: python3 exeinfo.py FILE

Print the header fields and the first 16 instructions, or one line
"INVALID: <category>" and exit 1. The exact output format is in the chapter.
"""
import sys


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    data = open(argv[1], "rb").read()
    # YOUR CODE HERE: parse the header, validate it, disassemble the payload.
    print(f"INVALID: not implemented ({len(data)} bytes read)")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
