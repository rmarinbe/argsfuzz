"""
argsfuzz - CLI Argument Fuzzing Generator

A schema-driven CLI argument fuzzing generator for testing command-line tools.
"""

from .config import (
    GenerationConfig,
    OutputFormat,
    Argument,
    PositionalArg,
    Rule,
    Subcommand,
)
from .registry import GeneratorRegistry, register_generator
from .schema import SchemaValidator
from .solver import ConstraintSolver
from .constraints import ConstraintValidator
from .generator import Generator
from .values import ValueGenerator
from .mutator import Mutator
from .writer import CorpusWriter
from .fuzzer import FuzzGenerator


__version__ = '1.0.0'

__all__ = [
    # Main entry point
    'FuzzGenerator',
    
    # Configuration
    'GenerationConfig',
    'OutputFormat',
    
    # Data classes
    'Argument',
    'PositionalArg', 
    'Rule',
    'Subcommand',
    
    # Components
    'SchemaValidator',
    'ConstraintSolver',
    'ConstraintValidator',
    'Generator',
    'ValueGenerator',
    'Mutator',
    'CorpusWriter',
    
    # Registry
    'GeneratorRegistry',
    'register_generator',
]
