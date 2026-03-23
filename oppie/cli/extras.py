def extras_available() -> dict[str, bool]:
    """Check which optional extras are installed."""
    httpx_ok = _try_import('httpx')
    textual_ok = _try_import('textual')
    return {
        'linear': httpx_ok,
        'llm': httpx_ok,
        'tui': textual_ok,
    }


def _try_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False
