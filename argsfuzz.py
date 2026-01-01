#!/usr/bin/env python3
"""
CLI Argument Fuzzing Generator

Implements a complete pipeline for generating valid and invalid command-line
argument combinations from a fuzzing configuration schema.

Pipeline:
    schema.json → SchemaValidator → ConstraintSolver → Generator → Mutator → CorpusWriter
"""

import json
import random
import sys
import argparse
import os
import tempfile
import importlib.util
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import re

try:
    from jsonschema import validate, ValidationError
except ImportError:
    print("ERROR: jsonschema package required. Install with: pip install jsonschema")
    sys.exit(1)

try:
    import rstr
    RSTR_AVAILABLE = True
except ImportError:
    RSTR_AVAILABLE = False


# Type alias for custom generator functions
# Signature: (rng: random.Random, params: Dict[str, Any]) -> str
GeneratorFunc = Callable[[random.Random, Dict[str, Any]], str]


class GeneratorRegistry:
    """Registry for custom value generators.
    
    Generators are functions that take (rng, params) and return a string value.
    They enable complex, reproducible value generation beyond simple types.
    """
    
    _generators: Dict[str, GeneratorFunc] = {}
    
    @classmethod
    def register(cls, name: str, func: GeneratorFunc) -> None:
        """Register a generator function by name."""
        cls._generators[name] = func
    
    @classmethod
    def get(cls, name: str) -> Optional[GeneratorFunc]:
        """Get a generator function by name."""
        return cls._generators.get(name)
    
    @classmethod
    def list_generators(cls) -> List[str]:
        """List all registered generator names."""
        return list(cls._generators.keys())
    
    @classmethod
    def load_from_file(cls, filepath: Path) -> int:
        """Load custom generators from a Python file.
        
        The file should define functions decorated with @register_generator
        or call GeneratorRegistry.register() directly.
        
        Returns: Number of generators loaded.
        """
        if not filepath.exists():
            return 0
        
        spec = importlib.util.spec_from_file_location("custom_generators", filepath)
        if spec is None or spec.loader is None:
            return 0
        
        module = importlib.util.module_from_spec(spec)
        # Make registry available to the module
        module.GeneratorRegistry = cls
        module.register_generator = register_generator
        
        before = len(cls._generators)
        spec.loader.exec_module(module)
        return len(cls._generators) - before


def register_generator(name: str):
    """Decorator to register a generator function.
    
    Usage:
        @register_generator("my_generator")
        def my_generator(rng: random.Random, params: dict) -> str:
            return "generated_value"
    """
    def decorator(func: GeneratorFunc) -> GeneratorFunc:
        GeneratorRegistry.register(name, func)
        return func
    return decorator



class OutputFormat(Enum):
    """Output format options"""
    SINGLE_FILE = "file"
    DIRECTORY = "directory"


@dataclass
class GenerationConfig:
    """Configuration for the generation process"""
    num_generations: int = 100
    invalid_ratio: float = 0.0  # 0.0 = all valid, 1.0 = all invalid
    output_format: OutputFormat = OutputFormat.SINGLE_FILE
    output_path: Path = Path("corpus")
    seed: Optional[int] = None
    min_args: int = 1  # Minimum number of arguments to generate
    max_args: Optional[int] = None  # Maximum number of arguments (None = use config default)
    create_dummy_files: bool = False  # Create actual dummy files/directories in /tmp
    verbose: bool = False  # Print progress messages (default False for library usage, CLI sets to True)
    generators_file: Optional[Path] = None  # Path to Python file with custom generators


@dataclass
class Argument:
    """Represents a parsed argument"""
    name: str
    flags: List[str]
    description: str
    probability: float
    group: Optional[str]
    depends_on: List[str]
    required: bool
    repeat_flag: Optional[Dict[str, int]]
    value_spec: Dict[str, Any]
    # Custom generator support
    generator: Optional[str] = None  # Name of registered generator function
    params: Optional[Dict[str, Any]] = None  # Parameters for generator


@dataclass
class PositionalArg:
    """Represents a positional argument"""
    name: str
    position: int
    required: bool
    variadic: bool
    value_spec: Dict[str, Any]


@dataclass
class Rule:
    """Represents a validation rule"""
    rule_type: str
    arguments: List[str]
    description: Optional[str] = None


class SchemaValidator:
    """Validates fuzzing configuration against the schema"""
    
    def __init__(self, schema_path: Path):
        with open(schema_path, 'r') as f:
            self.schema = json.load(f)
    
    def validate(self, config_path: Path) -> Dict[str, Any]:
        """Validate configuration and return parsed data"""
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        try:
            validate(instance=config, schema=self.schema)
        except ValidationError as e:
            raise ValueError(f"Invalid configuration: {e.message}")
        
        return config


@dataclass
class Subcommand:
    """Represents a subcommand"""
    name: str
    description: str
    aliases: List[str]
    probability: float
    arguments: Dict[str, Argument]
    positional: List[PositionalArg]


class ConstraintSolver:
    """Solves constraints and determines valid argument combinations"""
    
    def __init__(self, config: Dict[str, Any], rng: random.Random):
        self.config = config
        self.rng = rng
        self.arguments = self._parse_arguments()
        self.positional = self._parse_positional()
        self.subcommands = self._parse_subcommands()
        self.rules = self._parse_rules()
        self.groups = self._build_groups()
    
    def _parse_arguments(self) -> Dict[str, Argument]:
        """Parse arguments from config"""
        args = {}
        for arg_spec in self.config.get('arguments', []):
            arg = Argument(
                name=arg_spec['name'],
                flags=arg_spec['flags'],
                description=arg_spec.get('description', ''),
                probability=arg_spec.get('probability', 0.5),
                group=arg_spec.get('group'),
                depends_on=arg_spec.get('depends_on', []),
                required=arg_spec.get('required', False),
                repeat_flag=arg_spec.get('repeat_flag'),
                value_spec=arg_spec['value'],
                generator=arg_spec.get('generator'),
                params=arg_spec.get('params')
            )
            args[arg.name] = arg
        return args
    
    def _parse_positional(self) -> List[PositionalArg]:
        """Parse positional arguments"""
        pos_args = []
        for pos_spec in self.config.get('positional', []):
            pos_arg = PositionalArg(
                name=pos_spec['name'],
                position=pos_spec['position'],
                required=pos_spec.get('required', False),
                variadic=pos_spec.get('variadic', False),
                value_spec=pos_spec['value']
            )
            pos_args.append(pos_arg)
        return sorted(pos_args, key=lambda x: x.position)
    
    def _parse_subcommands(self) -> Dict[str, Subcommand]:
        """Parse subcommands"""
        subcommands = {}
        for sub_spec in self.config.get('subcommands', []):
            # Parse subcommand arguments
            sub_args = {}
            for arg_spec in sub_spec.get('arguments', []):
                arg = Argument(
                    name=arg_spec['name'],
                    flags=arg_spec['flags'],
                    description=arg_spec.get('description', ''),
                    probability=arg_spec.get('probability', 0.5),
                    group=arg_spec.get('group'),
                    depends_on=arg_spec.get('depends_on', []),
                    required=arg_spec.get('required', False),
                    repeat_flag=arg_spec.get('repeat_flag'),
                    value_spec=arg_spec['value'],
                    generator=arg_spec.get('generator'),
                    params=arg_spec.get('params')
                )
                sub_args[arg.name] = arg
            
            # Parse subcommand positional args
            sub_pos = []
            for pos_spec in sub_spec.get('positional', []):
                pos_arg = PositionalArg(
                    name=pos_spec['name'],
                    position=pos_spec['position'],
                    required=pos_spec.get('required', False),
                    variadic=pos_spec.get('variadic', False),
                    value_spec=pos_spec['value']
                )
                sub_pos.append(pos_arg)
            sub_pos = sorted(sub_pos, key=lambda x: x.position)
            
            subcommand = Subcommand(
                name=sub_spec['name'],
                description=sub_spec.get('description', ''),
                aliases=sub_spec.get('aliases', []),
                probability=sub_spec.get('probability', 0.5),
                arguments=sub_args,
                positional=sub_pos
            )
            subcommands[subcommand.name] = subcommand
        
        return subcommands
    
    def _parse_rules(self) -> List[Rule]:
        """Parse validation rules"""
        rules = []
        for rule_spec in self.config.get('rules', []):
            rule = Rule(
                rule_type=rule_spec['type'],
                arguments=rule_spec['arguments'],
                description=rule_spec.get('description')
            )
            rules.append(rule)
        return rules
    
    def _build_groups(self) -> Dict[str, List[str]]:
        """Build group mappings"""
        groups = {}
        for name in sorted(self.arguments.keys()):
            arg = self.arguments[name]
            if arg.group:
                if arg.group not in groups:
                    groups[arg.group] = []
                groups[arg.group].append(name)
        return groups


class Generator:
    """Generates valid command-line argument combinations"""
    
    def __init__(self, config: Dict[str, Any], solver: ConstraintSolver, rng: random.Random, create_dummy_files: bool = False):
        self.config = config
        self.solver = solver
        self.syntax = config.get('syntax', {})
        self.generation_params = config.get('generation', {})
        self.rng = rng  # Use dedicated random instance for reproducibility
        self.create_dummy_files = create_dummy_files
    
    def _trim_to_target_count(self, selected_args: List[str], target_count: int) -> List[str]:
        """Trim argument list to target count while preserving dependencies and rules.
        
        Args:
            selected_args: List of selected argument names (sorted)
            target_count: Desired number of arguments
            
        Returns:
            Trimmed list of argument names (sorted)
        """
        if len(selected_args) <= target_count:
            return selected_args
            
        # Identify must-keep arguments: required, has dependents, or satisfies rules
        must_keep = set()
        
        for arg_name in selected_args:
            arg = self.solver.arguments.get(arg_name)
            if arg and arg.required:
                must_keep.add(arg_name)
            
            # Check if any other selected arg depends on this one
            for other_name in selected_args:
                other_arg = self.solver.arguments.get(other_name)
                if other_arg and arg_name in other_arg.depends_on:
                    must_keep.add(arg_name)
        
        # Check rules - for one_of_required, keep at least one from the group
        for rule in self.solver.rules:
            if rule.rule_type == 'one_of_required':
                # Expand groups to get actual argument names
                expanded_args = set()
                for arg in rule.arguments:
                    if arg in self.solver.groups:
                        expanded_args.update(self.solver.groups[arg])
                    else:
                        expanded_args.add(arg)
                
                # Check if any from this rule are selected
                rule_args_selected = [a for a in expanded_args if a in selected_args]
                if rule_args_selected:
                    # Keep one randomly but deterministically
                    must_keep.add(self.rng.choice(sorted(rule_args_selected)))
        
        # Determine removable arguments
        can_remove = [a for a in selected_args if a not in must_keep]
        keep_count = len(must_keep)
        
        if keep_count <= target_count:
            # Can reach target by removing optional args
            to_remove = len(selected_args) - target_count
            if to_remove > 0 and can_remove:
                remove_these = self.rng.sample(can_remove, min(to_remove, len(can_remove)))
                return sorted([a for a in selected_args if a not in remove_these])
            return selected_args
        else:
            # Must keep more than target - keep all must_keep args
            return sorted(must_keep)
    
    def _add_to_target_count(self, selected_args: List[str], target_count: int) -> List[str]:
        """Add arguments to reach target count while respecting rules.
        
        Args:
            selected_args: List of selected argument names (sorted)
            target_count: Desired number of arguments
            
        Returns:
            Expanded list of argument names (sorted)
        """
        if len(selected_args) >= target_count:
            return selected_args
            
        available_args = [a for a in self.solver.arguments.keys() 
                         if a not in selected_args and self.solver.arguments[a].probability > 0]
        if not available_args:
            return selected_args
        
        # Add arguments one at a time, checking rules after each addition
        current = set(selected_args)
        self.rng.shuffle(available_args)
        
        for arg_name in available_args:
            if len(current) >= target_count:
                break
            
            # Try adding this argument
            current.add(arg_name)
            
            # Check if it violates any rules
            valid = True
            for rule in self.solver.rules:
                if rule.rule_type == 'mutually_exclusive':
                    expanded_args = set()
                    for r_arg in rule.arguments:
                        if r_arg in self.solver.groups:
                            expanded_args.update(self.solver.groups[r_arg])
                        else:
                            expanded_args.add(r_arg)
                    if len(expanded_args & current) > 1:
                        valid = False
                        break
            
            if not valid:
                current.discard(arg_name)
        
        return sorted(current)
    
    def generate_combination(self) -> Tuple[Optional[str], List[str], List[PositionalArg], int]:
        """Generate a single valid argument combination
        
        Returns:
            Tuple of (subcommand_name, selected argument names (sorted list), positional args, number of attempts)
        """
        # Decide if we should use a subcommand
        subcommand_name = None
        active_arguments = self.solver.arguments
        active_positional = self.solver.positional
        
        if self.solver.subcommands and self.rng.random() < 0.7:
            # Select a subcommand based on probability
            subcommands = list(self.solver.subcommands.values())
            weights = [sc.probability for sc in subcommands]
            if sum(weights) > 0:
                subcommand = self.rng.choices(subcommands, weights=weights, k=1)[0]
                subcommand_name = subcommand.name
                active_arguments = subcommand.arguments
                active_positional = subcommand.positional
        
        # Start with required arguments
        selected = set()
        for name in sorted(active_arguments.keys()):
            arg = active_arguments[name]
            if arg.required:
                selected.add(name)
        
        # Add arguments based on probability (sorted for determinism)
        for name in sorted(active_arguments.keys()):
            arg = active_arguments[name]
            if name not in selected and self.rng.random() < arg.probability:
                selected.add(name)
        
        # Resolve dependencies iteratively
        deps_added = True
        while deps_added:
            deps_added = False
            new_deps = set()
            for name in sorted(selected):  # Sorted for deterministic iteration
                deps = self._resolve_dependencies_for_args(name, selected, active_arguments)
                new_deps.update(deps - selected)
            if new_deps:
                selected.update(new_deps)
                deps_added = True
        
        # Validate and fix rules (handles mutually_exclusive, one_of_required, etc.)
        if subcommand_name is None:
            selected = self._fix_rules(selected)
        
        # Limit to max_args
        max_args = self.generation_params.get('max_args', 20)
        if len(selected) > max_args:
            # Deterministically select first N alphabetically
            selected = set(sorted(selected)[:max_args])
        
        # Convert to sorted list for deterministic iteration
        return subcommand_name, sorted(selected), active_positional, 1
    
    def _resolve_dependencies_for_args(self, arg_name: str, selected: Set[str], 
                                       arguments: Dict[str, Argument]) -> Set[str]:
        """Resolve dependencies for an argument"""
        arg = arguments[arg_name]
        deps = set()
        
        for dep in arg.depends_on:
            # Check if it's a group or argument
            if dep in self.solver.groups:
                # Need at least one from the group
                group_members = [m for m in self.solver.groups[dep] if m in selected]
                if not group_members:
                    # Add one from the group, respecting probability > 0
                    available = [m for m in self.solver.groups[dep] 
                                if m in arguments and arguments[m].probability > 0]
                    if available:
                        deps.add(self.rng.choice(available))
            else:
                # Direct dependency - only add if probability > 0
                if dep in arguments and arguments[dep].probability > 0:
                    deps.add(dep)
        
        return deps
    
    def _fix_rules(self, selected: Set[str]) -> Set[str]:
        """Fix rule violations deterministically"""
        for rule in self.solver.rules:
            # Expand groups in rule arguments
            expanded_args = set()
            for arg in rule.arguments:
                if arg in self.solver.groups:
                    expanded_args.update(self.solver.groups[arg])
                else:
                    expanded_args.add(arg)
            
            selected_from_rule = expanded_args & selected
            
            if rule.rule_type == 'mutually_exclusive' and len(selected_from_rule) > 1:
                # Keep one randomly but deterministically
                to_keep = self.rng.choice(sorted(selected_from_rule))
                for arg in selected_from_rule:
                    if arg != to_keep:
                        selected.discard(arg)
            
            elif rule.rule_type == 'one_of_required' and len(selected_from_rule) == 0:
                # Add one randomly but respect probability > 0
                available = [arg for arg in expanded_args 
                            if arg in self.solver.arguments and self.solver.arguments[arg].probability > 0]
                if available:
                    selected.add(self.rng.choice(sorted(available)))
            
            elif rule.rule_type == 'all_or_none':
                if 0 < len(selected_from_rule) < len(expanded_args):
                    # Either add all or remove all - only add those with probability > 0
                    available = [arg for arg in expanded_args 
                                if arg in self.solver.arguments and self.solver.arguments[arg].probability > 0]
                    if available:
                        selected.update(available)
        
        return selected
    
    def _format_csv_range(self, numbers: List[int]) -> str:
        """Format list of numbers as CSV range (e.g., 0,2-5,8)
        
        Args:
            numbers: List of integers
            
        Returns:
            Formatted range string with sorted, deduplicated numbers
        """
        if not numbers:
            return ""
        
        # Sort and deduplicate
        unique_sorted = sorted(set(numbers))
        
        if len(unique_sorted) == 1:
            return str(unique_sorted[0])
        
        # Build ranges
        ranges = []
        start = unique_sorted[0]
        prev = start
        
        for num in unique_sorted[1:]:
            if num == prev + 1:
                # Continue range
                prev = num
            else:
                # End of range
                if start == prev:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{prev}")
                start = num
                prev = num
        
        # Add final range
        if start == prev:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{prev}")
        
        return ",".join(ranges)
    
    def _generate_file_value(self, value_spec: Dict[str, Any]) -> str:
        """Generate a file path by scanning directory or creating dummy files.
        
        Args:
            value_spec: Should contain:
                - path: Directory to scan for files (optional)
                - pattern: Regex pattern to filter files (optional)
        
        Returns:
            Full path to a file
        """
        scan_path = value_spec.get('path', '')
        pattern = value_spec.get('pattern', '')
        
        # Try to scan for real files
        if scan_path and os.path.isdir(scan_path):
            files = []
            try:
                for entry in os.listdir(scan_path):
                    full_path = os.path.join(scan_path, entry)
                    if os.path.isfile(full_path):
                        if pattern:
                            # Filter by pattern
                            if re.search(pattern, entry) or re.search(pattern, full_path):
                                files.append(full_path)
                        else:
                            files.append(full_path)
                
                if files:
                    return self.rng.choice(files)
            except (PermissionError, OSError):
                pass
        
        # Generate dummy file
        if scan_path and os.path.isdir(scan_path):
            base_dir = scan_path
        else:
            # Use temp directory
            base_dir = tempfile.gettempdir()
        
        # Generate filename from pattern or use numbered default
        if pattern and RSTR_AVAILABLE:
            # Generate filename matching the regex pattern
            filename = rstr.xeger(pattern)
        elif pattern:
            # Fallback: try to extract extension from pattern
            # Look for literal extensions like \.json, \.txt, etc.
            ext_match = re.search(r'\\\.([\w]+)(?:\$)?$', pattern)
            if ext_match:
                ext = ext_match.group(1)
                filename = f"file_{self.rng.randint(1, 9999)}.{ext}"
            else:
                filename = f"file_{self.rng.randint(1, 9999)}.dat"
        else:
            filename = f"file_{self.rng.randint(1, 9999)}.dat"
        
        full_path = os.path.join(base_dir, filename)
        
        # Create the dummy file if requested
        if self.create_dummy_files:
            try:
                Path(full_path).touch(exist_ok=True)
            except (PermissionError, OSError):
                pass  # Silently ignore if we can't create it
        
        return full_path
    
    def _generate_directory_value(self, value_spec: Dict[str, Any]) -> str:
        """Generate a directory path by scanning or creating dummy directories.
        
        Args:
            value_spec: Should contain:
                - path: Root directory to scan for subdirectories (optional)
                - pattern: Regex pattern to filter directories (optional)
        
        Returns:
            Full path to a directory
        """
        scan_path = value_spec.get('path', '')
        pattern = value_spec.get('pattern', '')
        
        # Try to scan for real directories
        if scan_path and os.path.isdir(scan_path):
            directories = []
            try:
                # Get immediate subdirectories
                for entry in os.listdir(scan_path):
                    full_path = os.path.join(scan_path, entry)
                    if os.path.isdir(full_path):
                        if pattern:
                            # Filter by pattern
                            if re.search(pattern, entry) or re.search(pattern, full_path):
                                directories.append(full_path)
                        else:
                            directories.append(full_path)
                
                # Also scan recursively for more options
                for root, dirs, _ in os.walk(scan_path):
                    for d in dirs:
                        full_path = os.path.join(root, d)
                        if pattern:
                            if re.search(pattern, d) or re.search(pattern, full_path):
                                directories.append(full_path)
                        else:
                            directories.append(full_path)
                    # Limit recursion depth to avoid performance issues
                    if len(directories) > 100:
                        break
                
                if directories:
                    return self.rng.choice(directories)
            except (PermissionError, OSError):
                pass
        
        # Generate dummy directory
        if scan_path and os.path.isdir(scan_path):
            base_dir = scan_path
        else:
            # Use temp directory
            base_dir = tempfile.gettempdir()
        
        # Generate directory name from pattern or use numbered default
        if pattern and RSTR_AVAILABLE:
            # Generate dirname matching the regex pattern
            dirname = rstr.xeger(pattern)
        elif pattern:
            # Fallback: extract meaningful dirname from pattern
            dirname = re.sub(r'[\^$.*+?{}\[\]\\|()]', '', pattern)
            if not dirname or dirname == '':
                dirname = f"dir_{self.rng.randint(1, 9999)}"
        else:
            dirname = f"dir_{self.rng.randint(1, 9999)}"
        
        full_path = os.path.join(base_dir, dirname)
        
        # Create the dummy directory if requested
        if self.create_dummy_files:
            try:
                Path(full_path).mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                pass  # Silently ignore if we can't create it
        
        return full_path
    
    def generate_value(self, value_spec: Dict[str, Any], arg_name: str = "", 
                       generator: Optional[str] = None, 
                       params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generate a value based on value specification.
        
        Args:
            value_spec: The value specification dict with 'kind' and other params
            arg_name: Name of the argument (for context)
            generator: Optional name of custom generator to use
            params: Optional parameters for the custom generator
        """
        kind = value_spec['kind']
        
        # Custom generator support - takes priority over kind-based generation
        if kind == 'custom' or generator:
            gen_name = generator or value_spec.get('generator')
            gen_params = params or value_spec.get('params', {})
            
            if gen_name:
                gen_func = GeneratorRegistry.get(gen_name)
                if gen_func:
                    return gen_func(self.rng, gen_params)
                else:
                    # Generator not found - throw clear error
                    available = GeneratorRegistry.list_generators()
                    available_str = f"\nAvailable generators: {', '.join(sorted(available))}" if available else "\nNo custom generators loaded."
                    raise ValueError(
                        f"Custom generator '{gen_name}' not found for argument '{arg_name}'.\n"
                        f"Make sure the generator is registered with @register_generator('{gen_name}').\n"
                        f"Load custom generators with: python argsfuzz.py config.json -g generators.py{available_str}"
                    )
            raise ValueError(f"Argument '{arg_name}' has kind='custom' but no 'generator' specified.")
        
        if kind == 'flag':
            return None  # Flags have no value
        
        elif kind == 'integer':
            min_val = value_spec['min']
            max_val = value_spec['max']
            return str(self.rng.randint(min_val, max_val))
        
        elif kind == 'integer_optional':
            # Sometimes return no value
            if self.rng.random() < 0.3:
                return None
            min_val = value_spec['min']
            max_val = value_spec['max']
            return str(self.rng.randint(min_val, max_val))
        
        elif kind == 'float':
            min_val = value_spec['min']
            max_val = value_spec['max']
            return f"{self.rng.uniform(min_val, max_val):.2f}"
        
        elif kind == 'string':
            pattern = value_spec.get('pattern')
            if pattern and RSTR_AVAILABLE:
                # Generate string matching the regex pattern
                return rstr.xeger(pattern)
            elif pattern:
                # Fallback if rstr not available - strip regex chars
                clean = re.sub(r'[\^$.*+?{}\[\]\\|()]', '', pattern)
                return clean if clean else f"string_{self.rng.randint(1000, 9999)}"
            return f"value_{self.rng.randint(100, 999)}"
        
        elif kind == 'enum':
            values = value_spec.get('values', [])
            if values:
                return self.rng.choice(values)
            return "default"
        
        elif kind == 'list':
            values = value_spec.get('values', [])
            separator = value_spec.get('separator', ',')
            min_count = value_spec.get('min_count', 1)
            max_count = value_spec.get('max_count', 3)
            count = self.rng.randint(min_count, min(max_count, len(values) if values else max_count))
            
            if values:
                selected = self.rng.sample(values, min(count, len(values)))
            else:
                # Generate numeric list
                min_val = value_spec.get('min', 0)
                max_val = value_spec.get('max', 10)
                format_type = value_spec.get('format', 'plain')
                
                if format_type == 'csv_range':
                    # Generate random numbers then format as ranges
                    numbers = [self.rng.randint(min_val, max_val) for _ in range(count)]
                    return self._format_csv_range(numbers)
                else:
                    # Just generate numbers as strings
                    numbers = [self.rng.randint(min_val, max_val) for _ in range(count)]
                    selected = [str(n) for n in numbers]
            
            return separator.join(selected)
        
        elif kind == 'file':
            # Scan for files in provided path, filter by pattern, or generate dummy
            return self._generate_file_value(value_spec)
        
        elif kind == 'directory':
            # Scan for directories in provided path, filter by pattern, or generate dummy
            return self._generate_directory_value(value_spec)
        
        return "default_value"
    
    def format_argument(self, arg: Argument, value: Optional[str]) -> List[str]:
        """Format an argument with its value"""
        flag = self.rng.choice(arg.flags)
        
        if value is None:
            return [flag]
        
        # Decide on format (space vs equals)
        use_equals = False
        equals_prob = self.generation_params.get('equals_form_probability', 0.0)
        if flag.startswith('--') and self.rng.random() < equals_prob:
            use_equals = True
        
        if use_equals:
            return [f"{flag}={value}"]
        else:
            return [flag, value]


class Mutator:
    """Mutates valid combinations to create invalid test cases.
    
    This class applies various mutation strategies to introduce errors that would
    violate CLI constraints, useful for testing error handling.
    """
    
    def __init__(self, config: Dict[str, Any], solver: ConstraintSolver, rng: random.Random):
        self.config = config
        self.solver = solver
        self.generation_params = config.get('generation', {})
        self.rng = rng
    
    def mutate(self, args: List[str], target_invalid: bool) -> List[str]:
        """Mutate argument list
        
        Args:
            args: List of command-line arguments
            target_invalid: If True, ensure result is invalid
        
        Returns:
            Mutated argument list
        """
        if not target_invalid:
            return args
        
        mutation_strategies = [
            self._add_invalid_flag,
            self._duplicate_flag,
            self._remove_required_arg,
            self._add_conflicting_args,
            self._mutate_value,
        ]
        
        # Apply random mutation
        strategy = self.rng.choice(mutation_strategies)
        return strategy(args.copy())
    
    def _add_invalid_flag(self, args: List[str]) -> List[str]:
        """Add a completely invalid flag by generating or mutating an existing one"""
        # Shell-safe characters for flags (alphanumerics + dash/underscore)
        flag_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
        
        if args and self.rng.random() < 0.5:
            # Mutate an existing flag from the arguments
            flags = [a for a in args if a.startswith('-')]
            if flags:
                mutated = self._mutate_string(self.rng.choice(flags), flag_chars)
                args.insert(self.rng.randint(0, len(args)), mutated)
                return args
        
        # Generate a random invalid flag using shell-safe characters
        # (alphanumerics + dash/underscore to avoid control chars that break harnesses)
        flag_type = self.rng.choice(['short', 'long'])
        if flag_type == 'short':
            # Generate random single letter flag: -X
            char = self.rng.choice(flag_chars)
            invalid_flag = f'-{char}'
        else:
            # Generate random long flag: --random-text
            length = self.rng.randint(3, 15)
            chars = ''.join(self.rng.choice(flag_chars) for _ in range(length))
            invalid_flag = f'--{chars}'
        
        args.insert(self.rng.randint(0, len(args)), invalid_flag)
        return args
    
    def _duplicate_flag(self, args: List[str]) -> List[str]:
        """Duplicate a flag (invalid if duplicates not allowed)"""
        if not self.syntax.get('allow_duplicates', False):
            flags = [a for a in args if a.startswith('-')]
            if flags:
                dup_flag = self.rng.choice(flags)
                args.insert(self.rng.randint(0, len(args)), dup_flag)
        return args
    
    def _remove_required_arg(self, args: List[str]) -> List[str]:
        """Remove a required argument"""
        # Find required arguments
        required_args = [name for name, arg in self.solver.arguments.items() if arg.required]
        if required_args:
            req_arg = self.solver.arguments[self.rng.choice(required_args)]
            # Remove its flags from args
            for flag in req_arg.flags:
                if flag in args:
                    idx = args.index(flag)
                    args.pop(idx)
                    # Remove value if present
                    if idx < len(args) and not args[idx].startswith('-'):
                        args.pop(idx)
                    break
        return args
    
    def _add_conflicting_args(self, args: List[str]) -> List[str]:
        """Add conflicting arguments"""
        for rule in self.solver.rules:
            if rule.rule_type == 'mutually_exclusive' and len(rule.arguments) >= 2:
                # Expand groups to get actual argument names
                expanded_args = []
                for arg_ref in rule.arguments:
                    if arg_ref in self.solver.groups:
                        # It's a group - add all members
                        expanded_args.extend(self.solver.groups[arg_ref])
                    else:
                        # Direct argument
                        expanded_args.append(arg_ref)
                
                # Pick two different args to conflict
                if len(expanded_args) >= 2:
                    conflicting_pair = self.rng.sample(expanded_args, 2)
                    arg1 = self.solver.arguments.get(conflicting_pair[0])
                    arg2 = self.solver.arguments.get(conflicting_pair[1])
                    if arg1 and arg2:
                        args.extend([self.rng.choice(arg1.flags), self.rng.choice(arg2.flags)])
                        break
        return args
    
    def _mutate_value(self, args: List[str]) -> List[str]:
        """Mutate a value to be invalid by randomly adding/removing/replacing a character"""
        # Randomly mutate either a flag or a value
        if args and self.rng.random() < 0.5:
            # Mutate a flag (use safe characters)
            flags = [i for i, arg in enumerate(args) if arg.startswith('-')]
            if flags:
                idx = self.rng.choice(flags)
                flag_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
                args[idx] = self._mutate_string(args[idx], flag_chars)
        else:
            # Mutate a value (use extended ASCII for better fuzzing)
            for i, arg in enumerate(args):
                if arg.startswith('-') and i + 1 < len(args) and not args[i + 1].startswith('-'):
                    value_chars = ''.join(chr(i) for i in range(32, 256))
                    args[i + 1] = self._mutate_string(args[i + 1], value_chars)
                    break
        return args
    
    def _mutate_string(self, s: str, chars: str) -> str:
        """Randomly add, remove, or replace a character in a string
        
        Args:
            s: String to mutate
            chars: Character set to use for mutations
        """
        if not s:
            return self.rng.choice(chars)
        
        mutation_type = self.rng.choice(['add', 'remove', 'replace'])
        
        if mutation_type == 'add':
            pos = self.rng.randint(0, len(s))
            char = self.rng.choice(chars)
            return s[:pos] + char + s[pos:]
        
        elif mutation_type == 'remove' and len(s) > 1:
            pos = self.rng.randint(0, len(s) - 1)
            return s[:pos] + s[pos + 1:]
        
        else:  # replace
            pos = self.rng.randint(0, len(s) - 1)
            char = self.rng.choice(chars)
            return s[:pos] + char + s[pos + 1:]
    
    @property
    def syntax(self) -> Dict[str, Any]:
        return self.config.get('syntax', {})


class CorpusWriter:
    """Writes generated test cases to output"""
    
    def __init__(self, output_path: Path, output_format: OutputFormat):
        self.output_path = output_path
        self.output_format = output_format
        self.generation_count = 0
    
    def initialize(self):
        """Initialize output destination"""
        if self.output_format == OutputFormat.DIRECTORY:
            self.output_path.mkdir(parents=True, exist_ok=True)
        else:
            # Create parent directory for file
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            # Clear file if it exists
            if self.output_path.exists():
                self.output_path.unlink()
    
    def write(self, command_line: str):
        """Write a single test case"""
        try:
            if self.output_format == OutputFormat.DIRECTORY:
                # Write to individual file
                file_path = self.output_path / f"test_{self.generation_count:06d}.txt"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(command_line + '\n')
            else:
                # Append to single file
                with open(self.output_path, 'a', encoding='utf-8') as f:
                    f.write(command_line + '\n')
            
            self.generation_count += 1
        except IOError as e:
            raise IOError(f"Failed to write test case {self.generation_count}: {e}")
    
    def finalize(self) -> int:
        """Finalize output and return count"""
        return self.generation_count


class FuzzGenerator:
    """Main fuzzing generator orchestrator"""
    
    def __init__(self, config_path: Path, schema_path: Path, gen_config: GenerationConfig):
        self.config_path = config_path
        self.schema_path = schema_path
        self.gen_config = gen_config
        
        # Initialize dedicated random number generator for reproducibility
        self.rng = random.Random(gen_config.seed)
        self.verbose = gen_config.verbose
        
        # Pipeline components
        self.validator = SchemaValidator(schema_path)
        self.config = None
        self.solver = None
        self.generator = None
        self.mutator = None
        self.writer = None
    
    def run(self) -> int:
        """Run the complete generation pipeline"""
        if self.verbose:
            print(f"[1/7] Loading and validating schema...")
        self.config = self.validator.validate(self.config_path)
        tool_name = self.config.get('metadata', {}).get('tool_name', 'tool')
        if self.verbose:
            print(f"      Tool: {tool_name}")
        
        # Load custom generators if specified
        if self.verbose:
            print(f"[2/7] Loading custom generators...")
        loaded_count = 0
        if self.gen_config.generators_file:
            loaded_count = GeneratorRegistry.load_from_file(self.gen_config.generators_file)
        if self.verbose:
            print(f"      Built-in generators: {len(GeneratorRegistry.list_generators()) - loaded_count}")
            print(f"      Custom generators loaded: {loaded_count}")
        
        if self.verbose:
            print(f"[3/7] Building constraint solver...")
        self.solver = ConstraintSolver(self.config, self.rng)
        if self.verbose:
            print(f"      Arguments: {len(self.solver.arguments)}")
            print(f"      Subcommands: {len(self.solver.subcommands)}")
            print(f"      Rules: {len(self.solver.rules)}")
        
        if self.verbose:
            print(f"[4/7] Initializing generator...")
        self.generator = Generator(self.config, self.solver, self.rng, self.gen_config.create_dummy_files)
        
        if self.verbose:
            print(f"[5/7] Initializing mutator...")
        self.mutator = Mutator(self.config, self.solver, self.rng)
        
        if self.verbose:
            print(f"[6/7] Initializing corpus writer...")
        self.writer = CorpusWriter(self.gen_config.output_path, self.gen_config.output_format)
        self.writer.initialize()
        
        if self.verbose:
            print(f"[7/7] Generating test cases...")
            print(f"      Target: {self.gen_config.num_generations} generations")
            print(f"      Invalid ratio: {self.gen_config.invalid_ratio:.1%}")
        
        valid_count = 0
        invalid_count = 0
        
        for gen_idx in range(self.gen_config.num_generations):
            
            # Determine if this should be invalid
            should_be_invalid = self.rng.random() < self.gen_config.invalid_ratio
            
            # Generate combination
            subcommand_name, selected_args, active_positional, _ = self.generator.generate_combination()
            
            # Randomly pick target argument count between min and max
            max_args = self.gen_config.max_args if self.gen_config.max_args is not None else self.config.get('generation', {}).get('max_args', 20)
            target_count = self.rng.randint(self.gen_config.min_args, max_args)
            
            # Adjust to target count using helper methods
            if len(selected_args) > target_count:
                selected_args = self.generator._trim_to_target_count(selected_args, target_count)
            elif len(selected_args) < target_count:
                selected_args = self.generator._add_to_target_count(selected_args, target_count)
            
            # Re-validate rules after adjusting count
            selected_set = set(selected_args)
            selected_set = self.generator._fix_rules(selected_set)
            selected_args = sorted(selected_set)
            
            # Build command line (WITHOUT tool name)
            cmd_parts = []
            
            # Add global arguments if using subcommand
            global_args = []
            if subcommand_name:
                global_arg_names = self.config.get('global_arguments', [])
                for arg_name in selected_args:  # Already sorted
                    if arg_name in global_arg_names and arg_name in self.solver.arguments:
                        global_args.append(arg_name)
                
                # Add global arguments first
                for arg_name in global_args:
                    arg = self.solver.arguments[arg_name]
                    value = self.generator.generate_value(
                        arg.value_spec, arg_name, arg.generator, arg.params
                    )
                    formatted = self.generator.format_argument(arg, value)
                    cmd_parts.extend(formatted)
                
                # Add subcommand
                cmd_parts.append(subcommand_name)
                
                # Get subcommand object for its arguments
                subcommand = self.solver.subcommands[subcommand_name]
                active_arguments = subcommand.arguments
                selected_args = [a for a in selected_args if a not in global_args]
            else:
                active_arguments = self.solver.arguments
            
            # Add flags and options (already sorted)
            for arg_name in selected_args:
                if arg_name not in active_arguments:
                    continue
                arg = active_arguments[arg_name]
                
                # Determine repetitions
                repeat_count = 1
                if arg.repeat_flag:
                    repeat_probability = arg.repeat_flag.get('probability', 1.0)
                    if self.rng.random() < repeat_probability:
                        min_occurs = arg.repeat_flag.get('min_occurs', 1)
                        max_occurs = arg.repeat_flag.get('max_occurs', 1)
                        repeat_count = self.rng.randint(min_occurs, max_occurs)
                
                for _ in range(repeat_count):
                    value = self.generator.generate_value(
                        arg.value_spec, arg_name, arg.generator, arg.params
                    )
                    formatted = self.generator.format_argument(arg, value)
                    cmd_parts.extend(formatted)
            
            # Add positional arguments
            for pos_arg in active_positional:
                if pos_arg.required or self.rng.random() < 0.5:
                    if pos_arg.variadic:
                        count = self.rng.randint(1, 3)
                        for _ in range(count):
                            value = self.generator.generate_value(pos_arg.value_spec)
                            if value:
                                cmd_parts.append(value)
                    else:
                        value = self.generator.generate_value(pos_arg.value_spec)
                        if value:
                            cmd_parts.append(value)
            
            # Apply mutation if needed
            cmd_parts = self.mutator.mutate(cmd_parts, should_be_invalid)
            
            # Always shuffle deterministically to avoid sorted output
            # (We sort during generation for determinism, but shuffle at the end)
            # Shuffle flag-value pairs together, keep positional at end
            idx = 0
            flag_groups = []
            while idx < len(cmd_parts):
                if cmd_parts[idx].startswith('-'):
                    # Check if next item is a value (not a flag)
                    if '=' in cmd_parts[idx]:
                        # Single item: --flag=value
                        flag_groups.append([cmd_parts[idx]])
                        idx += 1
                    elif idx + 1 < len(cmd_parts) and not cmd_parts[idx + 1].startswith('-'):
                        # Two items: --flag value
                        flag_groups.append([cmd_parts[idx], cmd_parts[idx + 1]])
                        idx += 2
                    else:
                        # Just a flag with no value
                        flag_groups.append([cmd_parts[idx]])
                        idx += 1
                else:
                    # Positional argument - stop collecting flags
                    break
            
            # Collect remaining positional args
            positional = cmd_parts[idx:]
            
            # Shuffle the flag groups deterministically
            self.rng.shuffle(flag_groups)
            
            # Flatten flag groups and append positional
            cmd_parts = [item for group in flag_groups for item in group] + positional
            
            # Create command line
            command_line = ' '.join(cmd_parts)
            
            # Write to corpus
            self.writer.write(command_line)
            
            if should_be_invalid:
                invalid_count += 1
            else:
                valid_count += 1
            
            if self.verbose and (gen_idx + 1) % 10 == 0:
                print(f"      Progress: {gen_idx + 1}/{self.gen_config.num_generations}", end='\r')
        
        total = self.writer.finalize()
        
        if self.verbose:
            print(f"\nGeneration complete!")
            print(f"  Total: {total} test cases")
            print(f"  Valid: {valid_count}")
            print(f"  Invalid: {invalid_count}")
            print(f"  Output: {self.gen_config.output_path}")
            print(f"  Format: {self.gen_config.output_format.value}")
        
        return total


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Generate fuzzing test cases from CLI argument schema',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 100 valid test cases
  python fuzz_generator.py ../tslengine_cli_fuzz.json -n 100
  
  # Generate with 20% invalid cases
  python fuzz_generator.py ../tslengine_cli_fuzz.json -n 500 --invalid-ratio 0.2
  
  # Output to directory (one file per test)
  python fuzz_generator.py ../tslengine_cli_fuzz.json -n 100 -f directory -o corpus/
  
  # Reproducible generation with seed
  python fuzz_generator.py ../tslengine_cli_fuzz.json -n 100 --seed 42
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
                        help='Maximum number of arguments per generation (default: use schema max_args)')
    parser.add_argument('--invalid-ratio', type=float, default=0.0,
                        help='Ratio of invalid test cases (0.0-1.0, default: 0.0)')
    parser.add_argument('-f', '--format', choices=['file', 'directory'],
                        default='file', help='Output format (default: file)')
    parser.add_argument('-o', '--output', type=Path, default=Path('corpus.txt'),
                        help='Output path (file or directory, default: corpus.txt)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')
    parser.add_argument('--create-dummy-files', action='store_true',
                        help='Create actual dummy files/directories in /tmp for generated paths')
    parser.add_argument('-g', '--generators', type=Path, default=None,
                        help='Path to Python file with custom generator functions')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='Suppress progress output (useful for library usage)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.config.exists():
        print(f"ERROR: Configuration file not found: {args.config}")
        sys.exit(1)
    
    # Default schema path
    if args.schema is None:
        args.schema = Path(__file__).parent / 'argsfuzz-schema.json'
    
    if not args.schema.exists():
        print(f"ERROR: Schema file not found: {args.schema}")
        sys.exit(1)
    
    if args.generators is not None and not args.generators.exists():
        print(f"ERROR: Generators file not found: {args.generators}")
        sys.exit(1)
    
    if not 0.0 <= args.invalid_ratio <= 1.0:
        print(f"ERROR: Invalid ratio must be between 0.0 and 1.0")
        sys.exit(1)
    
    # Auto-detect verbosity: enable by default in CLI unless --quiet is passed
    # Check if stdout is a TTY (interactive terminal) to avoid noise when piped
    verbose = not args.quiet and sys.stdout.isatty()
    
    # Create generation config
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
        # Run generator
        generator = FuzzGenerator(args.config, args.schema, gen_config)
        count = generator.run()
        sys.exit(0 if count > 0 else 1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# Public API for library usage
__all__ = [
    'FuzzGenerator',
    'GenerationConfig',
    'OutputFormat',
    'SchemaValidator',
    'ConstraintSolver',
    'Generator',
    'Mutator',
    'CorpusWriter',
    'Argument',
    'PositionalArg',
    'Rule',
    'Subcommand',
]

"""
Library usage example:
    
    from argsfuzz import FuzzGenerator, GenerationConfig, OutputFormat
    from pathlib import Path
    
    # Quiet by default when used as library
    config = GenerationConfig(
        num_generations=1000,
        invalid_ratio=0.2,
        output_path=Path('corpus.txt'),
        seed=42
        # verbose defaults to False (no output)
    )
    
    fuzzer = FuzzGenerator('my_tool.json', 'argsfuzz-schema.json', config)
    count = fuzzer.run()  # Silent by default
    print(f"Generated {count} test cases")
    
    # Enable verbose output if needed:
    config_verbose = GenerationConfig(..., verbose=True)
"""


if __name__ == '__main__':
    main()
