"""Agente Arquitecto (Unit 03).

Lee `01-requerimiento.md` (debe estar aprobado), lo evalúa contra la base
de estándares de `docs/estandares/` y escribe `02-diseno.md` con resumen,
componentes afectados, decisión (ADR), riesgos y veredicto citando el
estándar aplicado (`standards_cited`, campo propio del contrato `Design`).

Si el requerimiento es ambiguo o le falta información esencial para
diseñar con responsabilidad, el agente no inventa: deja el diseño en
estado `observaciones` con `open_questions` (campo del contrato) en lugar
de completar los campos técnicos con supuestos.

La llamada a Bedrock está aislada en `_invoke_agent` para poder probar el
resto de la lógica sin red ni credenciales (ver `tests/test_architect.py`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from strands import Agent

from ..bedrock import get_strands_model
from ..contracts import DeploymentSpec, Design, Requirement, Verdict
from ..conventions import CONFIGURATION_KEYS
from ..runs import RunStore

ACTOR = "agente-arquitecto"
REPO_ROOT = Path(__file__).resolve().parents[3]
STANDARDS_DIR = REPO_ROOT / "docs" / "estandares"
CATALOG_PATH = REPO_ROOT / "templates" / "sysops" / "catalog.yml"

# Significado de cada clave de configuración, para explicarla en el prompt.
CONFIGURATION_HELP = {
    ("dynamodb", "partition_key"): "nombre del atributo clave de partición (String)",
    ("dynamodb", "ttl_attribute"): "nombre del atributo TTL (Number, epoch en segundos)",
    ("lambda", "FREQUENCY_STORE"): "implementación del contador: 'dynamodb' en AWS, 'memory' solo en pruebas",
}
# Configuración obligatoria en un diseño aprobado: sin estos nombres, código e
# infraestructura pueden no coincidir.
REQUIRED_CONFIGURATION = {"dynamodb": {"partition_key", "ttl_attribute"}}


def _find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Devuelve un ciclo de dependencias (ej. ['a', 'b', 'a']) o None."""
    state: dict[str, int] = {}  # 1 = en curso, 2 = terminado
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        path.append(node)
        for dep in graph.get(node, []):
            if state.get(dep) == 1:
                return path[path.index(dep):] + [dep]
            if dep not in state:
                found = visit(dep)
                if found:
                    return found
        path.pop()
        state[node] = 2
        return None

    for node in graph:
        if node not in state:
            found = visit(node)
            if found:
                return found
    return None


def known_standard_ids() -> set[str]:
    """Ids ARQ-NN definidos en docs/estandares/ (sin el README)."""
    ids: set[str] = set()
    for path in STANDARDS_DIR.glob("*.md"):
        if path.name != "README.md":
            ids.update(re.findall(r"\bARQ-\d{2}\b", path.read_text(encoding="utf-8")))
    return ids


def supported_kinds() -> set[str]:
    """Tipos de componente con plantilla homologada en el catálogo de SysOps."""
    if not CATALOG_PATH.is_file():
        return set()
    catalog = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    kinds: set[str] = set()
    for profile in (catalog.get("profiles") or {}).values():
        if profile.get("status", "ready") == "ready" and profile.get("template"):
            kinds.update(profile.get("capabilities", []))
    return kinds


# --- Esquema de la respuesta del modelo ------------------------------------
# No es el artefacto final: RunStore.write completa run_id, created_at y
# approval (siempre "pendiente"; el agente nunca autoaprueba su propio
# diseño, ver ARQ-07).


class DesignProposal(BaseModel):
    summary: str = Field(..., min_length=10)
    components: list[str] = Field(..., min_length=1)
    decision: str = Field(..., min_length=10)
    risks: list[str] = Field(default_factory=list)
    verdict: Verdict
    standards_cited: list[str] = Field(
        default_factory=list,
        description="Ids de estándares citados, ej. ['ARQ-01', 'ARQ-03']",
    )
    open_questions: list[str] = Field(
        default_factory=list,
        description="Preguntas que un humano debe responder antes de poder diseñar",
    )
    diagram_mermaid: str | None = Field(
        default=None, description="Diagrama Mermaid del cambio puntual, o None si hay open_questions"
    )
    deployment_spec: DeploymentSpec | None = Field(
        default=None,
        description=(
            "Infraestructura que SysOps debe crear. Obligatoria si verdict='aprobado'; "
            "null si el diseño no se puede aprobar."
        ),
    )

    @field_validator("risks", "standards_cited", "open_questions", mode="before")
    @classmethod
    def _null_list_is_empty(cls, value):
        # El modelo a veces envía null en listas opcionales; equivale a lista vacía.
        return [] if value is None else value

    @model_validator(mode="after")
    def _verdict_needs_support(self) -> "DesignProposal":
        if self.verdict != "aprobado" and not (self.standards_cited or self.open_questions):
            raise ValueError(
                "un veredicto distinto de 'aprobado' debe citar estándares (standards_cited) "
                "o dejar preguntas abiertas (open_questions)"
            )
        return self

    @model_validator(mode="after")
    def _standards_must_exist(self) -> "DesignProposal":
        known = known_standard_ids()
        unknown = sorted(set(self.standards_cited) - known) if known else []
        if unknown:
            raise ValueError(
                f"standards_cited incluye estándares que no existen: {', '.join(unknown)}; "
                f"válidos: {', '.join(sorted(known))}"
            )
        return self

    @model_validator(mode="after")
    def _approved_design_is_deployable(self) -> "DesignProposal":
        if self.verdict != "aprobado":
            return self
        spec = self.deployment_spec
        if spec is None:
            raise ValueError(
                "un diseño con verdict='aprobado' debe incluir deployment_spec; si no se puede "
                "declarar la infraestructura, use verdict='observaciones' con open_questions"
            )
        kinds = supported_kinds()
        unsupported = sorted({c.kind for c in spec.components} - kinds) if kinds else []
        if unsupported:
            raise ValueError(
                f"deployment_spec usa tipos sin plantilla homologada: {', '.join(unsupported)}; "
                f"tipos disponibles: {', '.join(sorted(kinds))}. Si el cambio los necesita, "
                "use verdict='observaciones' y pregúntelo en open_questions"
            )
        names = [c.name for c in spec.components]
        if len(names) != len(set(names)):
            raise ValueError("deployment_spec tiene nombres de componente repetidos")
        dangling = sorted({d for c in spec.components for d in c.depends_on} - set(names))
        if dangling:
            raise ValueError(f"depends_on referencia componentes inexistentes: {', '.join(dangling)}")
        cycle = _find_cycle({c.name: list(c.depends_on) for c in spec.components})
        if cycle:
            raise ValueError(
                f"depends_on forma un ciclo: {' -> '.join(cycle)}. depends_on indica qué debe existir "
                "antes (ej. la lambda depende de la tabla; la API depende de la lambda), nunca en ambos sentidos"
            )
        for component in spec.components:
            missing = sorted(REQUIRED_CONFIGURATION.get(component.kind, set()) - set(component.configuration))
            if missing:
                raise ValueError(
                    f"el componente {component.name} ({component.kind}) debe declarar en configuration: "
                    f"{', '.join(missing)}"
                )
        return self


SYSTEM_PROMPT_TEMPLATE = """\
Eres el agente Arquitecto de "Delivery Crew", un sistema multiagente que \
lleva cambios de requerimiento a despliegue verificado en un servicio de \
autorizaciones de adquirencia (`auth-service`). Tu única salida es un \
diseño técnico evaluado contra la base de estándares del equipo.

# Base de estándares (cítalos por id, ej. "ARQ-01", en `standards_cited`)

{standards}

# Reglas de tu trabajo

1. Si el requerimiento tiene toda la información necesaria para diseñar \
   (qué cambia, dónde, con qué datos), responde con un diseño completo y \
   un diagrama Mermaid del cambio puntual (no el diagrama general del \
   sistema).
2. Si el requerimiento es ambiguo o le falta información esencial (por \
   ejemplo: no dice qué pasa en un caso borde, o deja indefinido qué \
   componente guarda un estado nuevo), NO inventes el diseño: pon \
   verdict="observaciones", deja `open_questions` con las preguntas \
   concretas que un humano debe responder, y `diagram_mermaid` en null. \
   `summary`, `components` y `decision` deben explicar igualmente qué se \
   sabe y por qué no se puede avanzar, no pueden quedar vacíos.
3. Todo veredicto que no sea "aprobado" debe citar en `standards_cited` \
   el o los estándares incumplidos, o dejar `open_questions`, y explicar \
   el por qué en `decision`.
4. Nunca propongas guardar PAN, CVV ni datos reales de tarjetas, ni \
   saltar la aprobación humana de ningún paso del flujo.

{deployment_rules}
"""


def deployment_rules() -> str:
    """Instrucciones sobre deployment_spec, generadas desde conventions.py y el catálogo de SysOps."""
    kinds = sorted(supported_kinds())
    config_lines = []
    for kind, keys in sorted(CONFIGURATION_KEYS.items()):
        for key in sorted(keys):
            config_lines.append(
                f"   - en componentes `{kind}`, clave `{key}` (sin prefijo): {CONFIGURATION_HELP.get((kind, key), '')}"
            )
    required = "; ".join(f"`{k}` debe declarar {', '.join(sorted(v))}" for k, v in REQUIRED_CONFIGURATION.items())
    return f"""\
# Especificación de despliegue (`deployment_spec`)

SysOps genera la infraestructura solo a partir de `deployment_spec`, y el agente \
Desarrollador escribe el código con los nombres que declares acá. Si no coinciden, \
el servicio falla en AWS aunque las pruebas pasen.

5. Si verdict="aprobado", `deployment_spec` es obligatorio. Si no puedes \
   declarar la infraestructura, usa verdict="observaciones" con open_questions.
6. `components[].kind` solo puede ser uno de estos tipos con plantilla \
   homologada: {', '.join(kinds) or '(catálogo no disponible)'}. Si el cambio \
   necesita otro tipo, usa verdict="observaciones" y pregúntalo.
7. Declara cada recurso como un componente con nombre corto en kebab-case \
   (ej. "auth-api", "auth-handler", "frequency-store") y relaciónalos con \
   `depends_on` usando esos nombres. `depends_on` indica qué debe existir \
   antes: la lambda depende de la tabla y la API depende de la lambda. \
   Nunca declares una dependencia en ambos sentidos.
8. `configuration` solo admite estas claves (valores con letras, números, \
   "_", "." o "-"):
{chr(10).join(config_lines)}
   Reglas: {required}. Una lambda que use una tabla DynamoDB declara \
   `FREQUENCY_STORE=dynamodb`.
9. `data_classification` es "synthetic" para auth-service (no hay datos \
   reales). `environment` es "qa" salvo que el requerimiento diga otra cosa. \
   `health_check` describe la verificación observable tras desplegar; \
   `rollback_strategy`, cómo volver a la versión anterior; `observability`, \
   qué logs o métricas se revisan.
"""


def load_standards() -> str:
    """Lee todos los estándares de docs/estandares/*.md (menos el README) y
    los concatena para el prompt. Única fuente de verdad: se edita el
    Markdown, no el código (NFR de la Unit 03)."""
    files = sorted(p for p in STANDARDS_DIR.glob("*.md") if p.name != "README.md")
    if not files:
        raise RuntimeError(f"No se encontraron estándares en {STANDARDS_DIR}")
    return "\n\n---\n\n".join(p.read_text(encoding="utf-8") for p in files)


def _build_prompt(requirement: Requirement) -> str:
    criteria = "\n".join(f"- {c}" for c in requirement.acceptance_criteria)
    return f"""\
Requerimiento (run_id={requirement.run_id}):

Título: {requirement.title}
Servicio afectado: {requirement.affected_service}
Descripción: {requirement.description}

Criterios de aceptación:
{criteria}

Produce tu respuesta estructurada según las reglas del sistema.
"""


def _invoke_agent(prompt: str, *, fast: bool = False) -> DesignProposal:
    """Única función que toca Bedrock. Inyectable vía el parámetro
    `agent_fn` de `generate_design` para pruebas sin red."""
    agent = Agent(
        model=get_strands_model(fast=fast),
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(standards=load_standards(), deployment_rules=deployment_rules()),
    )
    result = agent(prompt, structured_output_model=DesignProposal)
    if result.structured_output is None:
        raise RuntimeError("El modelo no devolvió una respuesta estructurada válida")
    return result.structured_output


def _build_design(requirement: Requirement, proposal: DesignProposal) -> Design:
    body = ""
    if proposal.diagram_mermaid:
        body = f"## Diagrama\n\n```mermaid\n{proposal.diagram_mermaid.strip()}\n```\n"
    return Design(
        run_id=requirement.run_id,
        summary=proposal.summary,
        components=proposal.components,
        decision=proposal.decision,
        risks=proposal.risks,
        verdict=proposal.verdict,
        standards_cited=proposal.standards_cited,
        open_questions=proposal.open_questions,
        deployment_spec=proposal.deployment_spec,
        body=body,
    )


AgentFn = Callable[[str], DesignProposal]


def generate_design(
    run_id: str,
    base_dir: str | Path = "runs",
    agent_fn: AgentFn | None = None,
    actor: str = ACTOR,
) -> Path:
    """Flujo completo de la Unit 03: lee el requerimiento aprobado, invoca al
    agente Arquitecto (o `agent_fn` en pruebas) y escribe `02-diseno.md`.

    Lanza `NotApprovedError` (de `runs.py`) si el requerimiento todavía no
    tiene aprobación humana `aprobado` — el agente nunca avanza sobre un
    artefacto no aprobado (regla de `contratos-agentes.md`).
    """
    store = RunStore(run_id, base_dir)
    requirement = store.read_input_for(2, Requirement)

    prompt = _build_prompt(requirement)
    invoke = agent_fn or _invoke_agent
    proposal = invoke(prompt)

    design = _build_design(requirement, proposal)
    return store.write(design, actor=actor)


def seed_run(store: RunStore) -> None:
    """Crea un requerimiento aprobado del caso demo, si no existe. Mismo
    patrón que `agents/developer.py:seed_run`, para poder probar el agente
    Arquitecto solo, sin el resto del flujo."""
    from .. import examples

    store.create()
    if not store.exists(Requirement):
        store.write(examples.requirement(store.run_id), actor="orquestador")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Agente Arquitecto de Delivery Crew")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--seed", action="store_true", help="crear requerimiento de ejemplo aprobado")
    args = parser.parse_args(argv)

    store = RunStore(args.run_id, args.runs_dir)
    if args.seed:
        seed_run(store)

    path = generate_design(args.run_id, args.runs_dir)
    print(f"Diseño escrito en: {path} (pendiente de aprobación)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
