"""Espacio de trabajo acotado del agente Desarrollador.

El agente solo puede leer y escribir dentro de una carpeta (el servicio), y solo puede
ejecutar las pruebas de esa carpeta. No hay herramienta de shell.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

MAX_FILE_BYTES = 200_000
ALLOWED_SUFFIXES = {".py", ".md", ".txt", ".json", ".ini", ".toml", ".cfg"}
IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
TEST_TIMEOUT_S = 120

EventHook = Callable[[str, dict], None]


class SandboxError(PermissionError):
    """Operación fuera de lo permitido."""


@dataclass
class TestRun:
    __test__ = False  # no es una prueba de pytest

    passed: bool
    summary: str
    output: str


class Sandbox:
    def __init__(self, workdir: str | Path, service_dir: str = "services/auth_service",
                 on_event: EventHook | None = None) -> None:
        self.workdir = Path(workdir).resolve()
        self.root = (self.workdir / service_dir).resolve()
        self.service_dir = service_dir
        if not self.root.is_dir():
            raise SandboxError(f"no existe la carpeta del servicio: {self.root}")
        self._on_event = on_event or (lambda action, details: None)

    # --- rutas -------------------------------------------------------------

    def resolve(self, rel_path: str) -> Path:
        """Convierte una ruta relativa a la carpeta del servicio en absoluta, o falla."""
        if not isinstance(rel_path, str) or not rel_path.strip():
            raise SandboxError("ruta vacía")
        cleaned = rel_path.strip().replace("\\", "/")
        pure = PurePosixPath(cleaned)
        if pure.is_absolute() or ":" in cleaned or any(part == ".." for part in pure.parts):
            raise SandboxError(f"ruta no permitida: {rel_path!r} (use rutas relativas al servicio, sin '..')")
        if any(part in IGNORED_DIRS or part.startswith(".") for part in pure.parts):
            raise SandboxError(f"ruta no permitida: {rel_path!r}")
        target = (self.root / Path(*pure.parts)).resolve()
        if target != self.root and self.root not in target.parents:
            raise SandboxError(f"ruta fuera del servicio: {rel_path!r}")
        return target

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    # --- herramientas ------------------------------------------------------

    def list_files(self) -> list[str]:
        files = []
        for path in sorted(self.root.rglob("*")):
            rel_parts = path.relative_to(self.root).parts
            if path.is_file() and not any(p in IGNORED_DIRS or p.startswith(".") for p in rel_parts):
                files.append(self.relative(path))
        return files

    def read_file(self, rel_path: str) -> str:
        target = self.resolve(rel_path)
        if not target.is_file():
            raise SandboxError(f"no existe el archivo: {rel_path}")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise SandboxError(f"archivo demasiado grande: {rel_path}")
        self._on_event("tool_read_file", {"path": self.relative(target)})
        return target.read_text(encoding="utf-8")

    def write_file(self, rel_path: str, content: str) -> str:
        target = self.resolve(rel_path)
        if target.suffix not in ALLOWED_SUFFIXES:
            raise SandboxError(f"extensión no permitida: {target.suffix or '(sin extensión)'}")
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise SandboxError("contenido demasiado grande")
        existed = target.exists()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        rel = self.relative(target)
        self._on_event("tool_write_file", {"path": rel, "created": not existed})
        return rel

    def run_tests(self, timeout: int = TEST_TIMEOUT_S) -> TestRun:
        # Sin credenciales AWS: las pruebas no deben depender de la nube.
        env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                cwd=self.root, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            result = TestRun(False, f"las pruebas superaron {timeout} s", "")
        else:
            output = (proc.stdout + proc.stderr).strip()
            lines = [ln for ln in output.splitlines() if ln.strip()]
            summary = lines[-1].strip("= ").strip() if lines else "sin salida"
            result = TestRun(proc.returncode == 0, summary, output[-6000:])
        self._on_event("tool_run_tests", {"passed": result.passed, "summary": result.summary})
        return result
