# Caso demo

> Propuesta inicial, sujeta a cambios del equipo.

## Servicio de ejemplo
`auth-service`: un servicio sintético de autorizaciones de adquirencia. Recibe una solicitud de autorización con datos ficticios y responde aprobada o rechazada con un código de respuesta.

- API: `POST /authorize` con `{ "merchant_id", "amount", "currency", "card_token" }`.
- Respuesta: `{ "approved": bool, "response_code": "00" | "51" | ..., "message": "..." }`.
- Implementación sugerida: AWS Lambda detrás de API Gateway, con reglas simples en código (por ejemplo, rechazar si el monto supera un saldo simulado).
- Sin PAN, CVV ni datos reales. `card_token` es un identificador inventado.

## Requerimiento que entra al flujo
> "Agregar el código de rechazo 65 (excede el límite de frecuencia) al servicio de autorizaciones. Si un mismo `card_token` hace más de 3 solicitudes en 60 segundos, el servicio debe rechazar con `response_code: "65"` y un mensaje claro. El código debe aparecer en la respuesta de la API."

## Qué hace cada agente
1. **Arquitecto:** propone dónde guardar el contador de frecuencia (por ejemplo, DynamoDB con TTL), valida contra los estándares y produce el ADR y el diagrama. Aprueba el arquitecto.
2. **Desarrollador:** modifica el servicio, escribe las pruebas (caso aprobado, caso 65, borde de 3 solicitudes) y abre el pull request. Aprueba el desarrollador.
3. **Despliegue:** genera los cambios de infraestructura (tabla DynamoDB y permisos), muestra el costo estimado y el plan de rollback, y despliega en la cuenta del arquitecto. Aprueba sysops.
4. **Verificación:** el agente de Despliegue envía 4 solicitudes seguidas y comprueba que la cuarta devuelve `65`.

## Guion de la presentación (aprox. 5 minutos)
1. Problema: cuánto tarda hoy un cambio de este tipo (estimado manual).
2. Se escribe el requerimiento en una frase.
3. Se muestra el flujo de punta a punta, con las tres aprobaciones humanas.
4. Se prueba el servicio desplegado en vivo.
5. Se provoca un fallo a propósito y se muestra el rollback.
6. Métricas: tiempo total contra el estimado manual, pasos manuales eliminados, defectos detectados antes de desplegar.

## Plan B
Si el despliegue en vivo falla, se muestra una ejecución grabada y los artefactos de `runs/`.
