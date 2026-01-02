#!/usr/bin/env python3
"""
CLI Argument Fuzzing Generator

This is a backward-compatible wrapper. The implementation has been refactored
into the argsfuzz package for better maintainability.

Pipeline:
    schema.json → SchemaValidator → ConstraintSolver → Generator → Mutator → CorpusWriter
"""

# Re-export everything from the package for backward compatibility
from argsfuzz import (
    FuzzGenerator,
    GenerationConfig,
    OutputFormat,
    SchemaValidator,
    ConstraintSolver,
    ConstraintValidator,
    Generator,
    ValueGenerator,
    Mutator,
    CorpusWriter,
    Argument,
    PositionalArg,
    Rule,
    Subcommand,
    GeneratorRegistry,
    register_generator,
)

from argsfuzz.__main__ import main

# For scripts that import RSTR_AVAILABLE
try:
    import rstr
    RSTR_AVAILABLE = True
except ImportError:
    RSTR_AVAILABLE = False


__all__ = [
    'FuzzGenerator',
    'GenerationConfig',
    'OutputFormat',
    'SchemaValidator',
    'ConstraintSolver',
    'ConstraintValidator',
    'Generator',
    'ValueGenerator',
    'Mutator',
    'CorpusWriter',
    'Argument',
    'PositionalArg',
    'Rule',
    'Subcommand',
    'GeneratorRegistry',
    'register_generator',
    'RSTR_AVAILABLE',
]


if __name__ == '__main__':
    main()
