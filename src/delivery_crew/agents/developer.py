"""Agente Desarrollador (unidad 04).

Toma un diseño aprobado (02-diseno.md), implementa el cambio en auth-service dentro de una
copia aislada del repositorio (git worktree), ejecuta las pruebas, reintenta si fallan y deja
el resultado en 03-cambio.md con aprobación pendiente.

Uso:
  python -m delivery_crew.agents.developer --run-id demo-dev --seed
  python -m delivery_crew.agents.developer --run-id demo-dev --fresh      # repetir desde cero
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Callable

from ..contracts import Change, DeployableArtifact, Design, Requirement
from ..conventions import FREQUENCY_TABLE_ENV, LAMBDA_BUILD_COMMAND, LAMBDA_ENTRYPOINT, SERVICE_DIR
from ..runs import NotApprovedError, RunStore
from .narration import Narrator
from .sandbox import Sandbox, SandboxError, TestRun

ACTOR = "agente-desarrollador"
WORKTREES_DIR = ".worktrees"
MAX_DIFF_CHARS = 30_000
GIT_AUTHOR = ["-c", "user.name=Agente Desarrollador", "-c", "user.email=agente-desarrollador@delivery-crew.local"]

# Un "agente" es cualquier función que recibe un prompt y devuelve su resumen en texto.
AgentFn = Callable[[str], str]
AgentFactory = Callable[[Sandbox], AgentFn]


class DeveloperError(RuntimeError):
    """El agente no pudo producir un cambio."""


SYSTEM_PROMPT = textwrap.dedent("""
    Eres el agente Desarrollador de Delivery Crew, en una empresa de adquirencia de pagos.
    Implementas cambios en el servicio auth-service siguiendo un diseño ya aprobado por el arquitecto.

    Herramientas: list_files, read_file, write_file y run_tests. Las rutas son relativas a la
    carpeta del servicio (por ejemplo, "auth_service/rules.py" o "tests/test_auth_rules.py").

    Reglas obligatorias:
    1. Antes de escribir, lee los archivos relevantes (al menos README.md, auth_service/rules.py,
       auth_service/models.py, auth_service/handler.py y las pruebas existentes).
    2. Implementa solo lo que pide el diseño y el requerimiento. No cambies el comportamiento existente
       que no esté relacionado.
    3. Escribe al menos una prueba por cada criterio de aceptación, más los casos borde.
    4. Las pruebas no pueden usar AWS ni red. Si el diseño usa un servicio de AWS (por ejemplo DynamoDB),
       define una interfaz, una implementación en memoria para pruebas y otra con boto3 para producción,
       y elige la implementación por variable de entorno. Importa boto3 solo dentro de la implementación real.
       La implementación real también se prueba: con un cliente o tabla falsos en memoria que simulen las
       operaciones que usas (incluidas las condiciones), sin red.
    5. Nada de datos reales de tarjetas ni secretos en el código.
    6. write_file reemplaza el archivo completo: escribe siempre el contenido entero.
    7. Ejecuta run_tests y corrige hasta que todas las pruebas pasen. Las pruebas existentes no se pueden
       modificar: fijan el comportamiento actual. Si tu cambio rompe una, corrige el código.
    8. No cambies el contrato HTTP del servicio salvo que el requerimiento lo pida: un rechazo de negocio
       (cualquier response_code distinto de 00) responde HTTP 200 con approved=false. Tampoco cambies
       mensajes ni códigos existentes.
    9. Si implementas una ventana de tiempo, pruébala con un reloj simulado en ambas implementaciones,
       incluido el caso de solicitudes espaciadas por debajo del límite, que nunca deben rechazarse aunque
       se sostengan en el tiempo. Renovar el vencimiento en cada solicitud convierte la ventana en un
       bloqueo permanente: evítalo.
    10. Al terminar responde, en español y en pocas líneas: qué cambiaste, qué archivos, qué variables
       de entorno o recursos de infraestructura nuevos necesita el despliegue, y el resultado de las pruebas.
""").strip()


# --- git -------------------------------------------------------------------

def _git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode != 0:
        raise DeveloperError(f"git {' '.join(args)} falló: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout


def branch_name(run_id: str) -> str:
    return f"agente/{run_id}"


def create_worktree(repo: Path, run_id: str, fresh: bool = False, base: str = "HEAD") -> tuple[Path, str]:
    path = repo / WORKTREES_DIR / run_id
    branch = branch_name(run_id)
    branch_exists = bool(_git(repo, "branch", "--list", branch).strip())
    if fresh:
        if path.exists():
            _git(repo, "worktree", "remove", "--force", str(path), check=False)
            shutil.rmtree(path, ignore_errors=True)
        _git(repo, "worktree", "prune", check=False)
        if branch_exists:
            _git(repo, "branch", "-D", branch)
            branch_exists = False
    if path.exists() or branch_exists:
        raise DeveloperError(
            f"ya existe la copia de trabajo o la rama {branch!r} de esta ejecución; use --fresh para repetir"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "-b", branch, str(path), base)
    return path, branch


def stage_and_diff(worktree: Path) -> tuple[list[str], str]:
    _git(worktree, "add", "-A", "--", SERVICE_DIR)
    names = [n for n in _git(worktree, "diff", "--cached", "--name-only").splitlines() if n.strip()]
    diff = _git(worktree, "diff", "--cached", "--stat") + "\n" + _git(worktree, "diff", "--cached")
    return names, diff


# --- prompt ----------------------------------------------------------------

def deployment_section(design: Design) -> str:
    """Restricciones de infraestructura que el código debe respetar al pie de la letra."""
    spec = design.deployment_spec
    if spec is None:
        return ""
    lines = [
        "## Especificación de despliegue de Arquitectura (obligatoria)",
        "La infraestructura se genera con estos valores exactos. Si tu código usa otros nombres, "
        "fallará en AWS aunque las pruebas pasen.",
    ]
    for comp in spec.components:
        config = ", ".join(f"{k}={v}" for k, v in sorted(comp.configuration.items())) or "sin configuración"
        lines.append(f"- {comp.name} ({comp.kind}): {config}")
        if comp.kind == "dynamodb":
            if "partition_key" in comp.configuration:
                lines.append(f"  - La clave de partición de la tabla se llama exactamente "
                             f"'{comp.configuration['partition_key']}' (tipo String).")
            if "ttl_attribute" in comp.configuration:
                lines.append(f"  - El atributo TTL se llama exactamente '{comp.configuration['ttl_attribute']}' "
                             "(Number, epoch en segundos).")
            lines.append(f"  - El nombre de la tabla llega en la variable de entorno {FREQUENCY_TABLE_ENV}.")
            lines.append("  - El rol de la Lambda tiene permiso de dynamodb:GetItem, PutItem y UpdateItem.")
        if comp.kind == "lambda":
            for key, value in sorted(comp.configuration.items()):
                lines.append(f"  - La Lambda recibe la variable de entorno {key}={value}.")
            lines.append(f"  - Handler: {LAMBDA_ENTRYPOINT}.")
    return "\n".join(lines)


def build_deliverables(design: Design) -> list[DeployableArtifact]:
    """Un zip del servicio por cada componente Lambda del diseño. Valores fijos, no del modelo."""
    if design.deployment_spec is None:
        return []
    return [
        DeployableArtifact(component=comp.name, kind="zip", source_path=SERVICE_DIR,
                           build_command=LAMBDA_BUILD_COMMAND, entrypoint=LAMBDA_ENTRYPOINT)
        for comp in design.deployment_spec.components if comp.kind == "lambda"
    ]


def build_prompt(req: Requirement, design: Design, feedback: str | None = None) -> str:
    criteria = "\n".join(f"- {c}" for c in req.acceptance_criteria)
    components = "\n".join(f"- {c}" for c in design.components)
    risks = "\n".join(f"- {r}" for r in design.risks) or "- (ninguno)"
    review = ""
    if feedback:
        review = (
            "\n\n## Revisión humana del intento anterior: RECHAZADO\n"
            "Un intento anterior de este cambio fue rechazado en la revisión con este motivo. "
            "Tu implementación debe resolverlo explícitamente y cubrirlo con pruebas:\n"
            f"> {feedback}"
        )
    prompt = textwrap.dedent(f"""
        Implementa este cambio en {req.affected_service}.

        ## Requerimiento: {req.title}
        {req.description}

        Criterios de aceptación:
        {criteria}

        ## Diseño aprobado por {design.approval.by}
        Resumen: {design.summary}
        Decisión: {design.decision}
        Componentes:
        {components}
        Riesgos:
        {risks}

        {design.body}
    """).strip()
    infra = deployment_section(design)
    if infra:
        prompt += "\n\n" + infra
    return prompt + review


def retry_prompt(result: TestRun) -> str:
    return (
        "Las pruebas fallan después de tu cambio. Corrige el código o las pruebas (sin borrar pruebas "
        "válidas) y vuelve a ejecutar run_tests.\n\n"
        f"Resumen: {result.summary}\n\nSalida:\n{result.output[-4000:]}"
    )


# --- agente real (Strands + Bedrock) -----------------------------------------

def strands_agent_factory(sandbox: Sandbox) -> AgentFn:
    from strands import Agent, tool

    from ..bedrock import get_strands_model

    def guard(fn: Callable[[], str]) -> str:
        try:
            return fn()
        except SandboxError as exc:
            return f"ERROR: {exc}"

    @tool
    def list_files() -> str:
        """Lista los archivos de la carpeta del servicio (rutas relativas)."""
        return "\n".join(sandbox.list_files())

    @tool
    def read_file(path: str) -> str:
        """Lee un archivo del servicio.

        Args:
            path: ruta relativa a la carpeta del servicio, por ejemplo auth_service/rules.py
        """
        return guard(lambda: sandbox.read_file(path))

    @tool
    def write_file(path: str, content: str) -> str:
        """Crea o reemplaza por completo un archivo del servicio.

        Args:
            path: ruta relativa a la carpeta del servicio, por ejemplo auth_service/frequency.py
            content: contenido completo del archivo
        """
        return guard(lambda: f"escrito: {sandbox.write_file(path, content)}")

    @tool
    def run_tests() -> str:
        """Ejecuta todas las pruebas del servicio con pytest y devuelve el resultado."""
        result = sandbox.run_tests()
        status = "PASAN" if result.passed else "FALLAN"
        return f"{status}: {result.summary}\n\n{result.output[-4000:]}"

    narrator = Narrator(lambda text: sandbox.emit("agent_message", {"text": text}))
    agent = Agent(
        model=get_strands_model(max_tokens=16000, temperature=0.2),
        tools=[list_files, read_file, write_file, run_tests],
        system_prompt=SYSTEM_PROMPT,
        callback_handler=narrator,
        name="agente-desarrollador",
    )

    def run(prompt: str) -> str:
        try:
            return str(agent(prompt)).strip()
        finally:
            narrator.flush()

    return run


# --- flujo -----------------------------------------------------------------

def run_developer(store: RunStore, repo: str | Path, agent_factory: AgentFactory = strands_agent_factory,
                  max_attempts: int = 3, fresh: bool = False, push: bool = False,
                  log: Callable[[str], None] = lambda msg: None) -> Change:
    repo = Path(repo).resolve()

    # Compuertas: requerimiento y diseño aprobados por personas.
    store.read_input_for(2, Requirement)
    design = store.read_input_for(3, Design)
    req = store.read(Requirement)
    previous = store.read(Change) if store.exists(Change) else None
    if previous is not None and not fresh:
        raise DeveloperError("esta ejecución ya tiene 03-cambio.md; use --fresh para repetir")
    feedback = previous.approval.reason if previous and previous.approval.status == "rechazado" else None

    store.audit(ACTOR, "developer_started", feedback=feedback)
    worktree, branch = create_worktree(repo, store.run_id, fresh=fresh)
    log(f"Copia de trabajo: {worktree} (rama {branch})")

    def on_event(action: str, details: dict) -> None:
        store.audit(ACTOR, action, **details)
        if action == "tool_write_file":
            log(f"  escribió {details['path']}")
        elif action == "tool_run_tests":
            log(f"  pruebas: {details['summary']}")

    sandbox = Sandbox(worktree, SERVICE_DIR, on_event=on_event)
    agent = agent_factory(sandbox)

    prompt = build_prompt(req, design, feedback)
    if feedback:
        log(f"Incluye el motivo del rechazo anterior: {feedback}")
    summaries: list[str] = []
    result = TestRun(False, "sin ejecutar", "")
    for attempt in range(1, max_attempts + 1):
        log(f"Intento {attempt}/{max_attempts}...")
        summaries.append(agent(prompt))
        result = sandbox.run_tests()  # verificación independiente de lo que diga el agente
        store.audit(ACTOR, "verification", attempt=attempt, passed=result.passed, summary=result.summary)
        if result.passed:
            break
        prompt = retry_prompt(result)

    files, diff = stage_and_diff(worktree)
    if not files:
        store.audit(ACTOR, "developer_failed", reason="el agente no modificó archivos")
        raise DeveloperError("el agente no modificó ningún archivo")

    if result.passed:
        _git(worktree, *GIT_AUTHOR, "commit", "-q", "-m", f"{req.title} ({store.run_id})")
        if push:
            _git(worktree, "push", "-u", "origin", branch)
            store.audit(ACTOR, "branch_pushed", branch=branch)

    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n... (diff truncado)"
    body = "\n\n".join([
        "## Resumen del agente",
        summaries[-1] or "(sin resumen)",
        f"## Pruebas\n\nIntentos: {len(summaries)} de {max_attempts}. Resultado: {result.summary}",
        f"## Diff\n\n```diff\n{diff.strip()}\n```",
    ])
    change = Change(
        run_id=store.run_id,
        branch=branch,
        pull_request_url=None,  # sin token de GitHub; el PR se abre a mano desde la rama
        files_modified=files,
        test_result="passed" if result.passed else "failed",
        test_summary=result.summary,
        deliverables=build_deliverables(design),
        body=body,
    )
    store.write(change, actor=ACTOR)
    store.audit(ACTOR, "developer_finished", passed=result.passed, attempts=len(summaries))
    return change


# --- CLI -------------------------------------------------------------------

def seed_run(store: RunStore) -> None:
    """Crea requerimiento y diseño aprobados del caso demo, si no existen."""
    from .. import examples

    store.create()
    if not store.exists(Requirement):
        store.write(examples.requirement(store.run_id), actor="orquestador")
    if not store.exists(Design):
        store.write(examples.design(store.run_id), actor="agente-arquitecto")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agente Desarrollador de Delivery Crew")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--repo", default=".", help="raíz del repositorio git")
    parser.add_argument("--seed", action="store_true", help="crear requerimiento y diseño de ejemplo aprobados")
    parser.add_argument("--fresh", action="store_true", help="descartar la copia de trabajo y la rama anteriores de esta ejecución")
    parser.add_argument("--push", action="store_true", help="subir la rama a origin si las pruebas pasan")
    parser.add_argument("--max-attempts", type=int, default=3)
    args = parser.parse_args(argv)

    store = RunStore(args.run_id, args.runs_dir)
    if args.seed:
        seed_run(store)
    try:
        change = run_developer(store, args.repo, max_attempts=args.max_attempts, fresh=args.fresh,
                               push=args.push, log=print)
    except NotApprovedError as exc:
        print(f"Bloqueado: {exc}")
        return 2
    except (DeveloperError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 1

    print(f"\nResultado: pruebas {change.test_result} ({change.test_summary})")
    print(f"Rama: {change.branch}")
    print("Archivos:\n" + "\n".join(f"  {f}" for f in change.files_modified))
    print(f"Artefacto: {store.path / Change.FILENAME} (pendiente de aprobación)")
    return 0 if change.test_result == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
