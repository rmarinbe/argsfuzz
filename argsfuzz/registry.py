"""Generator registry for custom value generators."""

import importlib.util
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any


# Type alias for custom generator functions
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
        
        Returns: Number of generators loaded.
        """
        if not filepath.exists():
            return 0
        
        spec = importlib.util.spec_from_file_location("custom_generators", filepath)
        if spec is None or spec.loader is None:
            return 0
        
        module = importlib.util.module_from_spec(spec)
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
