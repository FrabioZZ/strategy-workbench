def unique_strategy_name(name: str, occupied: set[str], max_length: int) -> str:
    """Reserve a name, preserving its base spelling and room for the suffix."""
    base = name.strip()
    candidate = base[:max_length].rstrip()
    number = 2
    while candidate.casefold() in occupied:
        suffix = f' ({number})'
        candidate = base[:max_length - len(suffix)].rstrip() + suffix
        number += 1
    occupied.add(candidate.casefold())
    return candidate
