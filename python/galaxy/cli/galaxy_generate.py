#!/usr/bin/env python3
"""Generate the galaxy map SVG from galaxy.json.

--interactive adds pan and zoom.
"""

import argparse
import json
import sys

from galaxy.renderer import GalaxyMapGenerator


def main():
    parser = argparse.ArgumentParser(description='Generate galaxy map SVG')
    parser.add_argument('--input', '-i', required=True, help='Input JSON file')
    parser.add_argument('--output', '-o', required=True, help='Output SVG file')
    parser.add_argument('--width', '-w', type=int, default=5600, help='Image width (default: 5600)')
    parser.add_argument('--height', type=int, default=5600, help='Image height (default: 5600)')
    parser.add_argument('--interactive', action='store_true',
                        help='Embed viewBox zoom/pan controls (wheel zoom, drag pan)')

    args = parser.parse_args()

    try:
        with open(args.input, 'r') as f:
            data = json.load(f)

        generator = GalaxyMapGenerator(args.width, args.height, interactive=args.interactive)
        generator.generate(data, args.output)

    except FileNotFoundError:
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
