from __future__ import annotations

from rich.console import Console

console = Console()


def success(msg: str) -> None:
    """Print a success message with green checkmark."""
    console.print(f'[green]\u2713[/green] {msg}')


def warn(msg: str) -> None:
    """Print a warning message with yellow marker."""
    console.print(f'[yellow]\u26a0[/yellow] {msg}')


def error(msg: str) -> None:
    """Print an error message with red marker."""
    console.print(f'[red]\u2717[/red] {msg}')


def info(msg: str) -> None:
    """Print an info message with blue marker."""
    console.print(f'[blue]\u25cf[/blue] {msg}')
