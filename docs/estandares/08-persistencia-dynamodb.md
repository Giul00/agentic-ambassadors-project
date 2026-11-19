---
id: ARQ-08
titulo: Persistencia de servicios en DynamoDB
---

# ARQ-08: Persistencia de servicios en DynamoDB

**Regla:** Los servicios nuevos que guardan entidades de negocio por
identificador (ABM, CRUD, catálogos, estados) usan **Amazon DynamoDB** en
modo bajo demanda (`PAY_PER_REQUEST`), con cifrado en reposo y
recuperación a un punto en el tiempo. Cada entidad se guarda por su
identificador como clave de partición (`partition_key`, de tipo String).
Los registros de negocio no llevan TTL; solo los datos transitorios
(ver ARQ-03).

**Cómo se integra en el código:** La persistencia se implementa como un
**adaptador** detrás del puerto del dominio (por ejemplo
`MerchantRepository`), seleccionado por la variable de entorno
`STORAGE_BACKEND=dynamodb`. El nombre de la tabla llega en `TABLE_NAME`,
que inyecta la infraestructura. El adaptador en memoria se mantiene para
pruebas y desarrollo local. El dominio y los casos de uso no cambian.

**Por qué:** Es el estándar de plataforma: sin servidores que administrar,
escala a cero, se despliega con la plantilla homologada `lambda_dynamodb`
y ya tiene controles de seguridad revisados.

**Cómo se verifica:** El diseño declara un componente `dynamodb` con
`partition_key`, y la Lambda que lo usa depende de él y declara
`STORAGE_BACKEND=dynamodb`.

**Veredicto si se incumple:** `observaciones` si propone otra base sin
justificación (por ejemplo, RDS para un ABM por identificador).
