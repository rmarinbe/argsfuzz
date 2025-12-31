#!/usr/bin/env python3
"""
Example custom generators for argsfuzz.

This file demonstrates how to create custom value generators that can be
loaded and used by argsfuzz. Each generator is a function that takes:
  - rng: A random.Random instance for reproducible randomness
  - params: A dictionary of parameters from the JSON config

To use these generators:
  python argsfuzz.py config.json --generators custom_generators.py

Then in your config.json, use:
  "value": {
    "kind": "custom",
    "generator": "my_generator_name",
    "params": { ... }
  }
"""

import random
from typing import Any, Dict


# Use the decorator to register generators
# (GeneratorRegistry and register_generator are injected by argsfuzz when loading)

@register_generator("ip_address")
def gen_ip_address(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate random IPv4 addresses.
    
    Params:
        private_only: Only generate private IPs (default: False)
        include_localhost: Include 127.x.x.x range (default: True)
    """
    private_only = params.get('private_only', False)
    include_localhost = params.get('include_localhost', True)
    
    if private_only:
        # Generate only private ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x
        range_type = rng.randint(0, 3 if include_localhost else 2)
        if range_type == 0:
            return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        elif range_type == 1:
            return f"172.{rng.randint(16, 31)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        elif range_type == 2:
            return f"192.168.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        else:
            return f"127.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    else:
        # Any random IP
        return f"{rng.randint(1, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


@register_generator("port_range")
def gen_port_range(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate port number or range like '8080' or '8080-8090'.
    
    Params:
        min_port: Minimum port (default: 1024)
        max_port: Maximum port (default: 65535)
        allow_range: Allow port ranges (default: True)
        range_probability: Probability of generating a range (default: 0.3)
    """
    min_port = params.get('min_port', 1024)
    max_port = params.get('max_port', 65535)
    allow_range = params.get('allow_range', True)
    range_probability = params.get('range_probability', 0.3)
    
    start_port = rng.randint(min_port, max_port - 10)
    
    if allow_range and rng.random() < range_probability:
        end_port = rng.randint(start_port + 1, min(start_port + 100, max_port))
        return f"{start_port}-{end_port}"
    else:
        return str(start_port)


@register_generator("uuid")
def gen_uuid(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate a random UUID-like string.
    
    Params:
        uppercase: Use uppercase hex (default: False)
        format: 'standard' (with dashes) or 'compact' (no dashes) (default: 'standard')
    """
    uppercase = params.get('uppercase', False)
    fmt = params.get('format', 'standard')
    
    hex_chars = '0123456789ABCDEF' if uppercase else '0123456789abcdef'
    
    parts = [
        ''.join(rng.choices(hex_chars, k=8)),
        ''.join(rng.choices(hex_chars, k=4)),
        '4' + ''.join(rng.choices(hex_chars, k=3)),  # Version 4
        rng.choice('89ab' if not uppercase else '89AB') + ''.join(rng.choices(hex_chars, k=3)),
        ''.join(rng.choices(hex_chars, k=12))
    ]
    
    if fmt == 'compact':
        return ''.join(parts)
    return '-'.join(parts)


@register_generator("date_time")
def gen_date_time(rng: random.Random, params: Dict[str, Any]) -> str:
    """Generate date/time strings in various formats.
    
    Params:
        format: 'iso', 'date', 'time', 'epoch' (default: 'iso')
        year_min: Minimum year (default: 2020)
        year_max: Maximum year (default: 2025)
    """
    fmt = params.get('format', 'iso')
    year_min = params.get('year_min', 2020)
    year_max = params.get('year_max', 2025)
    
    year = rng.randint(year_min, year_max)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)  # Safe for all months
    hour = rng.randint(0, 23)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    
    if fmt == 'iso':
        return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
    elif fmt == 'date':
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif fmt == 'time':
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    elif fmt == 'epoch':
        # Approximate epoch calculation
        import calendar
        from datetime import datetime
        try:
            dt = datetime(year, month, day, hour, minute, second)
            return str(int(dt.timestamp()))
        except:
            return str(rng.randint(1577836800, 1735689600))  # 2020-2025 range
    else:
        return f"{year:04d}-{month:02d}-{day:02d}"
