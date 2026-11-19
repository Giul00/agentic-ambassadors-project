"""Código de origen de una ejecución: un servicio de este repositorio o un repo de GitHub.

Repo de GitHub (modo principal de la demo):
  - Se clona en runs/<id>/workspace/ al crear la ejecución. Solo HTTPS a github.com, solo dueños
    permitidos (DELIVERY_CREW_GITHUB_OWNERS), sin submódulos, con límite de tamaño.
  - Los tres agentes trabajan sobre ese clon. El Desarrollador hace su commit en la rama
    agente/<id> y, si hay GITHUB_TOKEN, la sube y abre un pull request.
  - El token se pasa a git como cabecera de una sola invocación (no queda en la configuración
    del clon) y se elimina de cualquier mensaje de error.

Correr las pruebas de un repo ejecuta su código en esta máquina: por eso la lista de dueños
permitidos. Las pruebas corren sin credenciales AWS (ver agents/sandbox.py).
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .contracts import Requirement
from .conventions import service_dir

DEFAULT_OWNERS = "Giul00,tomasdemarco"
MAX_REPO_BYTES = 20 * 1024 * 1024
_URL = re.compile(r"^https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/([A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$")
_REF = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


class WorkspaceError(RuntimeError):
    """El repositorio no se pudo preparar."""


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"


def allowed_owners() -> set[str]:
    raw = os.environ.get("DELIVERY_CREW_GITHUB_OWNERS", DEFAULT_OWNERS)
    return {o.strip().lower() for o in raw.split(",") if o.strip()}


def parse_repo_url(url: str) -> RepoRef:
    m = _URL.fullmatch((url or "").strip())
    if not m:
        raise WorkspaceError("la URL debe ser https://github.com/<dueño>/<repo>")
    owner, name = m.group(1), m.group(2)
    if name in (".", "..") or ".." in name:
        raise WorkspaceError("nombre de repositorio inválido")
    if owner.lower() not in allowed_owners():
        raise WorkspaceError(f"el dueño {owner!r} no está en la lista permitida ({', '.join(sorted(allowed_owners()))})")
    return RepoRef(owner, name)


def github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    return token.strip() if token and token.strip() else None


def _scrub(text: str) -> str:
    token = github_token()
    if token:
        text = text.replace(token, "***")
        text = text.replace(base64.b64encode(f"x-access-token:{token}".encode()).decode(), "***")
    return text


def _auth_args() -> list[str]:
    token = github_token()
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {basic}"]


def git(cwd: Path | None, *args: str, auth: bool = False, check: bool = True) -> str:
    cmd = ["git", *(_auth_args() if auth else []), "-c", "protocol.file.allow=never", *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env=env, timeout=180)
    if check and proc.returncode != 0:
        raise WorkspaceError(_scrub(f"git {args[0]} falló: {(proc.stderr or proc.stdout).strip()[:500]}"))
    return proc.stdout


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and ".git" not in f.parts)


def clone(repo: RepoRef, ref: str | None, dest: Path, source: str | None = None) -> str:
    """Clona (profundidad 1) en dest y devuelve el commit. `source` permite usar una ruta local en pruebas."""
    if ref is not None and (not _REF.fullmatch(ref) or ".." in ref):
        raise WorkspaceError("rama inválida")
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--depth", "1", "--single-branch", "--no-recurse-submodules"]
    if ref:
        args += ["--branch", ref]
    if source is not None:
        # Solo para pruebas: repositorio local.
        subprocess.run(["git", "clone", "--depth", "1", *(["--branch", ref] if ref else []),
                        f"file://{Path(source).resolve().as_posix()}", str(dest)],
                       check=True, capture_output=True)
    else:
        git(None, *args, repo.url, str(dest), auth=True)
    if (dest / ".gitmodules").exists():
        shutil.rmtree(dest, ignore_errors=True)
        raise WorkspaceError("el repositorio usa submódulos, que no están permitidos")
    if _size(dest) > MAX_REPO_BYTES:
        shutil.rmtree(dest, ignore_errors=True)
        raise WorkspaceError(f"el repositorio supera {MAX_REPO_BYTES // (1024 * 1024)} MB")
    return git(dest, "rev-parse", "--short=12", "HEAD").strip()


def detect_package(root: Path) -> str:
    """Paquete Python del servicio: una carpeta de primer nivel con handler.py que define lambda_handler."""
    candidates = []
    for child in sorted(root.iterdir()):
        handler = child / "handler.py"
        if child.is_dir() and not child.name.startswith(".") and handler.is_file():
            if "def lambda_handler" in handler.read_text(encoding="utf-8", errors="replace"):
                candidates.append(child.name)
    if not candidates:
        raise WorkspaceError("no se encontró un paquete con <paquete>/handler.py que defina lambda_handler")
    if len(candidates) > 1:
        raise WorkspaceError(f"hay más de un paquete con handler ({', '.join(candidates)}); indique uno")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", candidates[0]):
        raise WorkspaceError(f"nombre de paquete no soportado: {candidates[0]!r}")
    return candidates[0]


# --- ubicación del código de una ejecución --------------------------------------

def workspace_path(run_path: Path) -> Path:
    return run_path / "workspace"


@dataclass(frozen=True)
class CodeLocation:
    """Dónde está el código: repo git (root) y carpeta del servicio dentro de él (service_path)."""

    root: Path
    service_path: str  # relativa a root; "." si el servicio es la raíz del repo
    package: str
    repo: RepoRef | None = None

    @property
    def service_root(self) -> Path:
        return (self.root / self.service_path).resolve()


def locate(requirement: Requirement, run_path: Path, default_repo: Path) -> CodeLocation:
    if requirement.source_repo:
        root = workspace_path(run_path)
        if not (root / ".git").exists():
            raise WorkspaceError(f"falta el clon de {requirement.source_repo} en {root}")
        return CodeLocation(root, ".", detect_package(root), parse_repo_url(requirement.source_repo))
    path = service_dir(requirement.affected_service)
    package = Path(path).name
    return CodeLocation(Path(default_repo).resolve(), path, package)


def code_root(store, default_repo: Path) -> Path:
    """Raíz git del código de la ejecución (el clon si hay repo; si no, este repositorio)."""
    if not store.exists(Requirement):
        return Path(default_repo).resolve()
    req = store.read(Requirement)
    if req.source_repo:
        return locate(req, store.path, default_repo).root
    return Path(default_repo).resolve()


def prepare(requirement: Requirement, run_path: Path, source: str | None = None) -> tuple[str, str]:
    """Clona el repo de la ejecución. Devuelve (paquete, commit)."""
    assert requirement.source_repo
    repo = parse_repo_url(requirement.source_repo)
    commit = clone(repo, requirement.source_ref, workspace_path(run_path), source=source)
    return detect_package(workspace_path(run_path)), commit


# --- pull request ---------------------------------------------------------------

HttpJson = Callable[[str, str, dict[str, Any], str], tuple[int, dict[str, Any]]]


def _github_api(method: str, url: str, body: dict[str, Any], token: str) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(url, method=method, data=None if method == "GET" else json.dumps(body).encode(), headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
        "User-Agent": "delivery-crew"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - API de GitHub
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except json.JSONDecodeError:
            return exc.code, {}


def push_and_open_pr(location: CodeLocation, worktree: Path, branch: str, title: str, body: str,
                     api: HttpJson = _github_api) -> str:
    """Sube la rama del agente al repo y abre (o reutiliza) un pull request. Devuelve su URL."""
    token = github_token()
    if not token or location.repo is None:
        raise WorkspaceError("sin GITHUB_TOKEN: la rama queda local")
    base = git(location.root, "rev-parse", "--abbrev-ref", "HEAD").strip() or "main"
    git(worktree, "push", "--force-with-lease", location.repo.url, f"{branch}:refs/heads/{branch}", auth=True)
    url = f"https://api.github.com/repos/{location.repo.owner}/{location.repo.name}/pulls"
    status, data = api("POST", url, {"title": title, "head": branch, "base": base, "body": body,
                                     "maintainer_can_modify": True}, token)
    if status == 201 and data.get("html_url"):
        return str(data["html_url"])
    if status == 422:  # ya existe un PR para esa rama
        status2, existing = api("GET", f"{url}?head={location.repo.owner}:{branch}&state=open", {}, token)
        if status2 == 200 and isinstance(existing, list) and existing:
            return str(existing[0]["html_url"])
    raise WorkspaceError(_scrub(f"GitHub respondió {status} al abrir el PR: {str(data.get('message', ''))[:200]}"))


def merge_pull_request(location: CodeLocation, branch: str, pr_url: str, title: str,
                       api: HttpJson = _github_api) -> str:
    """Mergea el PR con squash, solo si su cabeza sigue siendo el commit aprobado. Devuelve el commit del merge."""
    token = github_token()
    if not token or location.repo is None:
        raise WorkspaceError("sin GITHUB_TOKEN: el cambio no se mergea")
    m = re.search(r"/pull/(\d+)/?$", pr_url or "")
    if not m:
        raise WorkspaceError(f"URL de pull request inválida: {pr_url!r}")
    approved = git(location.root, "rev-parse", branch).strip()
    url = f"https://api.github.com/repos/{location.repo.owner}/{location.repo.name}/pulls/{m.group(1)}/merge"
    status, data = api("PUT", url, {"merge_method": "squash", "sha": approved, "commit_title": title}, token)
    if status == 200 and data.get("merged"):
        return str(data.get("sha", ""))
    message = str(data.get("message", ""))[:200]
    if status == 409:
        raise WorkspaceError(f"la rama cambió después de la aprobación; no se mergea ({message})")
    if status == 405:
        raise WorkspaceError(f"GitHub no permite mergear el PR: {message}")
    raise WorkspaceError(_scrub(f"GitHub respondió {status} al mergear el PR: {message}"))
