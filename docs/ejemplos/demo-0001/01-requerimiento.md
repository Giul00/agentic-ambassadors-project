---
run_id: demo-0001
created_at: '2026-01-01T12:00:00Z'
approval:
  status: aprobado
  by: usuario
  at: '2026-01-01T12:00:00Z'
  reason: null
title: Código de rechazo 65 por límite de frecuencia
description: Si un mismo card_token hace más de 3 solicitudes en 60 segundos, auth-service
  debe rechazar con response_code 65 y un mensaje claro.
acceptance_criteria:
- La cuarta solicitud en 60 segundos devuelve response_code 65.
- Las tres primeras solicitudes no se ven afectadas.
- El código 65 aparece en la respuesta de la API.
- Un card_token con 2 solicitudes por minuto, sostenidas en el tiempo, nunca recibe
  65.
affected_service: auth-service
---


