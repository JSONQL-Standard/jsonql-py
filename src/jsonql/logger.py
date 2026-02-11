"""Logger abstraction for JSONQL Python SDK."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod


class Logger(ABC):
    """Abstract logger interface."""

    @abstractmethod
    def debug(self, message: str, *args: object) -> None: ...

    @abstractmethod
    def info(self, message: str, *args: object) -> None: ...

    @abstractmethod
    def warn(self, message: str, *args: object) -> None: ...

    @abstractmethod
    def error(self, message: str, *args: object) -> None: ...


class ConsoleLogger(Logger):
    """Logger that writes to the standard ``logging`` module."""

    def __init__(self, name: str = "jsonql") -> None:
        self._log = logging.getLogger(name)

    def debug(self, message: str, *args: object) -> None:
        self._log.debug(message, *args)

    def info(self, message: str, *args: object) -> None:
        self._log.info(message, *args)

    def warn(self, message: str, *args: object) -> None:
        self._log.warning(message, *args)

    def error(self, message: str, *args: object) -> None:
        self._log.error(message, *args)


class NoOpLogger(Logger):
    """Silent logger — discards all messages."""

    def debug(self, message: str, *args: object) -> None:
        pass

    def info(self, message: str, *args: object) -> None:
        pass

    def warn(self, message: str, *args: object) -> None:
        pass

    def error(self, message: str, *args: object) -> None:
        pass
