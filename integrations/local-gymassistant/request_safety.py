"""Process-wide accidental overload guard; backend must enforce its own quotas."""
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
import time
import json
from email.utils import parsedate_to_datetime
from datetime import timezone

from mcp.server.fastmcp import FastMCP


class SafetyLimit(Exception):
    """Rejected before sending: safe to distinguish from an unknown write outcome."""


_budget = ContextVar('gym_request_budget', default=None)


class CallBudget:
    def __init__(self):
        self.remaining = 64
        self.deadline = time.monotonic() + 90
        self.lock = Lock()

    def consume(self):
        with self.lock:
            if self.remaining <= 0 or time.monotonic() >= self.deadline:
                raise SafetyLimit('Лимит чтения за один вызов достигнут. Используйте постраничные инструменты.')
            self.remaining -= 1


class SafeFastMCP(FastMCP):
    read_only = False

    async def call_tool(self, name, arguments):
        tool = self._tool_manager.get_tool(name)
        if self.read_only and tool and tool.annotations and tool.annotations.readOnlyHint is False:
            raise SafetyLimit('MCP работает только на чтение; инструмент записи не запускался.')
        marker = _budget.set(CallBudget())
        try:
            return await super().call_tool(name, arguments)
        finally:
            _budget.reset(marker)


class RequestGuard:
    def __init__(self, clock=time.monotonic, wall_clock=time.time):
        self.clock = clock
        self.wall_clock = wall_clock
        self.lock = Lock()
        self.calls = deque()
        self.writes = deque()
        self.active = 0
        self.cooldown_until = 0

    @contextmanager
    def permit(self, method):
        budget = _budget.get()
        if budget is not None:
            budget.consume()
        with self.lock:
            now = self.clock()
            for queue in (self.calls, self.writes):
                while queue and queue[0] <= now - 60:
                    queue.popleft()
            if now < self.cooldown_until:
                raise SafetyLimit('API попросил паузу. Повторите позже; автоматического повтора нет.')
            write = method.upper() != 'GET'
            if self.active >= 2 or len(self.calls) >= 120 or (write and len(self.writes) >= 12):
                raise SafetyLimit('Лимит MCP достигнут: 2 запроса одновременно, 120/мин, запись 12/мин. Повторите позже.')
            self.calls.append(now)
            if write:
                self.writes.append(now)
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1

    def cooldown(self, retry_after=None):
        try:
            seconds = max(30, min(300, int(retry_after)))
        except (TypeError, ValueError, OverflowError):
            try:
                until = parsedate_to_datetime(retry_after)
                if until.tzinfo is None:
                    until = until.replace(tzinfo=timezone.utc)
                seconds = max(30, min(300, until.timestamp() - self.wall_clock()))
            except (TypeError, ValueError, OverflowError, AttributeError):
                seconds = 30
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, self.clock() + seconds)


# Shared by stdio tools, aliases, secondary Health token and remote auth checks.
PROCESS_GUARD = RequestGuard()


def encode_payload(body):
    # Walk iteratively before serialization so deeply nested/unbounded legacy
    # dictionaries cannot exhaust the encoder or bypass typed plan limits.
    pending = [(body, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if depth > 20 or nodes > 100000:
            raise SafetyLimit('Слишком большое или вложенное тело запроса; запрос не отправлен.')
        if isinstance(value, str) and len(value) > 10000:
            raise SafetyLimit('Текст превышает 10000 символов; запрос не отправлен.')
        if isinstance(value, (list, dict)):
            if len(value) > 10000:
                raise SafetyLimit('Слишком много элементов; запрос не отправлен.')
            if isinstance(value, dict):
                if any(not isinstance(k, str) or len(k) > 200 for k in value):
                    raise SafetyLimit('Некорректные ключи тела запроса.')
                value = value.values()
            pending.extend((item, depth + 1) for item in value)
    chunks, size = [], 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(body):
        encoded = chunk.encode('utf-8')
        size += len(encoded)
        if size > 1024 * 1024:
            raise SafetyLimit('Тело запроса превышает 1 МиБ; запрос не отправлен.')
        chunks.append(encoded)
    return b''.join(chunks)
