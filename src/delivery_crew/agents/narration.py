"""Narración de agentes: convierte el texto que el modelo va generando en eventos de auditoría.

Strands llama al callback_handler con fragmentos de texto (`data`) y con el inicio de cada
herramienta. El narrador junta los fragmentos y emite un mensaje completo cuando el modelo
termina de hablar o pasa a usar una herramienta. Así el panel puede mostrar, en vivo, qué
está razonando cada agente.
"""

from __future__ import annotations

from typing import Any, Callable

MAX_MESSAGE_CHARS = 4000


class Narrator:
    def __init__(self, emit: Callable[[str], None], echo: Callable[[str], None] | None = None,
                 max_chars: int = MAX_MESSAGE_CHARS) -> None:
        self._emit = emit
        self._echo = echo
        self._max = max_chars
        self._buffer: list[str] = []

    def __call__(self, **kwargs: Any) -> None:
        data = kwargs.get("data")
        if isinstance(data, str) and data:
            self._buffer.append(data)
            if self._echo:
                self._echo(data)
        event = kwargs.get("event") or {}
        tool_use = event.get("contentBlockStart", {}).get("start", {}).get("toolUse") if isinstance(event, dict) else None
        if tool_use or kwargs.get("complete") or "message" in kwargs:
            self.flush()

    def flush(self) -> None:
        text = "".join(self._buffer).strip()
        self._buffer.clear()
        if text:
            if len(text) > self._max:
                text = text[: self._max] + " …"
            self._emit(text)
