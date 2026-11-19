"""Ejecutor de despliegue (después de la aprobación humana de SysOps sobre 04-despliegue.md).

Despliega exactamente lo que se revisó:
  - el código del commit aprobado en la rama del agente Desarrollador (git archive, sin tocar el checkout),
  - la plantilla del bundle generado por el agente Despliegue (runs/<id>/generated/),
  - los parámetros del manifiesto (que salen del deployment_spec de Arquitectura).

Controles: la cuenta activa debe ser la del plan; se crea un change set y se registra qué
cambia antes de ejecutarlo; al terminar se corre la prueba de humo del servicio (smoke.json)
contra la URL desplegada. Nunca borra recursos (salvo un stack fallido que quedó vacío).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from ..contracts import Change, Deployment
from ..runs import NotApprovedError, RunStore

ACTOR = "agente-despliegue"
TERMINAL_OK = {"CREATE_COMPLETE", "UPDATE_COMPLETE"}
TERMINAL_BAD = {"CREATE_FAILED", "ROLLBACK_COMPLETE", "ROLLBACK_FAILED", "UPDATE_ROLLBACK_COMPLETE",
                "UPDATE_ROLLBACK_FAILED", "DELETE_COMPLETE", "DELETE_FAILED"}
POLL_SECONDS = 5
MAX_WAIT_SECONDS = 20 * 60


class DeployError(RuntimeError):
    """El despliegue no se pudo completar."""


@dataclass
class SmokeResult:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


# --- git -------------------------------------------------------------------

def _git(repo: Path, *args: str, binary: bool = False) -> Any:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True)
    if proc.returncode != 0:
        raise DeployError(f"git {' '.join(args)} falló: {proc.stderr.decode('utf-8', 'replace').strip()}")
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def package_from_branch(repo: Path, branch: str, source_path: str) -> tuple[bytes, str]:
    """Zip del paquete del servicio tal como está en la rama (sin pruebas). Devuelve (zip, commit)."""
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,120}", source_path) or ".." in source_path:
        raise DeployError(f"ruta de entregable no permitida: {source_path!r}")
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,120}", branch) or ".." in branch:
        raise DeployError(f"rama no permitida: {branch!r}")
    package = Path(source_path).name
    commit = _git(repo, "rev-parse", "--short=12", branch).strip()
    data = _git(repo, "archive", "--format=zip", f"--prefix={package}/", f"{commit}:{source_path}/{package}",
                binary=True)
    return data, commit


def read_from_branch(repo: Path, commit: str, path: str) -> str | None:
    try:
        return _git(repo, "show", f"{commit}:{path}")
    except DeployError:
        return None


# --- prueba de humo ---------------------------------------------------------

HttpFn = Callable[[str, str, bytes | None], tuple[int, str]]


def http_request(method: str, url: str, body: bytes | None) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - URL de la API recién desplegada
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def run_smoke(base_url: str, spec: dict[str, Any], http: HttpFn = http_request,
              on_step: Callable[[SmokeResult], None] = lambda r: None) -> list[SmokeResult]:
    """Ejecuta los pasos de smoke.json. Se detiene en el primer paso que falla."""
    saved: dict[str, str] = {}
    results: list[SmokeResult] = []
    for step in spec.get("steps", []):
        name = str(step.get("name", step.get("path", "")))
        path = str(step["path"])
        for key, value in saved.items():
            path = path.replace("{" + key + "}", value)
        body = json.dumps(step["body"]).encode("utf-8") if "body" in step else None
        try:
            status, text = http(str(step.get("method", "GET")).upper(), base_url.rstrip("/") + path, body)
        except Exception as exc:  # noqa: BLE001 - un error de red es un paso fallido
            result = SmokeResult(name, False, f"error de red: {exc}")
        else:
            expected = int(step.get("expect_status", 200))
            data: Any = None
            try:
                data = json.loads(text) if text else None
            except json.JSONDecodeError:
                pass
            problems = []
            if status != expected:
                problems.append(f"HTTP {status} (se esperaba {expected})")
            for key, value in (step.get("expect_json") or {}).items():
                actual = data.get(key) if isinstance(data, dict) else None
                if actual != value:
                    problems.append(f"{key}={actual!r} (se esperaba {value!r})")
            for var, field in (step.get("save") or {}).items():
                if isinstance(data, dict) and isinstance(data.get(field), str):
                    saved[var] = data[field]
                else:
                    problems.append(f"la respuesta no trae {field!r}")
            detail = "; ".join(problems) if problems else f"HTTP {status}"
            result = SmokeResult(name, not problems, detail)
        results.append(result)
        on_step(result)
        if not result.ok:
            break
    return results


# --- AWS ---------------------------------------------------------------------

Clients = Callable[[str], Any]


def boto_clients(region: str) -> Clients:
    import boto3

    session = boto3.session.Session(region_name=region)
    return lambda name: session.client(name)


def ensure_bucket(s3: Any, name: str, region: str, log: Callable[[str], None]) -> None:
    try:
        s3.head_bucket(Bucket=name)
        return
    except Exception:  # noqa: BLE001 - no existe o no es accesible: se intenta crear
        pass
    kwargs = {} if region == "us-east-1" else {"CreateBucketConfiguration": {"LocationConstraint": region}}
    s3.create_bucket(Bucket=name, **kwargs)
    s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
        "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
    s3.put_bucket_encryption(Bucket=name, ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
    log(f"Bucket de artefactos creado (privado y cifrado): {name}")


def _stack_status(cfn: Any, stack: str) -> str | None:
    try:
        return cfn.describe_stacks(StackName=stack)["Stacks"][0]["StackStatus"]
    except Exception as exc:  # noqa: BLE001
        if "does not exist" in str(exc):
            return None
        raise


def deploy_stack(cfn: Any, stack: str, template_body: str, parameters: dict[str, str], change_set_name: str,
                 log: Callable[[str], None], sleep: Callable[[float], None] = time.sleep,
                 poll_seconds: float = POLL_SECONDS, max_wait: float = MAX_WAIT_SECONDS) -> dict[str, str]:
    """Crea y ejecuta un change set, informa cada recurso y devuelve los Outputs del stack."""
    status = _stack_status(cfn, stack)
    if status == "ROLLBACK_COMPLETE":
        log(f"El stack {stack} quedó vacío tras un intento fallido; se elimina para recrearlo.")
        cfn.delete_stack(StackName=stack)
        _wait(cfn, stack, lambda s: s is None or s == "DELETE_COMPLETE", sleep, poll_seconds, max_wait)
        status = None
    if status and status.endswith("_IN_PROGRESS") and status != "REVIEW_IN_PROGRESS":
        raise DeployError(f"el stack {stack} está ocupado ({status}); reintente cuando termine")
    change_type = "CREATE" if status in (None, "REVIEW_IN_PROGRESS") else "UPDATE"

    cfn.create_change_set(
        StackName=stack, ChangeSetName=change_set_name, ChangeSetType=change_type, TemplateBody=template_body,
        Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
        Parameters=[{"ParameterKey": k, "ParameterValue": v} for k, v in sorted(parameters.items())],
    )
    while True:
        cs = cfn.describe_change_set(StackName=stack, ChangeSetName=change_set_name)
        if cs["Status"] in ("CREATE_COMPLETE", "FAILED"):
            break
        sleep(2)
    if cs["Status"] == "FAILED":
        reason = cs.get("StatusReason", "")
        if "didn't contain changes" in reason or "No updates" in reason:
            log("El change set no tiene cambios: la infraestructura ya está al día.")
            return _outputs(cfn, stack)
        raise DeployError(f"no se pudo crear el change set: {reason}")
    changes = [f"{c['ResourceChange']['Action']} {c['ResourceChange']['ResourceType']} "
               f"{c['ResourceChange']['LogicalResourceId']}" for c in cs.get("Changes", [])]
    log(f"Change set ({change_type}) con {len(changes)} cambios: " + "; ".join(changes))

    started = time.time()
    cfn.execute_change_set(StackName=stack, ChangeSetName=change_set_name)
    seen: set[str] = set()
    final = _wait(cfn, stack, lambda s: s in TERMINAL_OK or s in TERMINAL_BAD, sleep, poll_seconds, max_wait,
                  on_poll=lambda: _report_events(cfn, stack, started, seen, log))
    _report_events(cfn, stack, started, seen, log)
    if final not in TERMINAL_OK:
        reasons = _failure_reasons(cfn, stack, started)
        raise DeployError(f"el stack terminó en {final}: {reasons or 'sin detalle'}")
    log(f"Stack {stack}: {final}")
    return _outputs(cfn, stack)


def _wait(cfn: Any, stack: str, done: Callable[[str | None], bool], sleep: Callable[[float], None],
          poll_seconds: float, max_wait: float, on_poll: Callable[[], None] = lambda: None) -> str | None:
    deadline = time.monotonic() + max_wait
    while True:
        status = _stack_status(cfn, stack)
        on_poll()
        if done(status):
            return status
        if time.monotonic() > deadline:
            raise DeployError(f"el stack {stack} no terminó en {int(max_wait)} s (último estado: {status})")
        sleep(poll_seconds)


def _events_since(cfn: Any, stack: str, since: float) -> list[dict[str, Any]]:
    try:
        events = cfn.describe_stack_events(StackName=stack)["StackEvents"]
    except Exception:  # noqa: BLE001
        return []
    out = [e for e in events if e["Timestamp"].timestamp() >= since - 1]
    return list(reversed(out))


def _report_events(cfn: Any, stack: str, since: float, seen: set[str], log: Callable[[str], None]) -> None:
    for e in _events_since(cfn, stack, since):
        if e["EventId"] in seen or e["LogicalResourceId"] == stack:
            continue
        seen.add(e["EventId"])
        if e["ResourceStatus"].endswith("_COMPLETE") or e["ResourceStatus"].endswith("_FAILED"):
            reason = f": {e['ResourceStatusReason']}" if e["ResourceStatus"].endswith("_FAILED") else ""
            log(f"  {e['ResourceType']} {e['LogicalResourceId']}: {e['ResourceStatus']}{reason}")


def _failure_reasons(cfn: Any, stack: str, since: float) -> str:
    reasons = [f"{e['LogicalResourceId']}: {e.get('ResourceStatusReason', '')}"
               for e in _events_since(cfn, stack, since)
               if e["ResourceStatus"].endswith("_FAILED") and "cancelled" not in e.get("ResourceStatusReason", "")]
    return "; ".join(reasons[:3])


def _outputs(cfn: Any, stack: str) -> dict[str, str]:
    stack_info = cfn.describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack_info.get("Outputs", [])}


# --- flujo ---------------------------------------------------------------------

def execute_deployment(store: RunStore, repo: str | Path = ".", clients: Clients | None = None,
                       http: HttpFn = http_request, sleep: Callable[[float], None] = time.sleep,
                       poll_seconds: float = POLL_SECONDS) -> Deployment:
    repo = Path(repo).resolve()
    deployment = store.read(Deployment)
    if deployment.approval.status != "aprobado":
        raise NotApprovedError("04-despliegue.md no está aprobado por SysOps; no se ejecuta el despliegue")
    change = store.read(Change)
    if change.approval.status != "aprobado" or change.test_result != "passed":
        raise NotApprovedError("el cambio de código no está aprobado o sus pruebas no pasan")
    zips = [a for a in change.deliverables if a.kind == "zip"]
    if not zips:
        raise DeployError("el cambio no declara un entregable zip para la Lambda")
    if not (deployment.stack_name and deployment.project_name and deployment.environment):
        raise DeployError("el plan no tiene stack_name/project_name/environment (genérelo de nuevo)")
    manifest_path = store.path / "generated" / "manifest.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    template_path = store.path / "generated" / manifest["cloudformation_templates"][0]
    template_body = template_path.read_text(encoding="utf-8")

    log_lines: list[str] = []

    def log(message: str) -> None:
        log_lines.append(message)
        store.audit(ACTOR, "deploy_progress", text=message)

    def save(status: str, **fields: Any) -> Deployment:
        nonlocal deployment
        deployment = deployment.model_copy(update={"deployment_status": status,
                                                   "deployment_log": log_lines[-60:], **fields})
        store.write(deployment, actor=ACTOR)
        return deployment

    save("en_curso")
    clients = clients or boto_clients(deployment.region)
    try:
        account = clients("sts").get_caller_identity()["Account"]
        if account != deployment.target_account_id:
            raise DeployError(f"la cuenta activa es {account} y el plan aprobado es para {deployment.target_account_id}")
        log(f"Cuenta verificada: {account} ({deployment.region})")

        artifact = zips[0]
        data, commit = package_from_branch(repo, change.branch, artifact.source_path)
        package = Path(artifact.source_path).name
        log(f"Paquete {package}.zip desde {change.branch}@{commit} ({len(data) // 1024 or 1} KB, sin pruebas)")

        bucket = f"delivery-crew-artifacts-{account}-{deployment.region}"
        s3 = clients("s3")
        ensure_bucket(s3, bucket, deployment.region, log)
        key = f"{deployment.project_name}/{commit}/{package}.zip"
        s3.put_object(Bucket=bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        log(f"Artefacto subido a s3://{bucket}/{key}")

        parameters = {"ProjectName": deployment.project_name, "Environment": deployment.environment,
                      "ArtifactBucket": bucket, "ArtifactKey": key, **(manifest.get("parameter_overrides") or {})}
        change_set = f"dc-{commit}-{int(time.time())}"
        outputs = deploy_stack(clients("cloudformation"), deployment.stack_name, template_body, parameters,
                               change_set, log, sleep=sleep, poll_seconds=poll_seconds)
        url = outputs.get("ApiUrl")
        if not url:
            raise DeployError("el stack no devolvió la salida ApiUrl")
        log(f"API desplegada: {url}")

        smoke_text = read_from_branch(repo, commit, f"{artifact.source_path}/smoke.json")
        results: list[SmokeResult] = []
        if smoke_text:
            log("Prueba de humo contra la API desplegada:")
            results = run_smoke(url, json.loads(smoke_text), http=http,
                                on_step=lambda r: log(f"  {'✓' if r.ok else '✕'} {r.name}: {r.detail}"))
        else:
            log("El servicio no tiene smoke.json: se omite la prueba de humo.")
        healthy = all(r.ok for r in results)
        store.audit(ACTOR, "deploy_finished", healthy=healthy, url=url, commit=commit)
        return save("desplegado" if healthy else "fallido", endpoint_url=url, deployed_commit=commit,
                    health_check="ok" if healthy else "fallo")
    except Exception as exc:
        log(f"Error: {type(exc).__name__}: {exc}")
        save("fallido", health_check="fallo")
        raise
