"""Configuration and data classes for argsfuzz."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any


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
    min_args: int = 1
    max_args: Optional[int] = None
    create_dummy_files: bool = False
    verbose: bool = False
    generators_file: Optional[Path] = None


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
    generator: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


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


@dataclass
class Subcommand:
    """Represents a subcommand"""
    name: str
    description: str
    aliases: List[str]
    probability: float
    arguments: Dict[str, 'Argument']
    positional: List['PositionalArg']
