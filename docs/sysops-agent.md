# Agente SysOps / Despliegue

Este MVP implementa el primer límite de seguridad del agente de Despliegue: planifica, pero no ejecuta infraestructura. Consume el contrato `runs/<id>/03-cambio.md` y solo genera `04-despliegue.md` cuando detecta una aprobación humana explícita.

## Flujo

```text
03-cambio.md aprobado
        │
        ▼
validación de contrato ──rechazado──> termina sin escribir un plan
        │
        ▼
04-despliegue.md (pendiente de aprobación SysOps)
        │
        ▼
cdk synth/diff → aprobación → deploy → health check → rollback si corresponde
```

## Uso local

El archivo de entrada debe contener los campos del contrato: `rama`, `enlace al pull request`, `archivos modificados`, `resultado de las pruebas` y `estado de aprobación humana: aprobado`.

```powershell
$env:PYTHONPATH = "src"
python -m deployment_agent.cli demo-001
```

La siguiente iteración incorporará una herramienta de ejecución separada. Antes de que pueda ejecutar un despliegue deberá recibir: una aprobación de SysOps, la cuenta AWS de presentación esperada y los comandos CDK/destino aprobados. Así se evita que una entrada del repositorio active infraestructura por sí sola.

El stack inicial del caso demo vive en `infra/`: API Gateway, Lambda y DynamoDB con TTL. Se valida con `cdk synth` y `cdk diff`; `cdk deploy` permanece bloqueado hasta completar el artefacto de aprobación.

