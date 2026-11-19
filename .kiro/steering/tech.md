---
title: Stack técnico
inclusion: always
priority: medium
---

# Stack técnico

- Agentes: Strands Agents (Python).
- Lenguaje: Python 3.11 o superior en todo el proyecto (agentes, servicio demo y CDK). Decidido por el equipo.
- Modelo: Amazon Bedrock en us-west-2. Verificado con llamadas reales en la cuenta de Tomás (328692565825):
  - Por defecto: `us.anthropic.claude-sonnet-4-6` (agentes principales).
  - Pasos rápidos y baratos: `us.anthropic.claude-haiku-4-5-20251001-v1:0`.
  - Alternativa: `us.amazon.nova-pro-v1:0`.
  - Usar el ID completo con prefijo `us.` (son inference profiles).
  - Cada integrante debe repetir la verificación en su propia cuenta.
- Ejecución: AgentCore Runtime o AWS Lambda.
- Estado y artefactos: S3 y DynamoDB.
- Infraestructura como código: AWS CDK (o CloudFormation).
- Observabilidad: CloudWatch.
- Región: us-west-2.
## Cuentas AWS
- Cada integrante tiene una cuenta AWS temporal distinta. Las credenciales se obtienen en Workshop Studio y se cargan como variables de entorno de cada persona.
- Desarrollo y pruebas: cada uno en su cuenta.
- Despliegue para la presentación: se hace en una sola cuenta, la del arquitecto de soluciones (cuenta de despliegue). El sysops prepara y ejecuta el despliegue con las credenciales de esa cuenta, y el arquitecto las provee.
- Los recursos de AWS no se comparten entre cuentas. Los artefactos entre agentes viajan por Git (carpeta `runs/` o ramas), no por S3 ni DynamoDB de otra cuenta.
- La infraestructura como código no debe tener IDs de cuenta fijos. Se parametriza la cuenta y la región para poder desplegar en cualquiera.

## Estructura del repositorio
- `src/`: código de los agentes y del servicio demo.
- `infra/`: infraestructura como código.
- `docs/`: ADRs y diagramas.
- `aidlc/`: salida del planificador AI-DLC (plan, estado y unidades).

## Convenciones
- Una rama por persona. Cambios a `main` por pull request.
- Los contratos entre agentes están en `contratos-agentes.md` y no se cambian sin avisar a los tres.
