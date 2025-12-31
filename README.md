# argsfuzz

A schema-driven CLI argument fuzzing generator for testing command-line tools.

Generate valid and invalid command-line argument combinations from a declarative JSON schema. Useful for fuzzing, integration testing, and exploring CLI tool behavior.

## Features

- **Schema-driven**: Define arguments, types, constraints, and rules in JSON
- **Constraint-aware**: Handles dependencies, conflicts, mutual exclusion, and required arguments
- **Multiple value types**: flags, integers, floats, strings, enums, lists, files, directories
- **Custom generators**: Extend with Python functions for complex value generation (IPs, UUIDs, templates, etc.)
- **Subcommand support**: Model complex CLIs like `git`, `docker`, etc.
- **Positional arguments**: Handle ordered non-flag arguments
- **Invalid case generation**: Mutate valid combinations to test error handling
- **Reproducible**: Seed-based random generation for deterministic output
- **Flexible output**: Single file (one line per test) or directory (one file per test)
- **AFL-compatible**: Output works directly as AFL/libFuzzer corpus

## Installation

```bash
# Clone the repository
git clone https://github.com/rmarinbe/argsfuzz.git
cd argsfuzz

# Install all dependencies
pip install -r requirements.txt

# Or install individually:
pip install jsonschema        # Required: schema validation
pip install rstr              # Optional: regex pattern generation
```

## Quick Start

### As a Command-Line Tool

```bash
# Generate 100 test cases for curl
python argsfuzz.py examples/curl.json -n 100 -o corpus.txt

# Generate with 20% invalid cases
python argsfuzz.py examples/git.json -n 500 --invalid-ratio 0.2

# Output to directory (one file per test case, AFL-style)
python argsfuzz.py examples/tar.json -n 1000 -f directory -o corpus/

# Reproducible generation
python argsfuzz.py examples/curl.json -n 100 --seed 42
```

### As a Python Library

```python
from argsfuzz import FuzzGenerator, GenerationConfig, OutputFormat
from pathlib import Path

config = GenerationConfig(
    num_generations=1000,
    invalid_ratio=0.2,
    output_path=Path('corpus.txt'),
    seed=42,
    generators_file=Path('my_generators.py')  # Optional: custom generators
)

fuzzer = FuzzGenerator(
    config_path=Path('my_tool.json'),
    schema_path=Path('argsfuzz-schema.json'),
    gen_config=config
)
count = fuzzer.run()
print(f"Generated {count} test cases")
```

## Schema Format

Configuration files define the CLI structure:

```json
{
  "metadata": {
    "version": "1.0",
    "tool_name": "mytool",
    "description": "Fuzzing config for mytool"
  },
  "generation": {
    "max_args": 10,
    "equals_form_probability": 0.3
  },
  "arguments": [
    {
      "name": "verbose",
      "flags": ["-v", "--verbose"],
      "description": "Enable verbose output",
      "probability": 0.5,
      "value": { "kind": "flag" }
    },
    {
      "name": "count",
      "flags": ["-n", "--count"],
      "description": "Number of items",
      "value": { "kind": "integer", "min": 1, "max": 100 }
    }
  ]
}
```

### Value Types

| Kind | Description | Required Properties |
|------|-------------|---------------------|
| `flag` | Boolean flag, no value | - |
| `integer` | Integer number | `min`, `max` |
| `integer_optional` | Optional integer | `min`, `max` |
| `float` | Floating-point number | `min`, `max` |
| `string` | Text value | `pattern` (optional regex) |
| `enum` | One of predefined values | `values` |
| `list` | Multiple values | `values`, `separator`, `min_count`, `max_count` |
| `file` | File path | `path` (optional base dir), `pattern` (optional regex) |
| `directory` | Directory path | `path` (optional base dir), `pattern` (optional regex) |
| `custom` | Custom generator function | `generator`, `params` |

### Value Type Options

#### Numeric Bounds: `min` and `max`

For `integer`, `integer_optional`, and `float` types, specify value ranges:

```json
{
  "name": "threads",
  "flags": ["-t", "--threads"],
  "value": {
    "kind": "integer",
    "min": 1,
    "max": 64
  }
}
```

Generates values between 1 and 64 inclusive.

#### Enum Values: `values`

For `enum` and `list` types, provide predefined choices:

```json
{
  "name": "format",
  "flags": ["--output"],
  "value": {
    "kind": "enum",
    "values": ["json", "xml", "csv", "plain"]
  }
}
```

With `enum`, exactly one value is picked. With `list` type, multiple values can be selected.

#### List Configuration: `min_count` and `max_count`

Controls how many items appear in list output:

```json
{
  "name": "include_dirs",
  "flags": ["-I"],
  "value": {
    "kind": "list",
    "values": ["/usr/include", "/usr/local/include", "/opt/include"],
    "min_count": 1,
    "max_count": 2,
    "separator": ":"
  }
}
```

Generated outputs:
- `/usr/include` (1 item)
- `/usr/include:/usr/local/include` (2 items)
- `/opt/include` (1 item)

**Note:** If `max_count` exceeds available `values`, it's clamped to the number of values.

#### Separator: Joining List Items

The `separator` option defines how list items are joined (default is comma):

```json
{
  "name": "ld_path",
  "flags": ["--ld-library-path"],
  "value": {
    "kind": "list",
    "values": ["/lib", "/usr/lib", "/opt/lib"],
    "separator": ":",
    "min_count": 1,
    "max_count": 3
  }
}
```

Output example: `/lib:/usr/lib:/opt/lib` (colon-separated)

#### Formatting: `format`

Two formats available:

- **`plain`** (default): Join items with separator
  - `"a,b,c"`

- **`csv_range`**: Express numeric sequences as ranges
  - `"1,2,3,4,5"` → `"1-5"`
  - `"1,2,3,5,6,7"` → `"1-3,5-7"`

```json
{
  "name": "ports",
  "flags": ["--ports"],
  "value": {
    "kind": "list",
    "min": 1000,
    "max": 2000,
    "min_count": 3,
    "max_count": 5,
    "format": "csv_range"
  }
}
```

Output examples:
- `1200-1205` (5 consecutive ports)
- `1001,1500-1502,1999` (mixed format)

#### File/Directory Paths: `path`

The `path` option controls how file/directory values are generated:

- **If path exists** (directory): Lists items in that directory and returns one randomly
- **If path missing**: Generates a filename matching `pattern` (if specified) in that base path

```json
{
  "name": "input_file",
  "flags": ["--in"],
  "value": {
    "kind": "file",
    "path": "/var/data/",
    "pattern": "[a-z0-9_]+\\.dat"
  }
}
```

Output behaviors:
- `/var/data/` has files → Returns one (e.g., `/var/data/sensor_001.dat`)
- `/var/data/` missing → Generates (e.g., `/var/data/abc123xyz.dat`)

### Argument-Level Properties

Beyond value specifications, arguments support additional properties that control selection and constraints:

#### Probability: Inclusion Likelihood

The `probability` option (0.0-1.0) controls how often an argument is included in generated commands:

```json
{
  "name": "verbose",
  "flags": ["-v", "--verbose"],
  "probability": 0.3,
  "value": {
    "kind": "flag"
  }
}
```

With `probability: 0.3`, the flag appears in ~30% of generated commands. Default is 0.5 (50%).

#### Required: Always Include

Force an argument to appear in every generated command:

```json
{
  "name": "input_file",
  "flags": ["-i", "--input"],
  "required": true,
  "value": {
    "kind": "file"
  }
}
```

#### Group: Logical Argument Sets

Group related arguments for use in mutual exclusion and other rules:

```json
{
  "name": "json_output",
  "flags": ["--json"],
  "group": "output_format",
  "value": { "kind": "flag" }
},
{
  "name": "xml_output",
  "flags": ["--xml"],
  "group": "output_format",
  "value": { "kind": "flag" }
}
```

Then use a rule to enforce mutual exclusion:

```json
{
  "rules": [
    {
      "type": "mutually_exclusive",
      "arguments": ["output_format"],
      "description": "Only one output format allowed"
    }
  ]
}
```

#### Dependency: Requires Other Arguments

An argument can require another argument or group to be present:

```json
{
  "name": "output_compression",
  "flags": ["--compression"],
  "depends_on": ["output_file"],
  "value": {
    "kind": "enum",
    "values": ["gzip", "bzip2", "none"]
  }
}
```

The `output_file` argument (or group) must be present for `output_compression` to appear.

#### Repeat Flag: Multiple Occurrences

Allow an argument to appear multiple times:

```json
{
  "name": "include_path",
  "flags": ["-I"],
  "repeat_flag": {
    "min_occurs": 1,
    "max_occurs": 3
  },
  "value": {
    "kind": "directory",
    "path": "/usr/include"
  }
}
```

With these settings, `-I` can appear 1-3 times per command:
```
tool -I /usr/include -I /opt/include -I /local/include
```

### Regex Pattern Support

The `string`, `file`, and `directory` kinds support regex patterns for value generation and filtering. This uses **reverse regex** (generating strings that match a pattern) via the `rstr` library.

#### String Patterns

Generate strings matching a regex pattern:

```json
{
  "name": "session_id",
  "flags": ["--session"],
  "value": {
    "kind": "string",
    "pattern": "[A-Z]{3}-[0-9]{4}-[a-z]{2}"
  }
}
```

Output examples: `XKL-4829-qm`, `ABC-1234-xy`, `QRS-9012-ab`

#### File Patterns

For files, the pattern serves two purposes:

1. **Filtering**: If `path` points to an existing directory, files are filtered by the pattern
2. **Generation**: If no matching files found, generates filenames matching the pattern

```json
{
  "name": "config",
  "flags": ["--config"],
  "value": {
    "kind": "file",
    "path": "/etc/myapp/",
    "pattern": "[a-zA-Z0-9_-]+\\.json"
  }
}
```

Behavior:
- If `/etc/myapp/` exists: Returns a random `.json` file from that directory
- If directory missing or empty: Generates a filename like `config_a3Xk9.json`

#### Directory Patterns

Same behavior as files - filter existing directories or generate matching names:

```json
{
  "name": "output_dir",
  "flags": ["-o"],
  "value": {
    "kind": "directory",
    "path": "/var/log/",
    "pattern": "app_[0-9]{4}"
  }
}
```

Output examples: `app_2847`, `app_0193`, `app_7461`

#### Common Regex Patterns

| Pattern | Description | Examples |
|---------|-------------|----------|
| `[A-Za-z]+` | Letters only | `Hello`, `test` |
| `[0-9]{4}` | Exactly 4 digits | `1234`, `0001` |
| `[a-z]{2,5}` | 2-5 lowercase letters | `ab`, `hello` |
| `\w+\.txt` | Word chars + .txt | `file.txt`, `doc_1.txt` |
| `v[0-9]+\.[0-9]+` | Version string | `v1.0`, `v12.34` |
| `[A-Z]{2}-[0-9]{3}` | Code format | `AB-123`, `XY-999` |

> **Note**: The `rstr` package is required for reverse regex generation. Without it, the tool falls back to simplified string generation.

### Custom Generators

For complex value generation beyond built-in types, create custom generators. A generator is a Python function that receives a seeded random number generator (for reproducibility) and a parameters dictionary from the JSON config.

#### Basic Structure

```python
# my_generators.py
import random
from typing import Any, Dict

@register_generator("generator_name")
def my_generator(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate custom values.
    
    Args:
        rng: Random instance - ALWAYS use this instead of the random module
             to ensure reproducible generation with --seed
        params: Parameters dictionary from the JSON config's "params" field
    
    Returns:
        Generated string value for the argument
    """
    # Access params with defaults
    option = params.get('key', 'default_value')
    return f"result_{option}"
```

#### Using Custom Generators

1. Create your generator file (e.g., `my_generators.py`)
2. Reference it in your JSON config:

```json
{
  "name": "my_arg",
  "flags": ["--my-arg"],
  "value": {
    "kind": "custom",
    "generator": "generator_name",
    "params": {
      "key": "value",
      "count": 3
    }
  }
}
```

3. Run with the `-g` flag:

```bash
python argsfuzz.py config.json -g my_generators.py -n 100 --seed 42
```

#### Example: Weighted Key-Value Pairs

Generate strings like `AS:30,BR:15,FZ:5` for algorithm weights, priority settings, or resource allocations:

```python
@register_generator("weighted_pairs")
def gen_weighted_pairs(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate key:value pairs with random weights."""
    keys = params.get('keys', ['A', 'B', 'C'])
    weight_min = params.get('weight_min', 1)
    weight_max = params.get('weight_max', 100)
    min_count = params.get('min_count', 1)
    max_count = params.get('max_count', len(keys))
    separator = params.get('separator', ',')
    
    count = rng.randint(min_count, min(max_count, len(keys)))
    selected = rng.sample(keys, count)
    
    pairs = [f"{k}:{rng.randint(weight_min, weight_max)}" for k in selected]
    return separator.join(pairs)
```

JSON usage:
```json
"value": {
  "kind": "custom",
  "generator": "weighted_pairs",
  "params": {
    "keys": ["CPU", "MEM", "IO", "NET"],
    "weight_min": 0,
    "weight_max": 100,
    "min_count": 1,
    "max_count": 4
  }
}
```

Output examples: `CPU:45,MEM:80`, `IO:12`, `NET:95,CPU:30,MEM:67`

#### Example: Network Addresses

Generate IPv4 addresses with configurable ranges:

```python
@register_generator("ipv4_address")
def gen_ipv4(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate random IPv4 addresses."""
    private_only = params.get('private_only', False)
    
    if private_only:
        # Private ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x
        range_type = rng.randint(0, 2)
        if range_type == 0:
            return f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
        elif range_type == 1:
            return f"172.{rng.randint(16,31)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
        else:
            return f"192.168.{rng.randint(0,255)}.{rng.randint(1,254)}"
    else:
        return f"{rng.randint(1,223)}.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"
```

#### Example: UUID Generation

Generate RFC 4122 compliant UUIDs:

```python
@register_generator("uuid")
def gen_uuid(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate UUID v4 strings."""
    uppercase = params.get('uppercase', False)
    compact = params.get('compact', False)  # No dashes
    
    hex_chars = '0123456789ABCDEF' if uppercase else '0123456789abcdef'
    
    parts = [
        ''.join(rng.choices(hex_chars, k=8)),
        ''.join(rng.choices(hex_chars, k=4)),
        '4' + ''.join(rng.choices(hex_chars, k=3)),  # Version 4
        rng.choice('89ab') + ''.join(rng.choices(hex_chars, k=3)),
        ''.join(rng.choices(hex_chars, k=12))
    ]
    
    return ''.join(parts) if compact else '-'.join(parts)
```

#### Example: Date/Time Formats

Generate dates in various formats:

```python
@register_generator("datetime")
def gen_datetime(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate date/time strings."""
    fmt = params.get('format', 'iso')  # iso, date, epoch, custom
    year_range = params.get('year_range', [2020, 2025])
    
    year = rng.randint(year_range[0], year_range[1])
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    
    if fmt == 'iso':
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
    elif fmt == 'date':
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif fmt == 'epoch':
        from datetime import datetime
        dt = datetime(year, month, day, hour, minute, second)
        return str(int(dt.timestamp()))
    elif fmt == 'custom':
        template = params.get('template', '%Y-%m-%d')
        return template.replace('%Y', f'{year:04d}').replace('%m', f'{month:02d}').replace('%d', f'{day:02d}')
    return f"{year}-{month:02d}-{day:02d}"
```

#### Example: Template-Based Generation

Generate values from templates with placeholders:

```python
@register_generator("template")
def gen_template(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate values from a template with random substitutions."""
    template = params.get('template', '{prefix}_{id}')
    substitutions = params.get('substitutions', {})
    
    result = template
    for key, spec in substitutions.items():
        if isinstance(spec, list):
            value = rng.choice(spec)
        elif isinstance(spec, dict):
            value = rng.randint(spec.get('min', 0), spec.get('max', 100))
        else:
            value = spec
        result = result.replace(f'{{{key}}}', str(value))
    
    return result
```

JSON usage:
```json
"value": {
  "kind": "custom",
  "generator": "template",
  "params": {
    "template": "{env}_{service}_{id}.log",
    "substitutions": {
      "env": ["prod", "staging", "dev"],
      "service": ["api", "web", "worker"],
      "id": {"min": 1000, "max": 9999}
    }
  }
}
```

Output examples: `prod_api_4521.log`, `dev_worker_7834.log`

#### Example: Hex Values

Generate hexadecimal numbers with formatting:

```python
@register_generator("hex_value")
def gen_hex(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate formatted hexadecimal values."""
    min_val = params.get('min', 0)
    max_val = params.get('max', 255)
    prefix = params.get('prefix', '0x')
    width = params.get('width', 2)  # Zero-pad width
    uppercase = params.get('uppercase', False)
    
    value = rng.randint(min_val, max_val)
    hex_str = f"{value:0{width}x}"
    
    if uppercase:
        hex_str = hex_str.upper()
    
    return f"{prefix}{hex_str}"
```

#### Tips for Writing Generators

1. **Always use `rng`**: Never import `random` and use it directly. The `rng` parameter ensures reproducibility with `--seed`.

2. **Validate inputs**: Use `.get()` with sensible defaults to handle missing params gracefully.

3. **Handle edge cases**: Ensure `min_count` never exceeds available options when sampling.

4. **Keep it simple**: Each generator should do one thing well. Combine multiple generators for complex scenarios.

5. **Document params**: Add docstrings explaining what parameters your generator accepts.

### Constraints

**Dependencies** - Argument requires another to be present:
```json
{
  "name": "output_format",
  "depends_on": ["output_file"],
  ...
}
```

**Groups** - Logical grouping for mutual exclusion (used with `mutually_exclusive` rules):
```json
{
  "name": "json_output",
  "group": "output_format",
  ...
},
{
  "name": "xml_output",
  "group": "output_format",
  ...
}
```

Then define a rule to enforce mutual exclusion:
```json
{
  "rules": [
    {
      "type": "mutually_exclusive",
      "arguments": ["output_format"],
      "description": "Only one output format allowed"
    }
  ]
}
```

### Rules

Global validation rules for complex constraints:

```json
{
  "rules": [
    {
      "type": "mutually_exclusive",
      "arguments": ["verbose", "quiet"],
      "description": "Cannot be both verbose and quiet"
    },
    {
      "type": "one_of_required",
      "arguments": ["input_file", "stdin"],
      "description": "Must specify input source"
    }
  ]
}
```

Rule types:
- `mutually_exclusive`: Only one argument from the list can be present
- `one_of_required`: At least one argument from the list must be present
- `all_or_none`: Either all arguments present or none
- `requires`: First argument requires all others

### Subcommands

For tools like `git`, `docker`:

```json
{
  "subcommands": [
    {
      "name": "commit",
      "probability": 0.5,
      "arguments": [
        {
          "name": "message",
          "flags": ["-m", "--message"],
          "required": true,
          "value": { "kind": "string" }
        }
      ]
    }
  ]
}
```

### Positional Arguments

```json
{
  "positional": [
    {
      "name": "source",
      "position": 0,
      "required": true,
      "value": { "kind": "file" }
    },
    {
      "name": "destination",
      "position": 1,
      "required": false,
      "value": { "kind": "directory" }
    }
  ]
}
```

## CLI Options

```
usage: argsfuzz.py [-h] [-s SCHEMA] [-n NUM] [--min-args MIN] [--max-args MAX]
                   [--invalid-ratio RATIO] [-f {file,directory}] [-o OUTPUT]
                   [--seed SEED] [--create-dummy-files] [-g GENERATORS] [-q] config

Options:
  config                  Path to fuzzing configuration JSON
  -s, --schema           Path to schema file (default: argsfuzz-schema.json)
  -n, --num-generations  Number of test cases (default: 100)
  --min-args             Minimum arguments per test (default: 1)
  --max-args             Maximum arguments per test
  --invalid-ratio        Ratio of invalid cases 0.0-1.0 (default: 0.0)
  -f, --format           Output format: file or directory (default: file)
  -o, --output           Output path (default: corpus.txt)
  --seed                 Random seed for reproducibility
  --create-dummy-files   Create actual files in /tmp for file/dir arguments
  -g, --generators       Path to Python file with custom generators
  -q, --quiet            Suppress progress output
```

## Examples

See the `examples/` directory for complete schemas:

- **[git.json](examples/git.json)** - Demonstrates subcommands, positional args, mutual exclusion
- **[tar.json](examples/tar.json)** - Shows file operations, required args, groups
- **[curl.json](examples/curl.json)** - Covers HTTP methods, headers, authentication

### Example Output

```bash
$ python argsfuzz.py examples/curl.json -n 5 --seed 42
```

```
-X POST --max-time 45 https://example.com/api
--header "Content-Type: application/json" -o output.txt http://test.local
-v --compressed --location http://api.example.org
-u user:pass -d '{"key":"value"}' https://secure.example.com
--connect-timeout 30 -I http://check.example.net
```

## Pipeline Architecture

```
schema.json → SchemaValidator → ConstraintSolver → Generator → Mutator → CorpusWriter
     │              │                  │               │           │           │
     │              │                  │               │           │           └─ Output test cases
     │              │                  │               │           └─ Introduce invalid mutations
     │              │                  │               └─ Create valid combinations
     │              │                  └─ Build dependency/conflict graphs
     │              └─ Validate config against JSON schema
     └─ Define CLI structure
```

## Integration with Fuzzers

### AFL/AFL++

```bash
# Generate corpus
python argsfuzz.py my_tool.json -n 10000 -f directory -o afl_corpus/

# Run AFL
afl-fuzz -i afl_corpus -o findings -- ./my_tool @@
```

### LibFuzzer

```bash
# Generate seed corpus
python argsfuzz.py my_tool.json -n 1000 -f directory -o corpus/

# Run with libFuzzer
./my_tool_fuzzer corpus/
```

### Custom Harness

```python
from argsfuzz import FuzzGenerator, GenerationConfig
import subprocess

config = GenerationConfig(num_generations=1, seed=iteration)
fuzzer = FuzzGenerator('tool.json', 'argsfuzz-schema.json', config)

# Read generated line and execute
with open('corpus.txt') as f:
    args = f.read().strip().split()
    result = subprocess.run(['./my_tool'] + args, capture_output=True)
```

## Design Notes

### Mutual Exclusion with Groups

Use `group` property to logically group related arguments, then apply a `mutually_exclusive` rule to the group. This is cleaner and more maintainable than per-argument constraints:

```json
{
  "arguments": [
    { "name": "verbose", "group": "verbosity", ... },
    { "name": "quiet", "group": "verbosity", ... }
  ],
  "rules": [
    { "type": "mutually_exclusive", "arguments": ["verbosity"] }
  ]
}
```

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Author

Richard Marin B.
