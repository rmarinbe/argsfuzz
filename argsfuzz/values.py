"""Value generation for different argument types."""

import os
import re
import random
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any

from .registry import GeneratorRegistry

try:
    import rstr
    RSTR_AVAILABLE = True
except ImportError:
    RSTR_AVAILABLE = False


class ValueGenerator:
    """Generates values for different argument types."""
    
    def __init__(self, rng: random.Random, create_dummy_files: bool = False):
        self.rng = rng
        self.create_dummy_files = create_dummy_files
    
    def generate(self, value_spec: Dict[str, Any], arg_name: str = "",
                 generator: Optional[str] = None,
                 params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generate a value based on value specification."""
        kind = value_spec['kind']
        
        # Custom generator support
        if kind == 'custom' or generator:
            return self._generate_custom(value_spec, arg_name, generator, params)
        
        generators = {
            'flag': lambda: None,
            'integer': lambda: self._generate_integer(value_spec),
            'integer_optional': lambda: self._generate_integer_optional(value_spec),
            'float': lambda: self._generate_float(value_spec),
            'string': lambda: self._generate_string(value_spec),
            'enum': lambda: self._generate_enum(value_spec),
            'list': lambda: self._generate_list(value_spec),
            'file': lambda: self._generate_file(value_spec),
            'directory': lambda: self._generate_directory(value_spec),
        }
        
        gen_func = generators.get(kind)
        if gen_func:
            return gen_func()
        
        return "default_value"
    
    def _generate_custom(self, value_spec: Dict[str, Any], arg_name: str,
                         generator: Optional[str], 
                         params: Optional[Dict[str, Any]]) -> str:
        """Generate value using custom generator."""
        gen_name = generator or value_spec.get('generator')
        gen_params = params or value_spec.get('params', {})
        
        if gen_name:
            gen_func = GeneratorRegistry.get(gen_name)
            if gen_func:
                return gen_func(self.rng, gen_params)
            else:
                available = GeneratorRegistry.list_generators()
                available_str = f"\nAvailable: {', '.join(sorted(available))}" if available else ""
                raise ValueError(
                    f"Generator '{gen_name}' not found for '{arg_name}'.{available_str}"
                )
        raise ValueError(f"Argument '{arg_name}' has kind='custom' but no 'generator'.")
    
    def _generate_integer(self, spec: Dict[str, Any]) -> str:
        return str(self.rng.randint(spec['min'], spec['max']))
    
    def _generate_integer_optional(self, spec: Dict[str, Any]) -> Optional[str]:
        if self.rng.random() < 0.3:
            return None
        return str(self.rng.randint(spec['min'], spec['max']))
    
    def _generate_float(self, spec: Dict[str, Any]) -> str:
        return f"{self.rng.uniform(spec['min'], spec['max']):.2f}"
    
    def _generate_string(self, spec: Dict[str, Any]) -> str:
        pattern = spec.get('pattern')
        if pattern and RSTR_AVAILABLE:
            return rstr.xeger(pattern)
        elif pattern:
            clean = re.sub(r'[\^$.*+?{}\[\]\\|()]', '', pattern)
            return clean if clean else f"string_{self.rng.randint(1000, 9999)}"
        return f"value_{self.rng.randint(100, 999)}"
    
    def _generate_enum(self, spec: Dict[str, Any]) -> str:
        values = spec.get('values', ['default'])
        return self.rng.choice(values)
    
    def _generate_list(self, spec: Dict[str, Any]) -> str:
        values = spec.get('values', [])
        separator = spec.get('separator', ',')
        min_count = spec.get('min_count', 1)
        max_count = spec.get('max_count', 3)
        count = self.rng.randint(min_count, min(max_count, len(values) if values else max_count))
        
        if values:
            selected = self.rng.sample(values, min(count, len(values)))
        else:
            min_val = spec.get('min', 0)
            max_val = spec.get('max', 10)
            format_type = spec.get('format', 'plain')
            
            numbers = [self.rng.randint(min_val, max_val) for _ in range(count)]
            
            if format_type == 'csv_range':
                return self._format_csv_range(numbers)
            
            selected = [str(n) for n in numbers]
        
        return separator.join(selected)
    
    def _format_csv_range(self, numbers: List[int]) -> str:
        """Format list of numbers as CSV range (e.g., 0,2-5,8)"""
        if not numbers:
            return ""
        
        unique_sorted = sorted(set(numbers))
        
        if len(unique_sorted) == 1:
            return str(unique_sorted[0])
        
        ranges = []
        start = prev = unique_sorted[0]
        
        for num in unique_sorted[1:]:
            if num == prev + 1:
                prev = num
            else:
                ranges.append(f"{start}-{prev}" if start != prev else str(start))
                start = prev = num
        
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        return ",".join(ranges)
    
    def _generate_file(self, spec: Dict[str, Any]) -> str:
        """Generate a file path."""
        scan_path = spec.get('path', '')
        pattern = spec.get('pattern', '')
        
        # Try to find real files
        if scan_path and os.path.isdir(scan_path):
            files = self._scan_files(scan_path, pattern)
            if files:
                return self.rng.choice(files)
        
        # Generate dummy file
        return self._create_dummy_file(scan_path, pattern)
    
    def _generate_directory(self, spec: Dict[str, Any]) -> str:
        """Generate a directory path."""
        scan_path = spec.get('path', '')
        pattern = spec.get('pattern', '')
        
        # Try to find real directories
        if scan_path and os.path.isdir(scan_path):
            dirs = self._scan_directories(scan_path, pattern)
            if dirs:
                return self.rng.choice(dirs)
        
        # Generate dummy directory
        return self._create_dummy_directory(scan_path, pattern)
    
    def _scan_files(self, scan_path: str, pattern: str) -> List[str]:
        """Scan directory for files matching pattern."""
        files = []
        try:
            for entry in os.listdir(scan_path):
                full_path = os.path.join(scan_path, entry)
                if os.path.isfile(full_path):
                    if not pattern or re.search(pattern, entry) or re.search(pattern, full_path):
                        files.append(full_path)
        except (PermissionError, OSError):
            pass
        return files
    
    def _scan_directories(self, scan_path: str, pattern: str, max_results: int = 100) -> List[str]:
        """Scan for directories matching pattern."""
        directories = []
        try:
            for root, dirs, _ in os.walk(scan_path):
                for d in dirs:
                    full_path = os.path.join(root, d)
                    if not pattern or re.search(pattern, d) or re.search(pattern, full_path):
                        directories.append(full_path)
                if len(directories) >= max_results:
                    break
        except (PermissionError, OSError):
            pass
        return directories
    
    def _create_dummy_file(self, base_path: str, pattern: str) -> str:
        """Create a dummy file path."""
        base_dir = base_path if base_path and os.path.isdir(base_path) else tempfile.gettempdir()
        
        if pattern and RSTR_AVAILABLE:
            filename = rstr.xeger(pattern)
        elif pattern:
            ext_match = re.search(r'\\\.([\w]+)(?:\$)?$', pattern)
            ext = ext_match.group(1) if ext_match else 'dat'
            filename = f"file_{self.rng.randint(1, 9999)}.{ext}"
        else:
            filename = f"file_{self.rng.randint(1, 9999)}.dat"
        
        full_path = os.path.join(base_dir, filename)
        
        if self.create_dummy_files:
            try:
                Path(full_path).touch(exist_ok=True)
            except (PermissionError, OSError):
                pass
        
        return full_path
    
    def _create_dummy_directory(self, base_path: str, pattern: str) -> str:
        """Create a dummy directory path."""
        base_dir = base_path if base_path and os.path.isdir(base_path) else tempfile.gettempdir()
        
        if pattern and RSTR_AVAILABLE:
            dirname = rstr.xeger(pattern)
        elif pattern:
            dirname = re.sub(r'[\^$.*+?{}\[\]\\|()]', '', pattern) or f"dir_{self.rng.randint(1, 9999)}"
        else:
            dirname = f"dir_{self.rng.randint(1, 9999)}"
        
        full_path = os.path.join(base_dir, dirname)
        
        if self.create_dummy_files:
            try:
                Path(full_path).mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError):
                pass
        
        return full_path
