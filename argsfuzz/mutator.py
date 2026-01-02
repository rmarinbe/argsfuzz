"""Mutation strategies for generating invalid test cases."""

import random
from typing import Dict, List, Any

from .solver import ConstraintSolver


class Mutator:
    """Mutates valid combinations to create invalid test cases."""
    
    # Shell-safe characters for generating flags
    FLAG_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_'
    # Extended ASCII for value mutations
    VALUE_CHARS = ''.join(chr(i) for i in range(32, 256))
    
    def __init__(self, config: Dict[str, Any], solver: ConstraintSolver, rng: random.Random):
        self.config = config
        self.solver = solver
        self.rng = rng
    
    @property
    def syntax(self) -> Dict[str, Any]:
        return self.config.get('syntax', {})
    
    def mutate(self, args: List[str], target_invalid: bool) -> List[str]:
        """Mutate argument list if targeting invalid output."""
        if not target_invalid:
            return args
        
        strategies = [
            self._add_invalid_flag,
            self._duplicate_flag,
            self._remove_required_arg,
            self._add_conflicting_args,
            self._mutate_value,
        ]
        
        strategy = self.rng.choice(strategies)
        return strategy(args.copy())
    
    def _add_invalid_flag(self, args: List[str]) -> List[str]:
        """Add a completely invalid flag."""
        if args and self.rng.random() < 0.5:
            flags = [a for a in args if a.startswith('-')]
            if flags:
                mutated = self._mutate_string(self.rng.choice(flags), self.FLAG_CHARS)
                args.insert(self.rng.randint(0, len(args)), mutated)
                return args
        
        if self.rng.random() < 0.5:
            char = self.rng.choice(self.FLAG_CHARS)
            invalid_flag = f'-{char}'
        else:
            length = self.rng.randint(3, 15)
            chars = ''.join(self.rng.choice(self.FLAG_CHARS) for _ in range(length))
            invalid_flag = f'--{chars}'
        
        args.insert(self.rng.randint(0, len(args)), invalid_flag)
        return args
    
    def _duplicate_flag(self, args: List[str]) -> List[str]:
        """Duplicate a flag (invalid if duplicates not allowed)."""
        if not self.syntax.get('allow_duplicates', False):
            flags = [a for a in args if a.startswith('-')]
            if flags:
                dup_flag = self.rng.choice(flags)
                args.insert(self.rng.randint(0, len(args)), dup_flag)
        return args
    
    def _remove_required_arg(self, args: List[str]) -> List[str]:
        """Remove a required argument."""
        required_args = [name for name, arg in self.solver.arguments.items() if arg.required]
        if required_args:
            req_arg = self.solver.arguments[self.rng.choice(required_args)]
            for flag in req_arg.flags:
                if flag in args:
                    idx = args.index(flag)
                    args.pop(idx)
                    if idx < len(args) and not args[idx].startswith('-'):
                        args.pop(idx)
                    break
        return args
    
    def _add_conflicting_args(self, args: List[str]) -> List[str]:
        """Add conflicting arguments."""
        for rule in self.solver.rules:
            if rule.rule_type == 'mutually_exclusive' and len(rule.arguments) >= 2:
                expanded = list(self.solver.expand_groups(rule.arguments))
                if len(expanded) >= 2:
                    pair = self.rng.sample(expanded, 2)
                    arg1 = self.solver.arguments.get(pair[0])
                    arg2 = self.solver.arguments.get(pair[1])
                    if arg1 and arg2:
                        args.extend([self.rng.choice(arg1.flags), self.rng.choice(arg2.flags)])
                        break
        return args
    
    def _mutate_value(self, args: List[str]) -> List[str]:
        """Mutate a value to be invalid."""
        if args and self.rng.random() < 0.5:
            flags = [i for i, arg in enumerate(args) if arg.startswith('-')]
            if flags:
                idx = self.rng.choice(flags)
                args[idx] = self._mutate_string(args[idx], self.FLAG_CHARS)
        else:
            for i, arg in enumerate(args):
                if arg.startswith('-') and i + 1 < len(args) and not args[i + 1].startswith('-'):
                    args[i + 1] = self._mutate_string(args[i + 1], self.VALUE_CHARS)
                    break
        return args
    
    def _mutate_string(self, s: str, chars: str) -> str:
        """Randomly add, remove, or replace a character."""
        if not s:
            return self.rng.choice(chars)
        
        mutation = self.rng.choice(['add', 'remove', 'replace'])
        
        if mutation == 'add':
            pos = self.rng.randint(0, len(s))
            return s[:pos] + self.rng.choice(chars) + s[pos:]
        elif mutation == 'remove' and len(s) > 1:
            pos = self.rng.randint(0, len(s) - 1)
            return s[:pos] + s[pos + 1:]
        else:
            pos = self.rng.randint(0, len(s) - 1)
            return s[:pos] + self.rng.choice(chars) + s[pos + 1:]
