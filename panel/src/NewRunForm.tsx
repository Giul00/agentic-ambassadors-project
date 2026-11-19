import { useState } from "react";
import type { Config, NewRun } from "./types";

const DEMO: Omit<NewRun, "requested_by"> = {
  title: "Código de rechazo 65 por límite de frecuencia",
  description:
    "Si un mismo card_token hace más de 3 solicitudes en 60 segundos, auth-service debe rechazar con " +
    "response_code 65 y un mensaje claro.",
  acceptance_criteria: [
    "La cuarta solicitud en 60 segundos devuelve response_code 65.",
    "Las tres primeras solicitudes no se ven afectadas.",
    "El código 65 aparece en la respuesta de la API.",
    "Un card_token con 2 solicitudes por minuto, sostenidas en el tiempo, nunca recibe 65.",
  ],
  affected_service: "auth-service",
};

export function NewRunForm({
  config,
  defaultName,
  onCreate,
  onCancel,
}: {
  config: Config | null;
  defaultName: string;
  onCreate: (body: NewRun) => Promise<void>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(DEMO.title);
  const [description, setDescription] = useState(DEMO.description);
  const [criteria, setCriteria] = useState(DEMO.acceptance_criteria.join("\n"));
  const [name, setName] = useState(defaultName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const criteriaList = criteria.split("\n").map((c) => c.trim()).filter(Boolean);
  const valid = title.trim().length >= 3 && description.trim().length >= 10 && criteriaList.length > 0 && name.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate({
        title: title.trim(),
        description: description.trim(),
        acceptance_criteria: criteriaList,
        affected_service: "auth-service",
        requested_by: name.trim(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <form className="new-run" onSubmit={submit}>
      <div className="new-run-head">
        <h2>Nuevo requerimiento</h2>
        <button type="button" className="btn btn-small" onClick={() => {
          setTitle(DEMO.title);
          setDescription(DEMO.description);
          setCriteria(DEMO.acceptance_criteria.join("\n"));
        }}>
          Cargar caso demo
        </button>
      </div>
      <p className="muted">
        Los agentes diseñan, implementan y planifican el despliegue en <code>auth-service</code>. Cada etapa espera tu
        aprobación.
      </p>
      <label>
        Título
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} />
      </label>
      <label>
        Descripción
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} maxLength={2000} />
      </label>
      <label>
        Criterios de aceptación (uno por línea)
        <textarea value={criteria} onChange={(e) => setCriteria(e.target.value)} rows={5} />
      </label>
      <label>
        Quién lo pide
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Ej.: Tomás" />
      </label>
      {config && !config.target_account && (
        <p className="error">
          La API no tiene cuenta de despliegue ni credenciales AWS: los agentes no podrán llamar a Bedrock.
        </p>
      )}
      {config && (
        <p className="muted small">
          Modelo <code>{config.model_id}</code> · Región <code>{config.region}</code>
          {config.target_account && (
            <>
              {" "}
              · Cuenta de despliegue <code>{config.target_account}</code>
            </>
          )}
        </p>
      )}
      <div className="buttons">
        <button className="btn btn-approve" type="submit" disabled={!valid || busy}>
          {busy ? "Lanzando…" : "▶ Lanzar agentes"}
        </button>
        <button className="btn" type="button" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
