"""Convenciones compartidas entre Arquitectura, Desarrollo y SysOps.

Es la única fuente de estos nombres: el contrato los valida, el agente Desarrollador los
pasa al código y el agente Despliegue los traduce a parámetros de la plantilla.
Cambiarlos requiere acuerdo de los tres (ver .kiro/steering/contratos-agentes.md).
"""

from __future__ import annotations

import re

# Claves permitidas en DeploymentComponent.configuration, por tipo de componente.
#   dynamodb.partition_key   nombre del atributo clave de partición (String)
#   dynamodb.ttl_attribute   nombre del atributo TTL (Number, epoch en segundos)
#   lambda.FREQUENCY_STORE   variable de entorno: "dynamodb" en AWS, "memory" en pruebas
CONFIGURATION_KEYS: dict[str, frozenset[str]] = {
    "dynamodb": frozenset({"partition_key", "ttl_attribute"}),
    "lambda": frozenset({"FREQUENCY_STORE"}),
}

# Valores aceptados: se usan como parámetros de CloudFormation y en el pipeline,
# así que solo se permiten caracteres que no necesitan escape.
SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Variable de entorno con el nombre de la tabla. La inyecta siempre la infraestructura.
FREQUENCY_TABLE_ENV = "FREQUENCY_TABLE_NAME"

# Servicio demo.
SERVICE_DIR = "services/auth_service"
LAMBDA_ENTRYPOINT = "auth_service.handler.lambda_handler"
# Informativo: el pipeline usa este mismo empaquetado fijo y nunca ejecuta un comando
# tomado de un artefacto.
LAMBDA_BUILD_COMMAND = "python -m zipfile -c auth-service.zip auth_service"
