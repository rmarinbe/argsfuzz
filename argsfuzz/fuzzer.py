"""Main fuzzing generator orchestrator."""

import random
from pathlib import Path
from typing import Dict, List

from .config import GenerationConfig
from .schema import SchemaValidator
from .solver import ConstraintSolver
from .constraints import ConstraintValidator
from .generator import Generator
from .mutator import Mutator
from .writer import CorpusWriter
from .registry import GeneratorRegistry


class FuzzGenerator:
    """Main fuzzing generator orchestrator."""
    
    def __init__(self, config_path: Path, schema_path: Path, gen_config: GenerationConfig):
        self.config_path = config_path
        self.schema_path = schema_path
        self.gen_config = gen_config
        self.rng = random.Random(gen_config.seed)
        self.verbose = gen_config.verbose
        
        # Pipeline components (initialized in run())
        self.validator = SchemaValidator(schema_path)
        self.config = None
        self.solver = None
        self.constraint_validator = None
        self.generator = None
        self.mutator = None
        self.writer = None
    
    def run(self) -> int:
        """Run the complete generation pipeline."""
        self._log("[1/7] Loading and validating schema...")
        self.config = self.validator.validate(self.config_path)
        tool_name = self.config.get('metadata', {}).get('tool_name', 'tool')
        self._log(f"      Tool: {tool_name}")
        
        self._log("[2/7] Loading custom generators...")
        loaded_count = 0
        if self.gen_config.generators_file:
            loaded_count = GeneratorRegistry.load_from_file(self.gen_config.generators_file)
        self._log(f"      Built-in: {len(GeneratorRegistry.list_generators()) - loaded_count}")
        self._log(f"      Custom: {loaded_count}")
        
        self._log("[3/7] Building constraint solver...")
        self.solver = ConstraintSolver(self.config, self.rng)
        self.constraint_validator = ConstraintValidator(self.solver, self.rng)
        self._log(f"      Arguments: {len(self.solver.arguments)}")
        self._log(f"      Subcommands: {len(self.solver.subcommands)}")
        self._log(f"      Rules: {len(self.solver.rules)}")
        
        self._log("[4/7] Initializing generator...")
        self.generator = Generator(self.config, self.solver, self.rng, 
                                   self.gen_config.create_dummy_files)
        
        self._log("[5/7] Initializing mutator...")
        self.mutator = Mutator(self.config, self.solver, self.rng)
        
        self._log("[6/7] Initializing corpus writer...")
        self.writer = CorpusWriter(self.gen_config.output_path, self.gen_config.output_format)
        self.writer.initialize()
        
        self._log("[7/7] Generating test cases...")
        self._log(f"      Target: {self.gen_config.num_generations} generations")
        self._log(f"      Invalid ratio: {self.gen_config.invalid_ratio:.1%}")
        
        valid_count, invalid_count = self._generate_all()
        total = self.writer.finalize()
        
        self._log(f"\nGeneration complete!")
        self._log(f"  Total: {total} test cases")
        self._log(f"  Valid: {valid_count}")
        self._log(f"  Invalid: {invalid_count}")
        self._log(f"  Output: {self.gen_config.output_path}")
        self._log(f"  Format: {self.gen_config.output_format.value}")
        
        return total
    
    def _generate_all(self) -> tuple:
        """Generate all test cases."""
        valid_count = 0
        invalid_count = 0
        
        for gen_idx in range(self.gen_config.num_generations):
            should_be_invalid = self.rng.random() < self.gen_config.invalid_ratio
            
            # Generate combination
            subcommand_name, selected_args, active_positional, _ = self.generator.generate_combination()
            
            # Adjust to target count (also generates values for conditional deps)
            selected_args, generated_values = self._adjust_arg_count(selected_args, subcommand_name)
            
            # Build command line (reuses pre-generated values)
            cmd_parts = self._build_command(subcommand_name, selected_args, active_positional, generated_values)
            
            # Apply mutation if needed
            cmd_parts = self.mutator.mutate(cmd_parts, should_be_invalid)
            
            # Shuffle for variety
            cmd_parts = self._shuffle_command(cmd_parts)
            
            # Write output
            self.writer.write(' '.join(cmd_parts))
            
            if should_be_invalid:
                invalid_count += 1
            else:
                valid_count += 1
            
            if self.verbose and (gen_idx + 1) % 10 == 0:
                print(f"      Progress: {gen_idx + 1}/{self.gen_config.num_generations}", end='\r')
        
        return valid_count, invalid_count
    
    def _adjust_arg_count(self, selected_args: List[str], subcommand_name: str) -> tuple:
        """Adjust argument count to target range.
        
        Returns:
            Tuple of (adjusted args list, generated values dict)
        """
        max_args = (self.gen_config.max_args if self.gen_config.max_args is not None 
                   else self.config.get('generation', {}).get('max_args', 20))
        target_count = self.rng.randint(self.gen_config.min_args, max_args)
        
        # Get active arguments context
        if subcommand_name:
            active_arguments = self.solver.subcommands[subcommand_name].arguments
        else:
            active_arguments = self.solver.arguments
        
        # Trim or add
        if len(selected_args) > target_count:
            selected_args = self.generator._trim_to_target_count(selected_args, target_count, active_arguments)
        elif len(selected_args) < target_count:
            selected_args = self.generator._add_to_target_count(selected_args, target_count)
        
        # Pre-generate values for conditional dependency checking
        generated_values = {}
        for arg_name in selected_args:
            if arg_name in active_arguments:
                arg = active_arguments[arg_name]
                value = self.generator.generate_value(arg.value_spec, arg.name, arg.generator, arg.params)
                if value is not None:
                    generated_values[arg_name] = value
        
        # Pass values to constraint validator for conditional deps
        self.constraint_validator.set_generated_values(generated_values)
        
        # Ensure constraints are valid (single unified call!)
        selected_set = self.constraint_validator.ensure_valid(set(selected_args), active_arguments)
        
        # Remove values for args that were removed by conditional deps
        generated_values = {k: v for k, v in generated_values.items() if k in selected_set}
        
        return sorted(selected_set), generated_values
    
    def _build_command(self, subcommand_name: str, selected_args: List[str], 
                       active_positional, generated_values: dict = None) -> List[str]:
        """Build command line parts.
        
        Args:
            subcommand_name: Name of subcommand or None
            selected_args: List of selected argument names
            active_positional: List of positional argument configs
            generated_values: Pre-generated values dict (for conditional deps)
        """
        cmd_parts = []
        if generated_values is None:
            generated_values = {}
        
        if subcommand_name:
            active_arguments = self.solver.subcommands[subcommand_name].arguments
            global_arg_names = self.config.get('global_arguments', [])
            global_args = [a for a in selected_args 
                          if a in global_arg_names and a in self.solver.arguments]
            
            # Add global arguments first
            for arg_name in global_args:
                cmd_parts.extend(self._format_arg(self.solver.arguments[arg_name], generated_values))
            
            cmd_parts.append(subcommand_name)
            selected_args = [a for a in selected_args if a not in global_args]
        else:
            active_arguments = self.solver.arguments
        
        # Add flags and options
        for arg_name in selected_args:
            if arg_name not in active_arguments:
                continue
            arg = active_arguments[arg_name]
            
            repeat_count = self._get_repeat_count(arg)
            for _ in range(repeat_count):
                cmd_parts.extend(self._format_arg(arg, generated_values))
        
        # Add positional arguments
        for pos_arg in active_positional:
            if pos_arg.required or self.rng.random() < 0.5:
                count = self.rng.randint(1, 3) if pos_arg.variadic else 1
                for _ in range(count):
                    value = self.generator.generate_value(pos_arg.value_spec)
                    if value:
                        cmd_parts.append(value)
        
        return cmd_parts
    
    def _format_arg(self, arg, generated_values: dict = None) -> List[str]:
        """Format a single argument.
        
        Uses cached value if available, otherwise generates new one.
        """
        if generated_values is None:
            generated_values = {}
        
        # Use cached value if available
        if arg.name in generated_values:
            value = generated_values[arg.name]
        else:
            value = self.generator.generate_value(arg.value_spec, arg.name, arg.generator, arg.params)
        return self.generator.format_argument(arg, value)
    
    def _get_repeat_count(self, arg) -> int:
        """Get repeat count for an argument."""
        if not arg.repeat_flag:
            return 1
        
        if self.rng.random() < arg.repeat_flag.get('probability', 1.0):
            min_occurs = arg.repeat_flag.get('min_occurs', 1)
            max_occurs = arg.repeat_flag.get('max_occurs', 1)
            return self.rng.randint(min_occurs, max_occurs)
        return 1
    
    def _shuffle_command(self, cmd_parts: List[str]) -> List[str]:
        """Shuffle flag groups while keeping positional args at end."""
        idx = 0
        flag_groups = []
        
        while idx < len(cmd_parts):
            if cmd_parts[idx].startswith('-'):
                if '=' in cmd_parts[idx]:
                    flag_groups.append([cmd_parts[idx]])
                    idx += 1
                elif idx + 1 < len(cmd_parts) and not cmd_parts[idx + 1].startswith('-'):
                    flag_groups.append([cmd_parts[idx], cmd_parts[idx + 1]])
                    idx += 2
                else:
                    flag_groups.append([cmd_parts[idx]])
                    idx += 1
            else:
                break
        
        positional = cmd_parts[idx:]
        self.rng.shuffle(flag_groups)
        
        return [item for group in flag_groups for item in group] + positional
    
    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(message)
