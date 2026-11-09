from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel

TQuery = TypeVar("TQuery", bound=BaseModel)
TResult = TypeVar("TResult")


class Query(BaseModel):
    """Base query class"""

    pass


class QueryHandler(ABC, Generic[TQuery, TResult]):
    """Base query handler"""

    @abstractmethod
    async def handle(self, query: TQuery) -> TResult:
        """Execute query"""
        pass


class QueryBus:
    """Query bus for routing queries to handlers"""

    def __init__(self) -> None:
        self._handlers: Dict[type, QueryHandler[Any, Any]] = {}

    def register(self, query_type: type[Query], handler: QueryHandler[Any, Any]) -> None:
        """Register query handler"""
        self._handlers[query_type] = handler

    async def execute(self, query: Query) -> Any:
        """Execute query"""
        handler = self._handlers.get(type(query))
        if not handler:
            raise ValueError(f"No handler registered for {type(query).__name__}")
        return await handler.handle(query)


query_bus = QueryBus()
