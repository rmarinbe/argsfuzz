"""CLI entry point for argsfuzz."""

import sys
import argparse
from pathlib import Path

from .config import GenerationConfig, OutputFormat
from .fuzzer import FuzzGenerator


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate fuzzing test cases from CLI argument schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 100 valid test cases
  python -m argsfuzz config.json -n 100
  
  # Generate with 20% invalid cases
  python -m argsfuzz config.json -n 500 --invalid-ratio 0.2
  
  # Output to directory (one file per test)
  python -m argsfuzz config.json -n 100 -f directory -o corpus/
  
  # Reproducible generation with seed
  python -m argsfuzz config.json -n 100 --seed 42
        """
    )
    
    parser.add_argument('config', type=Path,
                        help='Path to fuzzing configuration JSON file')
    parser.add_argument('-s', '--schema', type=Path, default=None,
                        help='Path to schema file (default: argsfuzz-schema.json)')
    parser.add_argument('-n', '--num-generations', type=int, default=100,
                        help='Number of test cases to generate (default: 100)')
    parser.add_argument('--min-args', type=int, default=1,
                        help='Minimum number of arguments per generation (default: 1)')
    parser.add_argument('--max-args', type=int, default=None,
                        help='Maximum number of arguments per generation')
    parser.add_argument('--invalid-ratio', type=float, default=0.0,
                        help='Ratio of invalid test cases (0.0-1.0, default: 0.0)')
    parser.add_argument('-f', '--format', choices=['file', 'directory'],
                        default='file', help='Output format (default: file)')
    parser.add_argument('-o', '--output', type=Path, default=Path('corpus.txt'),
                        help='Output path (file or directory, default: corpus.txt)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--create-dummy-files', action='store_true',
                        help='Create actual dummy files/directories in /tmp')
    parser.add_argument('-g', '--generators', type=Path, default=None,
                        help='Path to Python file with custom generator functions')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress progress output')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.config.exists():
        print(f"ERROR: Configuration file not found: {args.config}")
        sys.exit(1)
    
    if args.schema is None:
        # Look for schema in package directory or current directory
        pkg_schema = Path(__file__).parent.parent / 'argsfuzz-schema.json'
        if pkg_schema.exists():
            args.schema = pkg_schema
        else:
            args.schema = Path('argsfuzz-schema.json')
    
    if not args.schema.exists():
        print(f"ERROR: Schema file not found: {args.schema}")
        sys.exit(1)
    
    if args.generators is not None and not args.generators.exists():
        print(f"ERROR: Generators file not found: {args.generators}")
        sys.exit(1)
    
    if not 0.0 <= args.invalid_ratio <= 1.0:
        print(f"ERROR: Invalid ratio must be between 0.0 and 1.0")
        sys.exit(1)
    
    verbose = not args.quiet and sys.stdout.isatty()
    
    gen_config = GenerationConfig(
        num_generations=args.num_generations,
        invalid_ratio=args.invalid_ratio,
        output_format=OutputFormat(args.format),
        output_path=args.output,
        seed=args.seed,
        min_args=args.min_args,
        max_args=args.max_args,
        create_dummy_files=args.create_dummy_files,
        verbose=verbose,
        generators_file=args.generators
    )
    
    try:
        generator = FuzzGenerator(args.config, args.schema, gen_config)
        count = generator.run()
        sys.exit(0 if count > 0 else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
