"""Argument combination generation."""

import random
from typing import Dict, List, Set, Tuple, Optional, Any

from .config import Argument, PositionalArg
from .solver import ConstraintSolver
from .constraints import ConstraintValidator
from .values import ValueGenerator


class Generator:
    """Generates valid command-line argument combinations."""
    
    def __init__(self, config: Dict[str, Any], solver: ConstraintSolver, 
                 rng: random.Random, create_dummy_files: bool = False,
                 min_args_override: Optional[int] = None,
                 max_args_override: Optional[int] = None):
        self.config = config
        self.solver = solver
        self.rng = rng
        self.generation_params = config.get('generation', {})
        self.min_args_override = min_args_override  # Command-line override
        self.max_args_override = max_args_override  # Command-line override
        self.constraint_validator = ConstraintValidator(solver, rng)
        self.value_generator = ValueGenerator(rng, create_dummy_files)
    
    def generate_combination(self) -> Tuple[Optional[str], List[str], List[PositionalArg], int]:
        """Generate a single valid argument combination.
        
        Returns:
            Tuple of (subcommand_name, selected argument names, positional args, attempts)
        """
        subcommand_name, active_arguments, active_positional = self._select_context()
        
        # Start with required arguments
        selected = {name for name, arg in active_arguments.items() if arg.required}
        
        # Add arguments based on probability
        for name, arg in active_arguments.items():
            if name not in selected and self.rng.random() < arg.probability:
                selected.add(name)
        
        # Ensure constraints are satisfied (skip conditional deps - they'll be checked later with values)
        if subcommand_name is None:
            selected = self.constraint_validator.ensure_valid(selected, active_arguments, 
                                                              skip_conditional_deps=True)
        
        # Pick random target count between min_args and max_args for this combination
        min_args = self.min_args_override if self.min_args_override is not None else self.generation_params.get('min_args', 1)
        max_args = self.max_args_override if self.max_args_override is not None else self.generation_params.get('max_args', 20)
        target_count = self.rng.randint(min_args, max_args)
        
        selected_list = sorted(selected)
        if len(selected_list) > target_count:
            selected_list = self._trim_to_target_count(selected_list, target_count, active_arguments)
        elif len(selected_list) < target_count:
            selected_list = self.add_to_target_count(selected_list, target_count)
        
        return subcommand_name, selected_list, active_positional, 1
    
    def _select_context(self) -> Tuple[Optional[str], Dict[str, Argument], List[PositionalArg]]:
        """Select subcommand context if applicable."""
        if self.solver.subcommands and self.rng.random() < 0.7:
            subcommands = list(self.solver.subcommands.values())
            weights = [sc.probability for sc in subcommands]
            if sum(weights) > 0:
                subcommand = self.rng.choices(subcommands, weights=weights, k=1)[0]
                return subcommand.name, subcommand.arguments, subcommand.positional
        
        return None, self.solver.arguments, self.solver.positional
    
    def _trim_to_target_count(self, selected_args: List[str], target_count: int,
                               arguments: Dict[str, Argument]) -> List[str]:
        """Trim argument list while preserving constraints."""
        if len(selected_args) <= target_count:
            return selected_args
        
        must_keep = self.constraint_validator.get_must_keep_args(selected_args, arguments)
        can_remove = [a for a in selected_args if a not in must_keep]
        
        if len(must_keep) <= target_count:
            to_remove = len(selected_args) - target_count
            if to_remove > 0 and can_remove:
                remove_these = self.rng.sample(can_remove, min(to_remove, len(can_remove)))
                return sorted([a for a in selected_args if a not in remove_these])
            return selected_args
        
        return sorted(must_keep)
    
    def add_to_target_count(self, selected_args: List[str], target_count: int) -> List[str]:
        """Add arguments to reach target count while respecting rules and probabilities."""
        if len(selected_args) >= target_count:
            return selected_args
        
        available = [a for a in self.solver.arguments.keys() 
                    if a not in selected_args and self.solver.arguments[a].probability > 0]
        if not available:
            return selected_args
        
        current = set(selected_args)
        
        # Use weighted random selection based on probabilities
        # This avoids bias and respects probability distribution
        while len(current) < target_count and available:
            # Get probabilities for all available arguments
            weights = [self.solver.arguments[name].probability for name in available]
            
            # Weighted random selection
            selected = self.rng.choices(available, weights=weights, k=1)[0]
            
            # Check if adding this argument violates any rules
            if not self.constraint_validator.check_rule_violation(current, selected):
                current.add(selected)
            
            # Remove from available pool (don't try same arg twice)
            available.remove(selected)
        
        return sorted(current)
    
    def generate_value(self, value_spec: Dict[str, Any], arg_name: str = "",
                       generator: Optional[str] = None,
                       params: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generate a value for an argument."""
        return self.value_generator.generate(value_spec, arg_name, generator, params)
    
    def format_argument(self, arg: Argument, value: Optional[str]) -> List[str]:
        """Format an argument with its value."""
        flag = self.rng.choice(arg.flags)
        
        if value is None:
            return [flag]
        
        equals_prob = self.generation_params.get('equals_form_probability', 0.0)
        use_equals = flag.startswith('--') and self.rng.random() < equals_prob
        
        if use_equals:
            return [f"{flag}={value}"]
        return [flag, value]
    
    # Backward compatibility aliases
    def _add_to_target_count(self, selected_args: List[str], target_count: int) -> List[str]:
        """Backward-compatible add method."""
        return self.add_to_target_count(selected_args, target_count)
    
    def _fix_rules(self, selected: Set[str]) -> Set[str]:
        """Backward-compatible rule fixing."""
        return self.constraint_validator._fix_rules(selected)
    
    def _resolve_dependencies_for_args(self, arg_name: str, selected: Set[str],
                                        arguments: Dict[str, Argument]) -> Set[str]:
        """Backward-compatible dependency resolution."""
        return self.constraint_validator._resolve_dependencies_for_arg(arg_name, selected, arguments)
