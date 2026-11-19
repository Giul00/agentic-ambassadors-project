"""Carga variables de entorno desde un archivo .env (sin dependencias externas).

Se usa al arrancar la API, el orquestador y check_env. Busca .env en el directorio actual y,
si no está, en la raíz del repositorio. Lo que define el .env reemplaza al entorno: así queda
un único lugar donde mirar qué credenciales usa la demo.

Formato: KEY=VALOR por línea; admite comentarios (#), líneas vacías, `export KEY=...`
y valores entre comillas simples o dobles. Nunca imprime valores, solo nombres.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()  # comentario al final de la línea
        values[key] = value
    return values


def find(start: Path | None = None) -> Path | None:
    for candidate in ((start or Path.cwd()) / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            return candidate
    return None


def load(path: Path | None = None, override: bool = True) -> tuple[Path | None, list[str]]:
    """Carga el .env. Devuelve (archivo, nombres cargados). Los valores vacíos se ignoran."""
    path = path or find()
    if path is None:
        return None, []
    loaded = []
    for key, value in parse(path.read_text(encoding="utf-8-sig")).items():
        if not value:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return path, loaded


def load_and_report(prefix: str = "") -> None:
    path, keys = load()
    if path is None:
        print(f"{prefix}Sin archivo .env (se usan las variables de la terminal).")
    else:
        print(f"{prefix}Variables cargadas desde {path}: {', '.join(sorted(keys)) or '(ninguna)'}")
