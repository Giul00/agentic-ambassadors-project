"""Validation and rendering for the file-based agent handoff contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re


RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
APPROVED_PATTERN = re.compile(
    r"(?:estado\s+de\s+aprobaci[oó]n(?:\s+humana)?|aprobaci[oó]n)\s*:\s*aprobado\b",
    re.IGNORECASE,
)


class ContractError(ValueError):
    """Raised when a handoff does not meet the deployment-agent contract."""


@dataclass(frozen=True)
class CodeChange:
    run_id: str
    branch: str
    pull_request: str
    changed_files: tuple[str, ...]
    test_result: str


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ContractError("El id de ejecución solo puede tener letras, números, _ y - (máximo 64 caracteres).")
    return run_id


def _field(text: str, name: str) -> str:
    match = re.search(rf"^\s*(?:[-*]\s*)?{re.escape(name)}\s*:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        raise ContractError(f"Falta el campo obligatorio '{name}' en 03-cambio.md.")
    return match.group(1).strip()


def _files(text: str) -> tuple[str, ...]:
    match = re.search(r"archivos\s+modificados\s*:\s*(.*?)(?=^\s*(?:[-*]\s*)?(?:resultado\s+de\s+las\s+pruebas|estado\s+de\s+aprobaci[oó]n|aprobaci[oó]n)\s*:|\Z)", text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
    if not match:
        raise ContractError("Falta el campo obligatorio 'archivos modificados' en 03-cambio.md.")
    values = [line.strip(" -\t") for line in match.group(1).strip().splitlines()]
    values = [value for value in values if value]
    if not values:
        raise ContractError("'archivos modificados' no puede estar vacío.")
    return tuple(values)


def parse_approved_change(run_id: str, path: Path) -> CodeChange:
    validate_run_id(run_id)
    if not path.is_file():
        raise ContractError(f"No existe el handoff requerido: {path}")
    text = path.read_text(encoding="utf-8")
    if not APPROVED_PATTERN.search(text):
        raise ContractError("El cambio no tiene aprobación humana 'aprobado'; no se genera un plan de despliegue.")
    return CodeChange(
        run_id=run_id,
        branch=_field(text, "rama"),
        pull_request=_field(text, "enlace al pull request"),
        changed_files=_files(text),
        test_result=_field(text, "resultado de las pruebas"),
    )


def render_deployment_plan(change: CodeChange, timestamp: datetime | None = None) -> str:
    now = timestamp or datetime.now(timezone.utc)
    changed_files = "\n".join(f"- `{file}`" for file in change.changed_files)
    return f"""# Plan de despliegue: {change.run_id}

**Fecha (UTC):** {now.isoformat(timespec='seconds')}
**Rama fuente:** `{change.branch}`
**Pull request:** {change.pull_request}

## Validaciones del handoff

- Estado de aprobación humana del cambio: **aprobado**
- Resultado de las pruebas informado: {change.test_result}
- Archivos modificados:
{changed_files}

## Recursos a crear o modificar

- Pendiente de confirmar mediante `cdk diff` tras revisar la infraestructura entregada en el PR.
- El agente no infiere recursos ni ejecuta IaC sin una aprobación humana explícita de SysOps.

## Pipeline propuesto

1. **Validar:** ejecutar pruebas y `cdk synth`.
2. **Planificar:** ejecutar `cdk diff` y adjuntar el resultado a este artefacto.
3. **Aprobar:** SysOps revisa cuenta AWS, diff, costo y rollback; registra aprobación abajo.
4. **Desplegar:** ejecutar el comando CDK aprobado, con la cuenta esperada validada por `aws sts get-caller-identity`.
5. **Verificar:** ejecutar health checks y consultar métricas/logs de CloudWatch.
6. **Recuperar:** si falla la verificación, ejecutar el rollback aprobado y registrar la evidencia.

## Costo estimado

- Pendiente de cálculo después de `cdk diff`. No se autoriza el despliegue hasta documentarlo.

## Plan de rollback

- Conservar el artefacto/versión previa antes de desplegar.
- Revertir al último commit o versión estable aprobada si falla el health check.
- Confirmar el estado recuperado mediante el mismo health check y CloudWatch.

## Resultado del chequeo de salud

- Pendiente: el despliegue aún no fue autorizado ni ejecutado.

## Aprobación humana de SysOps

Estado de aprobación humana: **pendiente**
Nombre: pendiente
Fecha: pendiente

## Auditoría

- El plan fue generado desde `03-cambio.md` aprobado.
- No se ejecutaron comandos AWS ni cambios de infraestructura al generar este documento.
"""
