"""Progress reporting helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ProgressState:
    current: int = 0
    total: int = 0
    message: str = ""


class ProgressReporter:
    """Tiny progress abstraction for UI or logs."""

    def __init__(self) -> None:
        self.state = ProgressState()

    def update(self, current: int, total: int, message: Optional[str] = None) -> None:
        self.state.current = current
        self.state.total = total
        if message is not None:
            self.state.message = message
