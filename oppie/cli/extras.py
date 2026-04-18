def extras_available() -> dict[str, bool]:
    """Check which optional extras are installed."""
    httpx_ok = _try_import('httpx')
    return {
        'linear': httpx_ok,
        'openai': httpx_ok,
        'anthropic': httpx_ok,
    }


def _try_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
