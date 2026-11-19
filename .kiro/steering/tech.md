---
title: Stack técnico
inclusion: always
priority: medium
---

# Stack técnico

- Agentes: Strands Agents (Python).
- Modelo: Amazon Bedrock. Confirmar qué modelos están habilitados en la cuenta antes de fijar uno.
- Ejecución: AgentCore Runtime o AWS Lambda.
- Estado y artefactos: S3 y DynamoDB.
- Infraestructura como código: AWS CDK (o CloudFormation).
- Observabilidad: CloudWatch.
- Región: us-west-2.
- Cuenta: la temporal del workshop. Las credenciales se obtienen en Workshop Studio y se cargan como variables de entorno de cada persona.

## Estructura del repositorio
- `src/`: código de los agentes y del servicio demo.
- `infra/`: infraestructura como código.
- `docs/`: ADRs y diagramas.
- `aidlc/`: salida del planificador AI-DLC (plan, estado y unidades).

## Convenciones
- Una rama por persona. Cambios a `main` por pull request.
- Los contratos entre agentes están en `contratos-agentes.md` y no se cambian sin avisar a los tres.
