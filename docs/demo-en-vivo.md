# Demo en vivo

![Panel durante una ejecución](img/panel-en-vivo.png)

**Historia:** "Tengo este código y quiero llevarlo a producción siguiendo los lineamientos de la empresa."
El repo de partida es [api-demo-agentic-ambassadors](https://github.com/tomasdemarco/api-demo-agentic-ambassadors): un ABM de comercios con puertos y adaptadores, **sin base de datos**.

| Etapa | Quién | Qué pasa |
|---|---|---|
| 1 | Persona | Pega la URL del repo y describe el pedido |
| 2 | Agente Arquitecto | Lee el código, aplica ARQ-08 (DynamoDB) y ARQ-09 (API Gateway + Lambda) y declara la infraestructura |
| 3 | Agente Desarrollador | Escribe el adaptador DynamoDB detrás del puerto, con pruebas; abre el pull request |
| — | Persona aprueba el cambio | El PR se **mergea** en `main` (squash, solo si la rama no cambió tras la aprobación) |
| 4 | Agente SysOps | Plan y bundle de CloudFormation con la plantilla homologada y los valores del diseño |
| 5 | Ejecutor (opcional, `--deploy`) | Change set, despliegue y prueba de humo contra la URL |

Todo corre en la laptop de quien presenta; los agentes usan Bedrock.

## Antes de presentar

1. **Credenciales AWS nuevas** (las del workshop vencen en algunas horas), cargadas en la terminal 1.
2. **Token de GitHub** *fine-grained*, solo para el repo de la demo, con permisos **Contents: read and write** y **Pull requests: read and write**. Sin token, la rama queda local y no hay PR ni merge.
3. Comprobar Bedrock: `.\.venv\Scripts\python.exe -m delivery_crew.check_env`
4. **Plan B:** dejar en el panel una ejecución completa de ensayo.

## Levantar

**Terminal 1: API y agentes**
```powershell
cd agentic-ambassadors-project
$env:GITHUB_TOKEN = "<token fine-grained>"      # opcional: PR y merge
.\.venv\Scripts\python.exe -m delivery_crew.api  # agregar --deploy solo en una cuenta con permisos completos
```
Al arrancar indica la cuenta y si el despliegue real está activado.

**Terminal 2: panel**
```powershell
cd agentic-ambassadors-project\panel
npm run dev
```
Abrir http://localhost:5173 → **+ Nueva ejecución** → pestaña **Repositorio de GitHub** → **Cargar ejemplo** → **Lanzar agentes**.

## Guion (unos 5 minutos)

1. **Pedido:** URL del repo y "Desplegar la API de comercios con persistencia real".
2. **Arquitecto (~40 s):** se ve cómo lee el código y elige DynamoDB por lineamiento. Mostrar `deployment_spec` (tabla con `partition_key`, `STORAGE_BACKEND=dynamodb`). **Aprobar.**
3. **Desarrollador (~2-3 min):** se ve qué archivos lee y escribe y cada corrida de pruebas. Mostrar el **diff** y el **PR** en GitHub.
   - Compuerta humana: **Rechazar** con un motivo y presionar **Que el agente lo rehaga con el motivo**.
   - Al **aprobar**, el PR se mergea en `main` y aparece en la actividad.
4. **SysOps (~1 s):** plan con el stack `dc-merchants-api-qa` y parámetros tomados del diseño. **Aprobar.**
5. **Cierre:** tiempo total, aprobaciones humanas, auditoría, y el PR mergeado en GitHub.

Para mostrar un rechazo del Arquitecto: pedir *"Guardar el número de tarjeta del titular de cada comercio"* (debe salir rechazado por ARQ-01).

## Si algo falla

| Síntoma | Qué hacer |
|---|---|
| "no se pudo conectar con la API" | La terminal 1 no está corriendo |
| `AttributeError` u otro error raro al empezar | Hay una API vieja corriendo: cerrarla (`Ctrl+C`) y volver a levantarla |
| `ExpiredToken` / `UnrecognizedClient` | Renovar credenciales, reiniciar la terminal 1 y **Reanudar agentes** |
| "dueño no está en la lista permitida" | Usar un repo de `tomasdemarco` o `Giul00` (o ajustar `DELIVERY_CREW_GITHUB_OWNERS`) |
| "sin GITHUB_TOKEN" | Esperado si no se cargó el token: sigue sin PR ni merge |
| "la rama cambió después de la aprobación" | Alguien empujó a la rama del agente: revisar y repetir |

## Límites

- El servicio debe ser un paquete Python con `<paquete>/handler.py:lambda_handler` y pruebas con `pytest`; sin dependencias externas (solo biblioteca estándar y `boto3`).
- Solo infraestructura del catálogo homologado (`lambda`, `dynamodb`, `api_gateway`, `s3`, `cloudwatch_alarm`).
- El despliegue real necesita permisos para crear roles, Lambdas y API Gateway: el rol del workshop no los tiene (falla con `iam:PassRole` y `apigateway:POST`). Usar `--deploy` en un sandbox propio.
