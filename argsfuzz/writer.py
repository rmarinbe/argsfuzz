"""Corpus output writing."""

from pathlib import Path

from .config import OutputFormat


class CorpusWriter:
    """Writes generated test cases to output."""
    
    def __init__(self, output_path: Path, output_format: OutputFormat):
        self.output_path = output_path
        self.output_format = output_format
        self.generation_count = 0
    
    def initialize(self) -> None:
        """Initialize output destination."""
        if self.output_format == OutputFormat.DIRECTORY:
            self.output_path.mkdir(parents=True, exist_ok=True)
        else:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            if self.output_path.exists():
                self.output_path.unlink()
    
    def write(self, command_line: str) -> None:
        """Write a single test case."""
        try:
            if self.output_format == OutputFormat.DIRECTORY:
                file_path = self.output_path / f"test_{self.generation_count:06d}.txt"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(command_line + '\n')
            else:
                with open(self.output_path, 'a', encoding='utf-8') as f:
                    f.write(command_line + '\n')
            
            self.generation_count += 1
        except IOError as e:
            raise IOError(f"Failed to write test case {self.generation_count}: {e}")
    
    def finalize(self) -> int:
        """Finalize output and return count."""
        return self.generation_count
