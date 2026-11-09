from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel

TCommand = TypeVar("TCommand", bound=BaseModel)
TResult = TypeVar("TResult")


class Command(BaseModel):
    """Base command class"""

    pass


class CommandHandler(ABC, Generic[TCommand, TResult]):
    """Base command handler"""

    @abstractmethod
    async def handle(self, command: TCommand) -> TResult:
        """Execute command"""
        pass


class CommandBus:
    """Command bus for routing commands to handlers"""

    def __init__(self) -> None:
        self._handlers: Dict[type, CommandHandler[Any, Any]] = {}

    def register(self, command_type: type[Command], handler: CommandHandler[Any, Any]) -> None:
        """Register command handler"""
        self._handlers[command_type] = handler

    async def execute(self, command: Command) -> Any:
        """Execute command"""
        handler = self._handlers.get(type(command))
        if not handler:
            raise ValueError(f"No handler registered for {type(command).__name__}")
        return await handler.handle(command)


command_bus = CommandBus()
