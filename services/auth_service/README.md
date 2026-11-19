# auth-service

Servicio sintético de autorizaciones de adquirencia. Es el servicio que el flujo de Delivery Crew modifica en la demo. Solo usa la biblioteca estándar de Python, así que se empaqueta para Lambda sin dependencias.

**No usa datos reales.** `card_token` es un identificador inventado (`tok_...`). Cualquier valor que parezca un número de tarjeta se rechaza con 400.

## API

`POST /authorize`

```json
{"merchant_id": "m1", "amount": 100, "currency": "ARS", "card_token": "tok_demo01"}
```

Respuesta 200 (aprobada o rechazada):

```json
{"approved": true, "response_code": "00", "message": "Aprobada"}
```

Errores: 400 (entrada inválida, con `details` por campo), 405 (método distinto de POST), 413 (cuerpo mayor a 10 KB).

## Reglas actuales

| Código | Cuándo | Ejemplo |
|---|---|---|
| `00` | Ninguna regla rechaza | `tok_demo01`, 100 ARS |
| `05` | Token bloqueado | `tok_blocked01` |
| `61` | Monto mayor al límite (1.000.000 ARS o 10.000 USD) | `tok_demo01`, 2.000.000 ARS |
| `51` | Token de saldo bajo y monto mayor a 100 | `tok_lowbal_a`, 150 ARS |

El código `65` (límite de frecuencia) **no existe todavía**: es el cambio que hace el agente Desarrollador en la demo.

## Estructura

| Archivo | Contenido |
|---|---|
| `auth_service/models.py` | Solicitud, decisión y validación de entrada |
| `auth_service/rules.py` | Reglas de decisión, en orden. Aquí se agregan reglas nuevas |
| `auth_service/handler.py` | Handler de Lambda: `auth_service.handler.lambda_handler` |
| `auth_service/__main__.py` | Servidor local para pruebas manuales |
| `tests/` | Pruebas (sin AWS) |

## Probarlo

Desde `services/auth_service`:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
..\..\.venv\Scripts\python.exe -m auth_service --port 8080
```

Con el servidor levantado, en otra terminal:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8080/authorize -ContentType "application/json" `
  -Body '{"merchant_id":"m1","amount":100,"currency":"ARS","card_token":"tok_demo01"}'
```

## Para el despliegue (sysops)

- Runtime: Python 3.12 o superior. Handler: `auth_service.handler.lambda_handler`.
- Paquete: el contenido de `services/auth_service/auth_service/` dentro de una carpeta `auth_service/` en la raíz del zip. No incluir `tests/`.
- Integración: API Gateway (REST o HTTP API) con `POST /authorize` en modo proxy.
