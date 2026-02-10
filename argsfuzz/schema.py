"""Schema validation for fuzzing configurations."""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from jsonschema import validate, ValidationError


class SchemaValidator:
    """Validates fuzzing configuration against the schema"""
    
    def __init__(self, schema_path: Optional[Path] = None, schema_data: Optional[dict] = None):
        if schema_data is not None:
            self.schema = schema_data
        elif schema_path is not None:
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            raise ValueError("Either schema_path or schema_data must be provided")
    
    def validate(self, config_path: Path) -> Dict[str, Any]:
        """Validate configuration and return parsed data"""
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        try:
            validate(instance=config, schema=self.schema)
        except ValidationError as e:
            raise ValueError(f"Invalid configuration: {e.message}")
        
        return config
