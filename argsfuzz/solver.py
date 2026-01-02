"""Constraint solver for argument combinations."""

import random
from typing import Dict, List, Any

from .config import Argument, PositionalArg, Rule, Subcommand


class ConstraintSolver:
    """Solves constraints and determines valid argument combinations"""
    
    def __init__(self, config: Dict[str, Any], rng: random.Random):
        self.config = config
        self.rng = rng
        self.arguments = self._parse_arguments()
        self.positional = self._parse_positional()
        self.subcommands = self._parse_subcommands()
        self.rules = self._parse_rules()
        self.groups = self._build_groups()
        # Pre-compute expanded rule arguments for efficiency
        self._expanded_rules = self._precompute_expanded_rules()
    
    def _parse_arguments(self) -> Dict[str, Argument]:
        """Parse arguments from config"""
        args = {}
        for arg_spec in self.config.get('arguments', []):
            arg = Argument(
                name=arg_spec['name'],
                flags=arg_spec['flags'],
                description=arg_spec.get('description', ''),
                probability=arg_spec.get('probability', 0.5),
                group=arg_spec.get('group'),
                depends_on=arg_spec.get('depends_on', []),
                required=arg_spec.get('required', False),
                repeat_flag=arg_spec.get('repeat_flag'),
                value_spec=arg_spec['value'],
                generator=arg_spec.get('generator'),
                params=arg_spec.get('params')
            )
            args[arg.name] = arg
        return args
    
    def _parse_positional(self) -> List[PositionalArg]:
        """Parse positional arguments"""
        pos_args = []
        for pos_spec in self.config.get('positional', []):
            pos_arg = PositionalArg(
                name=pos_spec['name'],
                position=pos_spec['position'],
                required=pos_spec.get('required', False),
                variadic=pos_spec.get('variadic', False),
                value_spec=pos_spec['value']
            )
            pos_args.append(pos_arg)
        return sorted(pos_args, key=lambda x: x.position)
    
    def _parse_subcommands(self) -> Dict[str, Subcommand]:
        """Parse subcommands"""
        subcommands = {}
        for sub_spec in self.config.get('subcommands', []):
            sub_args = {}
            for arg_spec in sub_spec.get('arguments', []):
                arg = Argument(
                    name=arg_spec['name'],
                    flags=arg_spec['flags'],
                    description=arg_spec.get('description', ''),
                    probability=arg_spec.get('probability', 0.5),
                    group=arg_spec.get('group'),
                    depends_on=arg_spec.get('depends_on', []),
                    required=arg_spec.get('required', False),
                    repeat_flag=arg_spec.get('repeat_flag'),
                    value_spec=arg_spec['value'],
                    generator=arg_spec.get('generator'),
                    params=arg_spec.get('params')
                )
                sub_args[arg.name] = arg
            
            sub_pos = []
            for pos_spec in sub_spec.get('positional', []):
                pos_arg = PositionalArg(
                    name=pos_spec['name'],
                    position=pos_spec['position'],
                    required=pos_spec.get('required', False),
                    variadic=pos_spec.get('variadic', False),
                    value_spec=pos_spec['value']
                )
                sub_pos.append(pos_arg)
            sub_pos = sorted(sub_pos, key=lambda x: x.position)
            
            subcommand = Subcommand(
                name=sub_spec['name'],
                description=sub_spec.get('description', ''),
                aliases=sub_spec.get('aliases', []),
                probability=sub_spec.get('probability', 0.5),
                arguments=sub_args,
                positional=sub_pos
            )
            subcommands[subcommand.name] = subcommand
        
        return subcommands
    
    def _parse_rules(self) -> List[Rule]:
        """Parse validation rules"""
        rules = []
        for rule_spec in self.config.get('rules', []):
            rule = Rule(
                rule_type=rule_spec['type'],
                arguments=rule_spec['arguments'],
                description=rule_spec.get('description')
            )
            rules.append(rule)
        return rules
    
    def _build_groups(self) -> Dict[str, List[str]]:
        """Build group mappings"""
        groups = {}
        for name, arg in self.arguments.items():
            if arg.group:
                if arg.group not in groups:
                    groups[arg.group] = []
                groups[arg.group].append(name)
        return groups
    
    def _precompute_expanded_rules(self) -> List[Dict[str, Any]]:
        """Pre-compute expanded arguments for each rule."""
        expanded_rules = []
        for rule in self.rules:
            expanded_args = set()
            for arg in rule.arguments:
                if arg in self.groups:
                    expanded_args.update(self.groups[arg])
                else:
                    expanded_args.add(arg)
            expanded_rules.append({
                'rule': rule,
                'expanded_args': expanded_args
            })
        return expanded_rules
    
    def expand_groups(self, arg_refs: List[str]) -> set:
        """Expand group references to actual argument names."""
        expanded = set()
        for arg_ref in arg_refs:
            if arg_ref in self.groups:
                expanded.update(self.groups[arg_ref])
            else:
                expanded.add(arg_ref)
        return expanded
