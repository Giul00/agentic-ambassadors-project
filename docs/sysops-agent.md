# Agente SysOps / Despliegue

Este MVP implementa el primer límite de seguridad del agente de Despliegue: planifica, pero no ejecuta infraestructura. Consume el contrato tipado `Change` en `runs/<id>/03-cambio.md` y solo genera `Deployment` en `04-despliegue.md` cuando detecta una aprobación humana explícita.

## Generación por contrato

El catálogo no limita a SysOps a copiar perfiles: es una biblioteca de patrones y controles. Con
`--generate-with-bedrock`, el agente recibe el `deployment_spec`, los artefactos entregados por
Desarrollo y los templates revisados como contexto; genera un `cloudformation/stack.yml` y un
`.gitlab-ci-sysops.yml` propios para la arquitectura solicitada. Esto permite proponer recursos
nuevos, por ejemplo RDS, SQS o EventBridge, sin que exista un perfil cerrado previo.

La propuesta se rechaza si no tiene YAML válido, recursos CloudFormation, las etapas corporativas
mínimas o despliegues manuales. Nunca se despliega desde el agente: el bundle sigue pendiente de
aprobación de SysOps y el pipeline conserva change set, aprobaciones y rollback.

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

El agente consume `deployment_spec` aprobado en `02-diseno.md` y los `deliverables` de `03-cambio.md`. El diseño define componentes, red, datos, health check, rollback y observabilidad; Desarrollo declara cómo construir cada artefacto. Si falta un componente, artefacto o perfil homologado, el agente se detiene sin generar IaC parcial.

```powershell
python -m delivery_crew.agents.deployment demo-001 --target-account 123456789012
```

Para generar IaC propio con Bedrock:

```powershell
python -m delivery_crew.agents.deployment demo-001 --target-account 123456789012 --generate-with-bedrock
```

La siguiente iteración incorporará una herramienta de ejecución separada. Antes de que pueda ejecutar un despliegue deberá recibir: una aprobación de SysOps, la cuenta AWS de presentación esperada y los comandos CDK/destino aprobados. Así se evita que una entrada del repositorio active infraestructura por sí sola.

Además del plan, el agente genera `runs/<id>/generated/`: plantillas CloudFormation seleccionadas desde el catálogo, `.gitlab-ci-sysops.yml`, manifiesto y health check. El bundle queda en estado `pending_sysops_approval`; `cdk deploy` o un despliegue CloudFormation permanece bloqueado hasta completar el artefacto de aprobación.

