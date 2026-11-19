# Estándares de arquitectura (adquirencia)

Base de estándares contra la que el agente Arquitecto evalúa cada diseño.
Son archivos Markdown independientes del código (Unit 03, NFR: "la base de
estándares se edita sin tocar código"). Cada archivo tiene un id único
(`ARQ-0N`) que el agente debe citar en su veredicto (campo
`standards_cited` del contrato `Design`).

Para agregar o cambiar un estándar: crear/editar el archivo acá. No
requiere cambios en `src/delivery_crew/architect.py`. Un cambio de
estándar no es un cambio de contrato entre agentes
(`contratos-agentes.md`), así que no necesita acuerdo de los tres — pero
sí conviene avisar si afecta un diseño ya aprobado.

| Id | Estándar | Archivo |
|----|----------|---------|
| ARQ-01 | Datos de tarjetas | `01-datos-de-tarjetas.md` |
| ARQ-02 | Secretos | `02-secretos.md` |
| ARQ-03 | Cifrado y datos transitorios | `03-cifrado-y-ttl.md` |
| ARQ-04 | Permisos mínimos | `04-permisos-minimos.md` |
| ARQ-05 | Trazabilidad del diseño | `05-trazabilidad.md` |
| ARQ-06 | Infraestructura parametrizada | `06-infraestructura-parametrizada.md` |
| ARQ-07 | Aprobación humana bloqueante | `07-aprobacion-humana.md` |
