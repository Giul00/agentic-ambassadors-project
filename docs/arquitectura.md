# Arquitectura

> Propuesta inicial, sujeta a cambios del equipo.

## Vista general

```mermaid
flowchart LR
    U[Usuario] -->|requerimiento| O[Orquestador]
    O --> A[Agente Arquitecto]
    A -->|02-diseno.md| H1{Aprueba arquitecto}
    H1 --> D[Agente Desarrollador]
    D -->|03-cambio.md + PR| H2{Aprueba desarrollador}
    H2 --> P[Agente Despliegue]
    P -->|04-despliegue.md| H3{Aprueba sysops}
    H3 --> X[Despliegue y verificación]
    X -->|falla| R[Rollback]
    X -->|ok| F[Reporte final]

    A -.-> BR[(Bedrock)]
    D -.-> BR
    P -.-> BR
    O -.-> AU[(Registro de auditoría)]
```

## Cuentas AWS
```mermaid
flowchart TB
    subgraph Dev1[Cuenta del desarrollador]
        T1[Desarrollo y pruebas]
    end
    subgraph Dev2[Cuenta del sysops]
        T2[Desarrollo y pruebas]
    end
    subgraph Dep[Cuenta del arquitecto: despliegue de la presentación]
        S[auth-service + DynamoDB]
        AG[Agentes en ejecución]
    end
    GH[(GitHub: código y runs/)]
    T1 --> GH
    T2 --> GH
    GH --> Dep
```

Los recursos de AWS no se comparten entre cuentas. Los artefactos entre agentes viajan por Git.

## Componentes
| Componente | Tecnología | Responsable |
|---|---|---|
| Orquestador | Strands Agents (grafo o flujo secuencial) con puntos de aprobación | Arquitecto |
| Agente Arquitecto | Strands Agents + Bedrock, base de estándares en Markdown | Arquitecto |
| Agente Desarrollador | Strands Agents + Bedrock, herramientas de archivos, Git y pruebas | Desarrollador |
| Agente Despliegue | Strands Agents + Bedrock, herramientas de CDK y CloudWatch | Sysops |
| Servicio demo `auth-service` | Lambda + API Gateway + DynamoDB | Desarrollador (código), Sysops (infraestructura) |
| Auditoría | Archivo JSONL por ejecución en `runs/<id>/audit.jsonl` | Arquitecto |

## Decisiones iniciales
1. **Artefactos en archivos Markdown versionados** y no en una base de datos. Es más simple, funciona entre cuentas y la auditoría queda gratis en Git.
2. **Aprobación humana como paso bloqueante** en el orquestador. Sin aprobación `aprobado` en el artefacto anterior, el siguiente agente no corre.
3. **Los agentes pueden ejecutarse localmente** durante el desarrollo, en cada cuenta, y solo el despliegue final va a la cuenta del arquitecto.
4. **Modelo por defecto:** `us.anthropic.claude-sonnet-4-6`, y Haiku 4.5 para pasos simples.
