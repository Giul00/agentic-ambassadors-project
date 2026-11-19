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
deployment_spec:
  environment: qa
  components:
  - name: auth-api
    kind: api_gateway
    depends_on:
    - auth-handler
    configuration: {}
  - name: auth-handler
    kind: lambda
    depends_on:
    - frequency-store
    configuration:
      FREQUENCY_STORE: dynamodb
  - name: frequency-store
    kind: dynamodb
    depends_on: []
    configuration:
      partition_key: pk
      ttl_attribute: ttl
  network_exposure: public
  data_classification: synthetic
  health_check: 'POST /authorize: tres 00 y luego 65'
  rollback_strategy: Restaurar la versión Lambda aprobada previamente y verificar
    el endpoint.
  observability:
  - CloudWatch logs
  - métrica de errores Lambda
---

Diagrama y detalle del diseño.
