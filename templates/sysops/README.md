# Catálogo de plantillas SysOps

Plantillas base parametrizadas para que el agente de Despliegue genere infraestructura y pipelines. No son copias de repositorios corporativos: se extrajeron los patrones de recursos, etapas y controles, y se eliminaron identificadores de cuentas, nombres de recursos, rutas internas y cualquier valor sensible.

## Fuentes relevadas localmente

| Perfil | Repositorio fuente | Patrón extraído |
|---|---|---|
| CI/CD | `template-ci-cd`, `template-ci-cd-ADQ`, `cf_alarms` | stages corporativos, jobs por ambiente y verificación posterior |
| Lambda | `cf_alarms`, `alertas-aws-health-teams`, `AmexDataExchangeRaw` | IAM mínimo, Lambda, logs, permisos y empaquetado S3 |
| S3 | `amexdataexchange_s3` | bucket parametrizado |
| Alarmas | `cf_alarms` | `AWS::CloudWatch::Alarm` parametrizada |
| ECS | `caseexecutor` | Fargate, ALB, logs, roles y health check |

## Uso por el agente

1. Lee el `Design` aprobado y clasifica los componentes.
2. Selecciona solo los perfiles compatibles del `catalog.yml`.
3. Completa los parámetros desde el diseño; nunca desde valores embebidos en la plantilla.
4. Ejecuta validación de CloudFormation y crea un change set.
5. Deja rutas, versión Git y resultado de validación en `04-despliegue.md`.

Los cambios en estas plantillas requieren revisión de Arquitectura y SysOps.
