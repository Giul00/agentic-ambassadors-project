import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { ArtifactView } from "./artifact";
import type { AuditEntry, RunDetail, RunState, RunSummary, Stage, StageState } from "./types";

const POLL_MS = 2000;

const STAGE_LABEL: Record<StageState, string> = {
  esperando: "Esperando",
  en_curso: "En curso",
  por_aprobar: "Por aprobar",
  aprobado: "Aprobado",
  rechazado: "Rechazado",
  invalido: "Inválido",
};

const STAGE_ICON: Record<StageState, string> = {
  esperando: "○",
  en_curso: "◔",
  por_aprobar: "!",
  aprobado: "✓",
  rechazado: "✕",
  invalido: "⚠",
};

const RUN_LABEL: Record<RunState, string> = {
  en_curso: "En curso",
  esperando_aprobacion: "Espera aprobación",
  completo: "Completo",
  rechazado: "Rechazado",
  invalido: "Inválido",
};

const RUN_TONE: Record<RunState, StageState> = {
  en_curso: "en_curso",
  esperando_aprobacion: "por_aprobar",
  completo: "aprobado",
  rechazado: "rechazado",
  invalido: "invalido",
};

function useLocalState<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* sin almacenamiento disponible */
    }
  }, [key, value]);
  return [value, setValue] as const;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m} min ${s.toString().padStart(2, "0")} s` : `${s} s`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "medium" });
}

function describeAction(e: AuditEntry): string {
  const file = e.artifact ? ` ${e.artifact}` : "";
  switch (e.action) {
    case "run_created":
      return "creó la ejecución";
    case "artifact_written":
      return `escribió${file}`;
    case "approval_aprobado":
      return `aprobó${file}`;
    case "approval_rechazado":
      return `rechazó${file}${e.reason ? `: ${e.reason}` : ""}`;
    default:
      return e.action + file;
  }
}

function defaultStep(detail: RunDetail): number {
  const pending = detail.stages.find((s) => s.state === "por_aprobar");
  if (pending) return pending.step;
  const bad = detail.stages.find((s) => s.state === "rechazado" || s.state === "invalido");
  if (bad) return bad.step;
  const active = detail.stages.find((s) => s.state === "en_curso");
  if (active) return active.step;
  return detail.stages[detail.stages.length - 1].step;
}

function Pill({ tone, children }: { tone: StageState; children: React.ReactNode }) {
  return <span className={`state state-${tone}`}>{children}</span>;
}

function DecisionBox({
  stage,
  onDecide,
}: {
  stage: Stage;
  onDecide: (status: "aprobado" | "rechazado", by: string, reason?: string) => Promise<void>;
}) {
  const [name, setName] = useLocalState("approverName", "");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approval = stage.artifact?.approval;

  if (approval && approval.status !== "pendiente") {
    return (
      <div className={`callout callout-${approval.status}`}>
        <strong>
          {approval.status === "aprobado" ? "Aprobado" : "Rechazado"} por {approval.by}
        </strong>
        <span className="muted"> · {formatTime(approval.at)}</span>
        {approval.reason && <p>Motivo: {approval.reason}</p>}
      </div>
    );
  }

  if (stage.state !== "por_aprobar") return null;

  async function submit(status: "aprobado" | "rechazado") {
    setBusy(true);
    setError(null);
    try {
      await onDecide(status, name.trim(), status === "rechazado" ? reason.trim() : undefined);
      setRejecting(false);
      setReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="decision">
      <h3>Esperando tu decisión</h3>
      <label>
        Tu nombre
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: Tomás" />
      </label>
      {rejecting && (
        <label>
          Motivo del rechazo
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} />
        </label>
      )}
      <div className="buttons">
        {!rejecting ? (
          <>
            <button className="btn btn-approve" disabled={busy || !name.trim()} onClick={() => submit("aprobado")}>
              Aprobar
            </button>
            <button className="btn btn-reject" disabled={busy || !name.trim()} onClick={() => setRejecting(true)}>
              Rechazar
            </button>
          </>
        ) : (
          <>
            <button
              className="btn btn-reject"
              disabled={busy || !name.trim() || !reason.trim()}
              onClick={() => submit("rechazado")}
            >
              Confirmar rechazo
            </button>
            <button className="btn" disabled={busy} onClick={() => setRejecting(false)}>
              Cancelar
            </button>
          </>
        )}
      </div>
      {!name.trim() && <p className="muted">Escribe tu nombre para decidir. Queda en la auditoría.</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [pickedStep, setPickedStep] = useState<number | null>(null);
  const [connError, setConnError] = useState<string | null>(null);
  const [manualHours, setManualHours] = useLocalState<number>("manualHours", 4);

  const refresh = useCallback(async () => {
    try {
      const list = await api.runs();
      setRuns(list);
      setConnError(null);
      const id = selectedId ?? list[0]?.run_id ?? null;
      if (selectedId === null && id) setSelectedId(id);
      if (id && list.some((r) => r.run_id === id)) {
        const [d, a] = await Promise.all([api.run(id), api.audit(id)]);
        setDetail(d);
        setAudit(a);
      } else {
        setDetail(null);
        setAudit([]);
      }
    } catch (e) {
      setConnError(e instanceof Error ? e.message : String(e));
    }
  }, [selectedId]);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  function selectRun(id: string) {
    setSelectedId(id);
    setPickedStep(null);
    setDetail(null);
    setAudit([]);
  }

  async function decide(step: number, status: "aprobado" | "rechazado", by: string, reason?: string) {
    if (!detail) return;
    const updated = await api.decide(detail.run_id, step, { status, by, reason });
    setDetail(updated);
    void refresh();
  }

  const activeStep = detail ? (pickedStep ?? defaultStep(detail)) : null;
  const stage = detail?.stages.find((s) => s.step === activeStep) ?? null;

  const manualSeconds = Math.max(0, manualHours) * 3600;
  const elapsed = detail?.metrics.elapsed_seconds ?? null;
  const saving =
    detail?.state === "completo" && elapsed !== null && manualSeconds > 0
      ? Math.max(0, Math.round((1 - elapsed / manualSeconds) * 100))
      : null;

  return (
    <div className="layout">
      <aside className="sidebar">
        <h1>Delivery Crew</h1>
        <p className="muted">De requerimiento a despliegue, con aprobación humana.</p>
        <h2>Ejecuciones</h2>
        {runs.length === 0 && !connError && <p className="muted">No hay ejecuciones todavía.</p>}
        <ul className="runs">
          {runs.map((r) => (
            <li key={r.run_id}>
              <button className={`run ${r.run_id === selectedId ? "run-active" : ""}`} onClick={() => selectRun(r.run_id)}>
                <span className="run-name">{r.run_id}</span>
                <Pill tone={RUN_TONE[r.state]}>{RUN_LABEL[r.state]}</Pill>
                <span className="dots" aria-hidden>
                  {r.stages.map((s) => (
                    <i key={s.step} className={`dot dot-${s.state}`} />
                  ))}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="main">
        {connError && (
          <div className="callout callout-error">
            <strong>No se pudo conectar con la API.</strong> {connError}
            <p>
              Verifica que esté corriendo: <code>python -m delivery_crew.api --port 8000</code>
            </p>
          </div>
        )}

        {!detail && !connError && <p className="muted">Selecciona una ejecución.</p>}

        {detail && (
          <>
            <header className="run-header">
              <h2>{detail.run_id}</h2>
              <Pill tone={RUN_TONE[detail.state]}>{RUN_LABEL[detail.state]}</Pill>
            </header>

            <section className="pipeline" aria-label="Etapas">
              {detail.stages.map((s, i) => (
                <div className="pipeline-item" key={s.step}>
                  <button
                    className={`stage stage-${s.state} ${s.step === activeStep ? "stage-active" : ""}`}
                    onClick={() => setPickedStep(s.step)}
                  >
                    <span className="stage-num">{s.step}</span>
                    <span className="stage-label">{s.label}</span>
                    <Pill tone={s.state}>
                      {STAGE_ICON[s.state]} {STAGE_LABEL[s.state]}
                    </Pill>
                  </button>
                  {i < detail.stages.length - 1 && <span className="arrow" aria-hidden>→</span>}
                </div>
              ))}
            </section>

            <section className="metrics">
              <div className="metric">
                <span className="metric-value">{formatDuration(elapsed)}</span>
                <span className="metric-label">Tiempo del flujo</span>
              </div>
              <div className="metric">
                <span className="metric-value">
                  {detail.metrics.human_approvals}/{detail.stages.length}
                </span>
                <span className="metric-label">Aprobaciones humanas</span>
              </div>
              <div className="metric">
                <span className="metric-value">
                  {detail.metrics.automated_steps_done}/{detail.metrics.automated_steps_total}
                </span>
                <span className="metric-label">Pasos hechos por agentes</span>
              </div>
              <div className="metric">
                <span className="metric-value">{saving !== null ? `${saving}%` : "—"}</span>
                <span className="metric-label">
                  Menos tiempo que hacerlo a mano (
                  <input
                    className="inline-number"
                    type="number"
                    min={0}
                    step={0.5}
                    value={manualHours}
                    onChange={(e) => setManualHours(Number(e.target.value))}
                    aria-label="Horas estimadas a mano"
                  />{" "}
                  h)
                </span>
              </div>
            </section>

            {stage && (
              <section className="detail">
                <div className="detail-head">
                  <h2>
                    {stage.step}. {stage.label}
                  </h2>
                  <code>{stage.filename}</code>
                </div>
                <ArtifactView stage={stage} />
                <DecisionBox key={`${detail.run_id}-${stage.step}`} stage={stage} onDecide={(status, by, reason) => decide(stage.step, status, by, reason)} />
              </section>
            )}

            <section className="audit">
              <h2>Auditoría</h2>
              {audit.length === 0 ? (
                <p className="muted">Sin eventos.</p>
              ) : (
                <ol>
                  {[...audit].reverse().map((e, i) => (
                    <li key={`${e.at}-${i}`}>
                      <time>{formatTime(e.at)}</time>
                      <strong>{e.actor}</strong> {describeAction(e)}
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
