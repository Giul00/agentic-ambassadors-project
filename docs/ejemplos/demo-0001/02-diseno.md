---
run_id: demo-0001
created_at: '2026-01-01T12:00:00Z'
approval:
  status: aprobado
  by: arquitecto
  at: '2026-01-01T12:00:00Z'
  reason: null
summary: Contar solicitudes por card_token en una tabla DynamoDB con TTL de 60 segundos.
components:
- auth-service (reglas)
- 'DynamoDB: tabla de frecuencia'
decision: Usar DynamoDB con contador atómico y TTL en lugar de memoria de la Lambda.
risks:
- Costo por escritura en cada solicitud.
- Latencia extra de una llamada a DynamoDB.
verdict: aprobado
standards_cited:
- Permisos mínimos
- Sin datos de tarjeta reales
open_questions: []
---

Diagrama y detalle del diseño.
