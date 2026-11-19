# Agente SysOps / Despliegue

Este MVP implementa el primer límite de seguridad del agente de Despliegue: planifica, pero no ejecuta infraestructura. Consume el contrato tipado `Change` en `runs/<id>/03-cambio.md` y solo genera `Deployment` en `04-despliegue.md` cuando detecta una aprobación humana explícita.

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

El archivo de entrada usa YAML front matter y los campos del contrato compartido: `branch`, `pull_request_url`, `files_modified`, `test_result`, `test_summary` y `approval.status: aprobado`.

```powershell
python -m delivery_crew.agents.deployment demo-001 --target-account 123456789012
```

La siguiente iteración incorporará una herramienta de ejecución separada. Antes de que pueda ejecutar un despliegue deberá recibir: una aprobación de SysOps, la cuenta AWS de presentación esperada y los comandos CDK/destino aprobados. Así se evita que una entrada del repositorio active infraestructura por sí sola.

Además del plan, el agente genera `runs/<id>/generated/`: plantillas CloudFormation seleccionadas desde el catálogo, `.gitlab-ci-sysops.yml`, manifiesto y health check. El bundle queda en estado `pending_sysops_approval`; `cdk deploy` o un despliegue CloudFormation permanece bloqueado hasta completar el artefacto de aprobación.

