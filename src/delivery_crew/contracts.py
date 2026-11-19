"""Contratos entre agentes.

Cada traspaso es un artefacto: un archivo Markdown con un bloque YAML al inicio
(front matter) que contiene los campos estructurados, y un cuerpo libre opcional.
El formato está descrito en .kiro/steering/contratos-agentes.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .conventions import CONFIGURATION_KEYS, SAFE_VALUE

ApprovalStatus = Literal["pendiente", "aprobado", "rechazado"]
Verdict = Literal["aprobado", "observaciones", "rechazado"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class ContractError(ValueError):
    """El artefacto no cumple el contrato."""


class Approval(BaseModel):
    """Aprobación humana de un artefacto."""

    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus = "pendiente"
    by: str | None = None
    at: datetime | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def _decision_needs_author(self) -> "Approval":
        if self.status != "pendiente" and not self.by:
            raise ValueError("una aprobación o rechazo debe indicar quién la dio ('by')")
        if self.status == "rechazado" and not self.reason:
            raise ValueError("un rechazo debe indicar el motivo ('reason')")
        return self


class Artifact(BaseModel):
    """Base de todos los artefactos."""

    model_config = ConfigDict(extra="forbid")

    FILENAME: ClassVar[str]
    STEP: ClassVar[int]

    run_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utcnow)
    body: str = ""
    approval: Approval = Field(default_factory=Approval)

    def to_markdown(self) -> str:
        data = self.model_dump(mode="json", exclude={"body"})
        header = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
        return f"---\n{header}\n---\n\n{self.body.strip()}\n"

    @classmethod
    def from_markdown(cls, text: str) -> "Artifact":
        text = text.lstrip("\ufeff")
        if not text.startswith("---"):
            raise ContractError(f"{cls.FILENAME}: falta el bloque YAML inicial")
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ContractError(f"{cls.FILENAME}: el bloque YAML no está cerrado")
        try:
            data = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            raise ContractError(f"{cls.FILENAME}: YAML inválido: {exc}") from exc
        if not isinstance(data, dict):
            raise ContractError(f"{cls.FILENAME}: el bloque YAML debe ser un mapa")
        data["body"] = parts[2].strip()
        try:
            return cls.model_validate(data)
        except ValidationError as exc:
            raise ContractError(_format_errors(cls.FILENAME, exc)) from exc


def _format_errors(filename: str, exc: ValidationError) -> str:
    lines = [f"{filename}: el artefacto no cumple el contrato"]
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "(raíz)"
        lines.append(f"  - {field}: {err['msg']}")
    return "\n".join(lines)


class Requirement(Artifact):
    """01: entrada del orquestador."""

    FILENAME: ClassVar[str] = "01-requerimiento.md"
    STEP: ClassVar[int] = 1

    title: str = Field(min_length=3)
    description: str = Field(min_length=10)
    acceptance_criteria: list[str] = Field(min_length=1)
    affected_service: str = Field(min_length=1)


class DeploymentComponent(BaseModel):
    """A component that Architecture authorizes SysOps to provision."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2)
    kind: str = Field(min_length=2, pattern=r"^[a-z][a-z0-9_-]*$")
    depends_on: list[str] = Field(default_factory=list)
    configuration: dict[str, str] = Field(default_factory=dict)

    @field_validator("depends_on", "configuration", mode="before")
    @classmethod
    def _null_is_empty(cls, value, info):
        # Los modelos de lenguaje a veces envían null en campos opcionales.
        if value is None:
            return [] if info.field_name == "depends_on" else {}
        return value

    @model_validator(mode="after")
    def _configuration_follows_convention(self) -> "DeploymentComponent":
        allowed = CONFIGURATION_KEYS.get(self.kind)
        if allowed is not None:
            unknown = sorted(set(self.configuration) - allowed)
            if unknown:
                raise ValueError(
                    f"configuración no reconocida para {self.kind} '{self.name}': {', '.join(unknown)}; "
                    f"claves permitidas: {', '.join(sorted(allowed))}"
                )
        bad = sorted(k for k, v in self.configuration.items() if not SAFE_VALUE.fullmatch(v))
        if bad:
            raise ValueError(f"valores no permitidos en configuración ({', '.join(bad)}): use letras, números, '_', '.' o '-'")
        return self


class DeploymentSpec(BaseModel):
    """Structured operational constraints supplied by Architecture."""

    model_config = ConfigDict(extra="forbid")

    environment: Literal["dev", "qa", "uat", "prod"]
    components: list[DeploymentComponent] = Field(min_length=1)
    network_exposure: Literal["private", "internal", "public"]
    data_classification: Literal["synthetic", "internal", "confidential"]
    health_check: str = Field(min_length=3)
    rollback_strategy: str = Field(min_length=10)
    observability: list[str] = Field(min_length=1)


class DeployableArtifact(BaseModel):
    """A build output supplied by Development for one architecture component."""

    model_config = ConfigDict(extra="forbid")

    component: str = Field(min_length=2)
    kind: Literal["zip", "container", "static", "package"]
    source_path: str = Field(min_length=1)
    build_command: str = Field(min_length=1)
    entrypoint: str | None = None


class Design(Artifact):
    """02: salida del agente Arquitecto."""

    FILENAME: ClassVar[str] = "02-diseno.md"
    STEP: ClassVar[int] = 2

    summary: str = Field(min_length=10)
    components: list[str] = Field(min_length=1)
    decision: str = Field(min_length=10)
    risks: list[str] = Field(default_factory=list)
    verdict: Verdict
    standards_cited: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    deployment_spec: DeploymentSpec | None = None

    @model_validator(mode="after")
    def _verdict_needs_support(self) -> "Design":
        if self.verdict != "aprobado" and not (self.standards_cited or self.open_questions):
            raise ValueError(
                "un veredicto distinto de 'aprobado' debe citar estándares o dejar preguntas abiertas"
            )
        return self


class Change(Artifact):
    """03: salida del agente Desarrollador."""

    FILENAME: ClassVar[str] = "03-cambio.md"
    STEP: ClassVar[int] = 3

    branch: str = Field(min_length=1)
    pull_request_url: str | None = None
    files_modified: list[str] = Field(min_length=1)
    test_result: Literal["passed", "failed"]
    test_summary: str = Field(min_length=1)
    deliverables: list[DeployableArtifact] = Field(default_factory=list)

    @model_validator(mode="after")
    def _pr_only_if_tests_pass(self) -> "Change":
        if self.pull_request_url and self.test_result != "passed":
            raise ValueError("no se puede abrir un pull request con pruebas fallidas")
        return self


class Deployment(Artifact):
    """04: salida del agente Despliegue."""

    FILENAME: ClassVar[str] = "04-despliegue.md"
    STEP: ClassVar[int] = 4

    target_account_id: str = Field(pattern=r"^\d{12}$")
    region: str = Field(min_length=1)
    resources: list[str] = Field(min_length=1)
    estimated_cost_usd: float = Field(ge=0)
    rollback_plan: str = Field(min_length=10)
    health_check: Literal["pendiente", "ok", "fallo"] = "pendiente"
    rolled_back: bool = False
    # Ejecución real (los completa el ejecutor de despliegue tras la aprobación de SysOps).
    stack_name: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9-]{0,127}$")
    project_name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{2,30}$")
    environment: str | None = None
    endpoint_url: str | None = Field(default=None, pattern=r"^https://[A-Za-z0-9.-]+(/[A-Za-z0-9._~/-]*)?$")
    deployed_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    deployment_status: Literal["no_ejecutado", "en_curso", "desplegado", "fallido"] = "no_ejecutado"
    deployment_log: list[str] = Field(default_factory=list)


ARTIFACTS: tuple[type[Artifact], ...] = (Requirement, Design, Change, Deployment)
BY_STEP: dict[int, type[Artifact]] = {a.STEP: a for a in ARTIFACTS}
