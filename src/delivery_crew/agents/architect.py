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

from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field, model_validator
from strands import Agent

from ..bedrock import get_strands_model
from ..contracts import Design, Requirement, Verdict
from ..runs import RunStore

ACTOR = "agente-arquitecto"
STANDARDS_DIR = Path(__file__).resolve().parents[3] / "docs" / "estandares"


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

    @model_validator(mode="after")
    def _verdict_needs_support(self) -> "DesignProposal":
        if self.verdict != "aprobado" and not (self.standards_cited or self.open_questions):
            raise ValueError(
                "un veredicto distinto de 'aprobado' debe citar estándares (standards_cited) "
                "o dejar preguntas abiertas (open_questions)"
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
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(standards=load_standards()),
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
