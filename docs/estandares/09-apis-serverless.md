---
id: ARQ-09
titulo: Exposición de APIs con API Gateway y Lambda
---

# ARQ-09: Exposición de APIs con API Gateway y Lambda

**Regla:** Las APIs HTTP de los servicios se exponen con **Amazon API
Gateway** (REST, regional) integrado en modo proxy con **AWS Lambda**
(Python 3.12). El ruteo de la API lo resuelve el handler del servicio
(`<paquete>.handler.lambda_handler`), no la configuración de API Gateway.
La Lambda tiene un rol propio con permisos solo sobre sus recursos
(ver ARQ-04) y logs en CloudWatch con retención acotada.

**Por qué:** Un único patrón de despliegue, ya homologado por SysOps en la
plantilla `lambda_dynamodb`, reduce el tiempo de puesta en producción y
evita configuraciones ad hoc.

**Cómo se verifica:** El diseño declara componentes `api_gateway` y
`lambda`, con la API dependiendo de la Lambda. El health check describe
una verificación observable sobre las rutas del servicio (por ejemplo,
alta y consulta de una entidad).

**Veredicto si se incumple:** `observaciones` si propone otro mecanismo de
exposición (servidores, contenedores) sin una necesidad que lo justifique.
