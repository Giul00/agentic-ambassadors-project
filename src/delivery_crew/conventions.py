"""Convenciones compartidas entre Arquitectura, Desarrollo y SysOps.

Es la única fuente de estos nombres: el contrato los valida, el agente Desarrollador los
pasa al código y el agente Despliegue los traduce a parámetros de la plantilla.
Cambiarlos requiere acuerdo de los tres (ver .kiro/steering/contratos-agentes.md).
"""

from __future__ import annotations

import re
from pathlib import Path

# Claves permitidas en DeploymentComponent.configuration, por tipo de componente.
#   dynamodb.partition_key   nombre del atributo clave de partición (String). Obligatorio.
#   dynamodb.ttl_attribute   nombre del atributo TTL (Number, epoch en segundos). Opcional.
#   lambda.STORAGE_BACKEND   variable de entorno con el adaptador de persistencia:
#                            "dynamodb" en AWS, "memory" en pruebas
CONFIGURATION_KEYS: dict[str, frozenset[str]] = {
    "dynamodb": frozenset({"partition_key", "ttl_attribute"}),
    "lambda": frozenset({"STORAGE_BACKEND"}),
}
STORAGE_BACKENDS = ("dynamodb", "memory")

# Valores aceptados: se usan como parámetros de CloudFormation y en el pipeline,
# así que solo se permiten caracteres que no necesitan escape.
SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Variable de entorno con el nombre de la tabla. La inyecta siempre la infraestructura.
TABLE_ENV = "TABLE_NAME"

# Servicios: cada uno vive en services/<paquete>/ con el paquete Python <paquete>/ adentro
# y su handler de Lambda en <paquete>/handler.py:lambda_handler.
SERVICES_DIR = "services"
_SERVICE_NAME = re.compile(r"^[a-z][a-z0-9-]{1,40}$")


def service_package(service: str) -> str:
    """'merchants-api' -> 'merchants_api'."""
    if not _SERVICE_NAME.fullmatch(service):
        raise ValueError(f"nombre de servicio inválido: {service!r}")
    return service.replace("-", "_")


def service_dir(service: str) -> str:
    """Ruta relativa a la raíz del repositorio: 'services/merchants_api'."""
    return f"{SERVICES_DIR}/{service_package(service)}"


def lambda_entrypoint(service: str) -> str:
    return f"{service_package(service)}.handler.lambda_handler"


def build_command(service: str) -> str:
    """Informativo: el empaquetado real es fijo y nunca ejecuta un comando tomado de un artefacto."""
    package = service_package(service)
    return f"python -m zipfile -c {package}.zip {package}"


def available_services(repo_root: str | Path) -> list[str]:
    """Servicios presentes en services/ (con su handler de Lambda)."""
    root = Path(repo_root) / SERVICES_DIR
    if not root.is_dir():
        return []
    found = []
    for child in sorted(root.iterdir()):
        if (child / child.name / "handler.py").is_file():
            found.append(child.name.replace("_", "-"))
    return found


# Compatibilidad: el servicio original de la demo.
SERVICE_DIR = service_dir("auth-service")
LAMBDA_ENTRYPOINT = lambda_entrypoint("auth-service")
LAMBDA_BUILD_COMMAND = build_command("auth-service")
