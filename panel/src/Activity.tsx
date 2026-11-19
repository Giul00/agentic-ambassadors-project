import { useEffect, useRef, useState } from "react";
import type { AuditEntry } from "./types";

const ACTORS: Record<string, string> = {
  orquestador: "Orquestador",
  orchestrator: "Orquestador",
  "agente-arquitecto": "Agente Arquitecto",
  "agente-desarrollador": "Agente Desarrollador",
  "agente-despliegue": "Agente Despliegue",
};

const AGENT_CLASS: Record<string, string> = {
  "agente-arquitecto": "who-arq",
  "agente-desarrollador": "who-dev",
  "agente-despliegue": "who-ops",
};

function time(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString("es-AR", { hour12: false });
}

function str(v: unknown): string {
  return v === undefined || v === null ? "" : String(v);
}

function Message({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 600;
  return (
    <div className="bubble">
      <div className={long && !open ? "bubble-text clamp" : "bubble-text"}>{text}</div>
      {long && (
        <button className="link" onClick={() => setOpen(!open)}>
          {open ? "ver menos" : "ver más"}
        </button>
      )}
    </div>
  );
}

function Row({ e }: { e: AuditEntry }) {
  const who = ACTORS[e.actor] ?? e.actor;
  const cls = AGENT_CLASS[e.actor] ?? (ACTORS[e.actor] ? "who-orq" : "who-human");
  const t = <time>{time(e.at)}</time>;
  switch (e.action) {
    case "run_created":
      return <li className="ev ev-muted">{t} Ejecución creada</li>;
    case "stage_started":
      return (
        <li className="ev ev-stage">
          {t} ▶ <strong>{str(e.stage)}</strong>: {e.retry ? "reintentando con el motivo del rechazo" : "el agente empieza a trabajar"}
        </li>
      );
    case "stage_finished":
      return <li className="ev ev-ok">{t} ✓ {str(e.stage)} listo en {str(e.seconds)} s</li>;
    case "stage_failed":
      return <li className="ev ev-bad">{t} ✕ {str(e.stage)} falló: {str(e.error)}</li>;
    case "agent_message":
      return (
        <li className={`ev ev-msg ${cls}`}>
          {t} <span className="who">{who}</span>
          <Message text={str(e.text)} />
        </li>
      );
    case "tool_read_file":
      return <li className={`ev ev-tool ${cls}`}>{t} 📖 leyó <code>{str(e.path)}</code></li>;
    case "tool_write_file":
      return (
        <li className={`ev ev-tool ${cls}`}>
          {t} ✏️ {e.created ? "creó" : "modificó"} <code>{str(e.path)}</code>
        </li>
      );
    case "tool_run_tests":
      return (
        <li className={`ev ${e.passed ? "ev-ok" : "ev-bad"} ${cls}`}>
          {t} 🧪 corrió las pruebas: {str(e.summary)}
        </li>
      );
    case "verification":
      return (
        <li className={`ev ${e.passed ? "ev-ok" : "ev-bad"}`}>
          {t} 🔒 verificación independiente (intento {str(e.attempt)}): {str(e.summary)}
        </li>
      );
    case "developer_started":
      return e.feedback ? (
        <li className="ev ev-stage">{t} ↻ el Desarrollador recibe el motivo del rechazo: “{str(e.feedback)}”</li>
      ) : null;
    case "artifact_written":
      if (e.actor in ACTORS && e.actor !== "orquestador") {
        return <li className={`ev ev-tool ${cls}`}>{t} 📄 entregó <code>{str(e.artifact)}</code> para revisión</li>;
      }
      return null;
    case "approval_aprobado":
      return <li className="ev ev-human ev-ok">{t} 👤 <strong>{e.actor}</strong> aprobó <code>{str(e.artifact)}</code></li>;
    case "approval_rechazado":
      return (
        <li className="ev ev-human ev-bad">
          {t} 👤 <strong>{e.actor}</strong> rechazó <code>{str(e.artifact)}</code>: “{str(e.reason)}”
        </li>
      );
    case "waiting_approval":
      return <li className="ev ev-wait">{t} ⏸ {str(e.stage)}: esperando aprobación humana</li>;
    case "deployment_bundle_generated":
      return (
        <li className="ev ev-tool who-ops">
          {t} 📦 generó el bundle de despliegue con los perfiles {Array.isArray(e.profiles) ? e.profiles.join(", ") : ""}
        </li>
      );
    case "flow_completed":
      return <li className="ev ev-final ev-ok">{t} 🏁 Flujo completo</li>;
    case "flow_stopped":
      return (
        <li className="ev ev-final ev-bad">
          {t} ■ Flujo detenido ({str(e.outcome)}){e.reason ? `: ${str(e.reason)}` : ""}
        </li>
      );
    default:
      return null;
  }
}

export function Activity({ entries, live }: { entries: AuditEntry[]; live: boolean }) {
  const box = useRef<HTMLOListElement>(null);
  const stick = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [entries.length]);

  return (
    <section className="activity">
      <div className="activity-head">
        <h2>Lo que hacen los agentes</h2>
        {live && <span className="live">● en vivo</span>}
      </div>
      {entries.length === 0 ? (
        <p className="muted">Sin actividad todavía.</p>
      ) : (
        <ol
          ref={box}
          onScroll={(ev) => {
            const el = ev.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
          }}
        >
          {entries.map((e, i) => (
            <Row key={`${e.at}-${i}`} e={e} />
          ))}
        </ol>
      )}
    </section>
  );
}
