# Implementation Plan: Delivery Crew

**Generated:** 2026-11-19
**Complexity:** Standard
**Strategy:** Strategy D: Parallel Streams
**Team:** 3 personas: desarrollador, arquitecto de soluciones, sysops
**Target unit duration:** Relativa (S, M, L). El plazo real está por confirmar.

---

## Project Summary

Delivery Crew lleva un cambio de requerimiento a despliegue verificado con cuatro agentes (Arquitecto, Desarrollador, Despliegue y Orquestador) y aprobación humana en cada traspaso. Se descompuso en flujos paralelos, uno por persona, porque cada agente tiene un dueño distinto y cada persona trabaja en su propia cuenta AWS. Una unidad base compartida fija los contratos entre agentes, y una integración final conjunta despliega en la cuenta del arquitecto. Lee `.kiro/steering/product.md`, `tech.md`, `guardrails.md` y `contratos-agentes.md` antes de empezar.

---

## Unit Catalogue

### Unit 01: Base y contratos
**File:** `aidlc/units/01-base-y-contratos.md`
**Branch:** `feature/01-base-y-contratos`
**Description:** Estructura del código, esquemas de los artefactos entre agentes y configuración común de Strands y Bedrock.
**Key deliverables:**
- Esquemas de `01-requerimiento.md` a `04-despliegue.md` con ejemplos.
- Módulo común para invocar Bedrock y leer o escribir artefactos en `runs/`.
- Entorno Python reproducible y comprobación de Bedrock en cada cuenta.
**Dependencies:** None, puede empezar de inmediato
**Suggested assignee:** Los tres (el desarrollador integra)
**Estimated duration:** S
**Demo checkpoint:** Un script crea una ejecución de ejemplo y valida los cuatro artefactos contra sus esquemas.

### Unit 02: Servicio demo auth-service
**File:** `aidlc/units/02-servicio-demo-auth.md`
**Branch:** `feature/02-servicio-demo-auth`
**Description:** Servicio sintético de autorizaciones sobre el que se hará el cambio de la demo.
**Key deliverables:**
- `POST /authorize` con reglas simples y datos sintéticos.
- Pruebas unitarias.
**Dependencies:** Unit 01
**Suggested assignee:** Desarrollador
**Estimated duration:** S
**Demo checkpoint:** Una solicitud de ejemplo devuelve aprobada o rechazada con su código.

### Unit 03: Agente Arquitecto
**File:** `aidlc/units/03-agente-arquitecto.md`
**Branch:** `feature/03-agente-arquitecto`
**Description:** Agente que convierte un requerimiento en diseño, ADR y veredicto contra estándares.
**Key deliverables:**
- Base de estándares en Markdown (seguridad, datos, patrones).
- Agente que produce `02-diseno.md` con veredicto.
- Diagrama generado en Mermaid.
**Dependencies:** Unit 01
**Suggested assignee:** Arquitecto de soluciones
**Estimated duration:** M
**Demo checkpoint:** Dado el requerimiento del caso demo, produce un diseño válido y señala un incumplimiento si se le fuerza uno.

### Unit 04: Agente Desarrollador
**File:** `aidlc/units/04-agente-desarrollador.md`
**Branch:** `feature/04-agente-desarrollador`
**Description:** Agente que implementa un diseño aprobado sobre `auth-service`, con pruebas y pull request.
**Key deliverables:**
- Herramientas de lectura y escritura de archivos, ejecución de pruebas y Git.
- Agente que produce `03-cambio.md` con el pull request.
**Dependencies:** Unit 01, Unit 02
**Suggested assignee:** Desarrollador
**Estimated duration:** M
**Demo checkpoint:** A partir de un diseño de ejemplo, modifica el servicio y las pruebas pasan.

### Unit 05: Agente Despliegue e infraestructura
**File:** `aidlc/units/05-agente-despliegue.md`
**Branch:** `feature/05-agente-despliegue`
**Description:** Infraestructura como código del servicio demo y agente que planifica, despliega, verifica y revierte.
**Key deliverables:**
- Proyecto CDK parametrizado por cuenta y región (sin IDs fijos).
- Agente que produce `04-despliegue.md` con costo estimado y plan de rollback.
- Verificación de salud y rollback.
**Dependencies:** Unit 01
**Suggested assignee:** Sysops
**Estimated duration:** M
**Demo checkpoint:** Despliega y revierte una versión del servicio en una cuenta de prueba.

### Unit 06: Orquestador y aprobaciones
**File:** `aidlc/units/06-orquestador-aprobaciones.md`
**Branch:** `feature/06-orquestador-aprobaciones`
**Description:** Coordina a los agentes, bloquea cada paso hasta la aprobación humana y registra la auditoría.
**Key deliverables:**
- Flujo secuencial Arquitecto, Desarrollador, Despliegue.
- Compuerta de aprobación por línea de comandos.
- Registro de auditoría `audit.jsonl`.
**Dependencies:** Unit 01
**Suggested assignee:** Arquitecto de soluciones
**Estimated duration:** S
**Demo checkpoint:** Con agentes simulados, el flujo se detiene sin aprobación y avanza con ella.

### Unit 07: Integración y presentación
**File:** `aidlc/units/07-integracion-presentacion.md`
**Branch:** `feature/07-integracion-presentacion`
**Description:** Ejecución de punta a punta en la cuenta del arquitecto, medición y preparación de la presentación.
**Key deliverables:**
- Ejecución completa del caso demo con los tres agentes reales.
- Fallo provocado y rollback demostrado.
- Medición de tiempo y pasos manuales, y guion ensayado.
**Dependencies:** Units 02, 03, 04, 05, 06
**Suggested assignee:** Los tres
**Estimated duration:** M
**Demo checkpoint:** El caso demo corre completo, con aprobaciones, y el servicio desplegado devuelve el código 65.

---

## Dependency Graph

```
Unit 01 (base y contratos)
├── Unit 02 (servicio demo)            depende de 01
│   └── Unit 04 (agente desarrollador) depende de 01, 02
├── Unit 03 (agente arquitecto)        depende de 01, en paralelo con 02
├── Unit 05 (agente despliegue)        depende de 01, en paralelo con 02
└── Unit 06 (orquestador)              depende de 01, en paralelo con 02

Unit 07 (integración y presentación)   depende de 02, 03, 04, 05, 06
```

Flujos paralelos:

```
Desarrollador        Arquitecto            Sysops
─────────────        ──────────────        ──────────────
01 base (todos)      01 base (todos)       01 base (todos)
02 servicio demo     03 agente arq.        05 agente despliegue
04 agente dev.       06 orquestador
          └────────── 07 integración (todos) ──────────┘
```

---

## Execution Order and Assignment

| Wave | Unit | Assignee | Parallel With | Gate Before Starting |
|------|------|----------|---------------|----------------------|
| 1 | 01 Base y contratos | Los tres | N/A | Nada, empezar aquí |
| 2 | 02 Servicio demo | Desarrollador | 03, 05, 06 | Unit 01 en main |
| 2 | 03 Agente Arquitecto | Arquitecto | 02, 05, 06 | Unit 01 en main |
| 2 | 05 Agente Despliegue | Sysops | 02, 03, 06 | Unit 01 en main |
| 2 | 06 Orquestador | Arquitecto | 02, 05 | Unit 01 en main |
| 3 | 04 Agente Desarrollador | Desarrollador | 03, 05, 06 si siguen en curso | Unit 02 en main |
| 4 | 07 Integración | Los tres | N/A | Units 02 a 06 en main |

*Las unidades de una misma oleada no dependen entre sí y se pueden trabajar a la vez.*

El arquitecto tiene dos unidades en la oleada 2 (03 y 06). Si se retrasa, el orquestador (06) puede pasar al desarrollador una vez termine la unidad 02.

---

## Branch and Merge Guide

### Branch Naming

| Unit | Suggested Branch |
|------|-----------------|
| 01 Base y contratos | `feature/01-base-y-contratos` |
| 02 Servicio demo | `feature/02-servicio-demo-auth` |
| 03 Agente Arquitecto | `feature/03-agente-arquitecto` |
| 04 Agente Desarrollador | `feature/04-agente-desarrollador` |
| 05 Agente Despliegue | `feature/05-agente-despliegue` |
| 06 Orquestador | `feature/06-orquestador-aprobaciones` |
| 07 Integración | `feature/07-integracion-presentacion` |

### Merge Sequence

**Merge 1: Unit 01 → main**
- Who merges: Desarrollador
- Prerequisite: los tres revisaron y aceptaron los contratos
- Unblocks: unidades 02, 03, 05 y 06
- Notes: después de este merge los contratos no cambian sin acuerdo de los tres

**Merge 2: Units 02, 03, 05, 06 → main**
- Who merges: cada dueño, con revisión de otra persona
- Prerequisite: pruebas pasando y checkpoint verificado
- Unblocks: unidad 04 (tras la 02) y la unidad 07

**Merge 3: Unit 04 → main**
- Who merges: Desarrollador
- Prerequisite: unidad 02 en main
- Unblocks: unidad 07

**Merge 4: Unit 07 → main**
- Who merges: Sysops
- Prerequisite: ejecución de punta a punta correcta en la cuenta del arquitecto
- Unblocks: la presentación

---

### Merge Conflict Hotspots

| File / Area | Touched By | Owner for Conflict Resolution |
|-------------|-----------|-------------------------------|
| `.kiro/steering/contratos-agentes.md` y esquemas | Units 01, 03, 04, 05, 06 | Arquitecto |
| `requirements.txt` o `pyproject.toml` | Todas | Desarrollador |
| `infra/` | Units 02, 05 | Sysops |
| `aidlc/status.md` | Todas | Quien termine la unidad |

---

## Risk and Coordination Notes

- **Bedrock o permisos distintos entre cuentas:** cada uno verifica Bedrock en su cuenta en la unidad 01. El arquitecto verifica además permisos de despliegue (Lambda, API Gateway, DynamoDB, IAM) en su cuenta cuanto antes.
- **Credenciales temporales caducadas:** caducan en pocas horas. Tener a mano el procedimiento para renovarlas en Workshop Studio.
- **Contratos cambiantes:** son la frontera entre tres personas. Cualquier cambio se avisa a los tres.
- **Despliegue en vivo falla en la presentación:** preparar una ejecución grabada y los artefactos de `runs/` como plan B.
- **Alcance:** si falta tiempo, recortar a un recorrido mínimo (un caso fijo, sin reintentos ni casos alternativos) antes que dejar una unidad a medias.

---

## Definition of Done

Applies to every unit before it can be merged to main:

- [ ] All user stories from the unit file are implemented
- [ ] All NFRs from the unit file are met (with evidence)
- [ ] Unit tests written and passing
- [ ] Code reviewed by at least one other developer
- [ ] No regressions in dependent units
- [ ] Branch rebased on latest main before merge
- [ ] Demo checkpoint verified
- [ ] `aidlc/status.md` updated to reflect unit completion
- [ ] Sin credenciales ni datos reales en el código (ver `guardrails.md`)
