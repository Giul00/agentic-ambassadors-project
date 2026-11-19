# Agentic Ambassadors: Delivery Crew

Sistema multiagente que lleva un cambio de requerimiento a despliegue verificado en adquirencia, con aprobación humana en cada traspaso. Descripción completa en `.kiro/steering/product.md`.

## Cómo empezar
1. Instalar Kiro CLI e iniciar sesión: `kiro-cli login`.
2. Clonar el repositorio y abrir Kiro en la raíz:
   ```bash
   git clone https://github.com/Giul00/agentic-ambassadors-project.git
   cd agentic-ambassadors-project
   kiro-cli chat
   ```
3. El steering AI-DLC se carga solo. Para planificar, describir la idea y el planificador hará preguntas una por una hasta generar las unidades de trabajo en `aidlc/`.

## Documentación
- `docs/arquitectura.md`: diagramas y decisiones iniciales.
- `docs/caso-demo.md`: caso demo, guion y plan B.
- `aidlc/plan.md`: plan de trabajo, reparto y orden de merges.
- `aidlc/units/`: siete unidades de trabajo.
- `aidlc/elaboration-log.md`: supuestos por confirmar.

## Estructura
- `.kiro/steering/`: reglas del proyecto (`product`, `tech`, `guardrails`, `contratos-agentes`) y el steering AI-DLC (`aidlc-*`).
- `.kiro/agents/`: agentes del planificador AI-DLC.
- `.kiro/templates/`: plantillas del planificador.
- `src/`, `infra/`, `docs/`: código, infraestructura y documentación.

## Credenciales AWS
Las credenciales del workshop son temporales y personales. Se cargan como variables de entorno en la terminal de cada persona. No se suben al repositorio.

## Reparto
- Desarrollador: agente Desarrollador y orquestador.
- Arquitecto de soluciones: agente Arquitecto y estándares.
- Sysops: agente Despliegue, cuenta AWS y observabilidad.

## Créditos
El steering y los agentes AI-DLC provienen de [wilmatos/aidlc-sprint-planning](https://github.com/wilmatos/aidlc-sprint-planning) (licencia MIT).
