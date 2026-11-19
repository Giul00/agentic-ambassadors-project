---
run_id: demo-0001
created_at: '2026-01-01T12:00:00Z'
approval:
  status: aprobado
  by: sysops
  at: '2026-01-01T12:00:00Z'
  reason: null
target_account_id: '123456789012'
region: us-west-2
resources:
- 'DynamoDB: tabla de frecuencia'
- 'IAM: permiso de lectura y escritura para la Lambda'
estimated_cost_usd: 0.05
rollback_plan: Volver a la versión anterior de la Lambda y eliminar la tabla creada.
health_check: ok
rolled_back: false
---


