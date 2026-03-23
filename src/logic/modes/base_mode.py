# src/logic/modes/base_mode.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.logic.input_event import InputEvent


class BaseMode(ABC):
    """Abstract base class for all pi-ano modes."""

    @abstractmethod
    def reset(self, now: float) -> None: ...

    @abstractmethod
    def update(self, now: float) -> None: ...

    @abstractmethod
    def handle_events(self, events: List[InputEvent]) -> None: ...

    def on_exit(self) -> None:
        """Called when leaving this mode. Override if cleanup is needed."""
        pass
