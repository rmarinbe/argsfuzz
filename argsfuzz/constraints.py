"""Constraint validation and dependency resolution.

This module provides a unified interface for ensuring argument combinations
are valid according to rules and dependencies.
"""

import random
from typing import Dict, List, Optional, Set, Tuple

from .config import Argument
from .solver import ConstraintSolver


class ConstraintValidator:
    """Validates and fixes argument constraints.
    
    Provides a single entry point for ensuring argument combinations
    satisfy all rules and dependencies.
    """
    
    def __init__(self, solver: ConstraintSolver, rng: random.Random):
        self.solver = solver
        self.rng = rng
        self.generated_values: Dict[str, str] = {}  # Track values for conditional deps
    
    def set_generated_values(self, values: Dict[str, str]) -> None:
        """Set the generated values for conditional dependency checking."""
        self.generated_values = values
    
    def ensure_valid(self, selected: Set[str], arguments: Dict[str, Argument], 
                      skip_conditional_deps: bool = False) -> Set[str]:
        """Ensure argument set satisfies all constraints.
        
        This is the single source of truth for constraint validation.
        It applies rules and resolves dependencies iteratively until stable.
        
        Args:
            selected: Set of selected argument names
            arguments: Dictionary of available arguments
            skip_conditional_deps: If True, skip value-conditional dependency checks.
                                   Use this before values are generated.
            
        Returns:
            Valid set of argument names
        """
        # Fix rules first
        selected = self._fix_rules(selected)
        
        # Resolve dependencies iteratively
        selected = self._resolve_all_dependencies(selected, arguments, skip_conditional_deps)
        
        return selected
    
    def _fix_rules(self, selected: Set[str]) -> Set[str]:
        """Fix rule violations deterministically."""
        selected = selected.copy()
        
        for rule_info in self.solver._expanded_rules:
            rule = rule_info['rule']
            expanded_args = rule_info['expanded_args']
            selected_from_rule = expanded_args & selected
            
            if rule.rule_type == 'mutually_exclusive' and len(selected_from_rule) > 1:
                to_keep = self.rng.choice(sorted(selected_from_rule))
                for arg in selected_from_rule:
                    if arg != to_keep:
                        selected.discard(arg)
            
            elif rule.rule_type == 'one_of_required' and len(selected_from_rule) == 0:
                available = [arg for arg in expanded_args 
                            if arg in self.solver.arguments 
                            and self.solver.arguments[arg].probability > 0]
                if available:
                    selected.add(self.rng.choice(sorted(available)))
            
            elif rule.rule_type == 'all_or_none':
                if 0 < len(selected_from_rule) < len(expanded_args):
                    available = [arg for arg in expanded_args 
                                if arg in self.solver.arguments 
                                and self.solver.arguments[arg].probability > 0]
                    if available:
                        selected.update(available)
        
        return selected
    
    def _resolve_all_dependencies(self, selected: Set[str], 
                                   arguments: Dict[str, Argument],
                                   skip_conditional_deps: bool = False) -> Set[str]:
        """Resolve dependencies iteratively until stable.
        
        Also removes arguments whose conditional dependencies are not satisfied.
        
        Args:
            selected: Set of selected argument names
            arguments: Dictionary of available arguments  
            skip_conditional_deps: If True, skip value-conditional checks
        """
        selected = selected.copy()
        
        changed = True
        while changed:
            changed = False
            to_remove = set()
            new_deps = set()
            
            for name in sorted(selected):
                deps = self._resolve_dependencies_for_arg(name, selected, arguments, skip_conditional_deps)
                
                # Handle conditional dependency failure
                if '__REMOVE_SELF__' in deps:
                    to_remove.add(name)
                    changed = True
                else:
                    new_deps.update(deps - selected)
            
            # Remove args with unsatisfied conditional deps
            if to_remove:
                selected -= to_remove
            
            # Add new dependencies
            if new_deps:
                selected.update(new_deps)
                changed = True
        
        return selected
    
    def _parse_conditional_dep(self, dep: str) -> Tuple[str, Optional[List[str]]]:
        """Parse a dependency string, handling value conditions.
        
        Formats:
            "arg_name" - simple dependency
            "arg_name=val1,val2" - conditional (only if arg_name has one of these values)
        
        Returns:
            (arg_name, allowed_values or None)
        """
        if '=' in dep:
            arg_name, values_str = dep.split('=', 1)
            allowed_values = [v.strip() for v in values_str.split(',')]
            return arg_name, allowed_values
        return dep, None
    
    def _is_conditional_dep_satisfied(self, arg_name: str, allowed_values: List[str]) -> bool:
        """Check if a conditional dependency is satisfied.
        
        Returns True if the arg's generated value matches one of the allowed values.
        """
        if arg_name not in self.generated_values:
            # No value generated yet - can't be satisfied
            return False
        
        generated_value = self.generated_values[arg_name]
        return generated_value in allowed_values
    
    def _resolve_dependencies_for_arg(self, arg_name: str, selected: Set[str],
                                       arguments: Dict[str, Argument],
                                       skip_conditional_deps: bool = False) -> Set[str]:
        """Resolve dependencies for a single argument.
        
        Args:
            arg_name: Name of argument to check
            selected: Current set of selected arguments
            arguments: Available arguments
            skip_conditional_deps: If True, skip value-conditional checks
        """
        if arg_name not in arguments:
            return set()
        
        arg = arguments[arg_name]
        deps = set()
        
        for dep in arg.depends_on:
            dep_arg, allowed_values = self._parse_conditional_dep(dep)
            
            # Handle conditional dependencies (arg=val1,val2)
            if allowed_values is not None:
                if skip_conditional_deps:
                    # Don't check value conditions yet, just ensure the base arg is present
                    if dep_arg in arguments:
                        deps.add(dep_arg)
                    continue
                    
                if not self._is_conditional_dep_satisfied(dep_arg, allowed_values):
                    # Condition not met - this arg should be removed
                    # Return special marker that will cause this arg to be excluded
                    return {'__REMOVE_SELF__'}
                continue  # Condition met, no need to add as dependency
            
            if dep_arg in self.solver.groups:
                # Need at least one from the group
                group_members = [m for m in self.solver.groups[dep_arg] if m in selected]
                if not group_members:
                    available = [m for m in self.solver.groups[dep_arg] if m in arguments]
                    if available:
                        with_prob = [m for m in available if arguments[m].probability > 0]
                        deps.add(self.rng.choice(with_prob if with_prob else available))
            else:
                # Direct dependency
                if dep_arg in arguments:
                    deps.add(dep_arg)
        
        return deps
    
    def check_rule_violation(self, selected: Set[str], arg_to_add: str) -> bool:
        """Check if adding an argument would violate any rules.
        
        Returns True if violation would occur.
        """
        test_set = selected | {arg_to_add}
        
        for rule_info in self.solver._expanded_rules:
            rule = rule_info['rule']
            expanded_args = rule_info['expanded_args']
            
            if rule.rule_type == 'mutually_exclusive':
                if len(expanded_args & test_set) > 1:
                    return True
        
        return False
    
    def get_must_keep_args(self, selected_args: List[str], 
                           arguments: Dict[str, Argument]) -> Set[str]:
        """Identify arguments that must be kept when trimming.
        
        Returns set of argument names that cannot be removed.
        """
        must_keep = set()
        
        for arg_name in selected_args:
            arg = arguments.get(arg_name)
            if not arg:
                continue
                
            # Required args must stay
            if arg.required:
                must_keep.add(arg_name)
            
            # Args with dependencies - keep both dependent and dependencies
            if arg.depends_on:
                must_keep.add(arg_name)
                for dep in arg.depends_on:
                    if dep in selected_args:
                        must_keep.add(dep)
                    elif dep in self.solver.groups:
                        for member in self.solver.groups[dep]:
                            if member in selected_args:
                                must_keep.add(member)
            
            # Check if other args depend on this one
            for other_name in selected_args:
                other_arg = arguments.get(other_name)
                if other_arg and arg_name in other_arg.depends_on:
                    must_keep.add(arg_name)
        
        # For one_of_required rules, keep at least one
        for rule_info in self.solver._expanded_rules:
            rule = rule_info['rule']
            if rule.rule_type == 'one_of_required':
                expanded_args = rule_info['expanded_args']
                rule_args_selected = [a for a in expanded_args if a in selected_args]
                if rule_args_selected:
                    must_keep.add(self.rng.choice(sorted(rule_args_selected)))
        
        return must_keep
