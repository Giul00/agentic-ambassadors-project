import { useEffect, useState } from "react";
import type { Config, NewRun, Service } from "./types";

export function NewRunForm({
  config,
  services,
  defaultName,
  onCreate,
  onCancel,
}: {
  config: Config | null;
  services: Service[];
  defaultName: string;
  onCreate: (body: NewRun) => Promise<void>;
  onCancel: () => void;
}) {
  const [service, setService] = useState(services[0]?.name ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [name, setName] = useState(defaultName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = services.find((s) => s.name === service) ?? null;

  function loadDemo(s: Service | null) {
    if (!s?.demo) return;
    setTitle(s.demo.title);
    setDescription(s.demo.description);
    setCriteria(s.demo.acceptance_criteria.join("\n"));
  }

  useEffect(() => {
    if (!service && services.length) setService(services[0].name);
  }, [services, service]);

  useEffect(() => {
    loadDemo(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [service]);

  const criteriaList = criteria.split("\n").map((c) => c.trim()).filter(Boolean);
  const valid =
    !!service && title.trim().length >= 3 && description.trim().length >= 10 && criteriaList.length > 0 && name.trim();

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
        affected_service: service,
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
        <h2>Nuevo pedido</h2>
        <button type="button" className="btn btn-small" onClick={() => loadDemo(selected)} disabled={!selected?.demo}>
          Cargar ejemplo
        </button>
      </div>
      <p className="muted">
        Elegí el código y describí qué querés. El Arquitecto aplica los lineamientos de la empresa, el Desarrollador
        implementa y SysOps prepara el despliegue con las plantillas homologadas. Cada etapa espera tu aprobación.
      </p>
      <label>
        Tengo este código
        <select value={service} onChange={(e) => setService(e.target.value)}>
          {services.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      {selected?.summary && <p className="muted small service-summary">{selected.summary}</p>}
      <label>
        Qué necesito
        <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} />
      </label>
      <label>
        Detalle
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
          La API no tiene credenciales AWS: los agentes no podrán llamar a Bedrock.
        </p>
      )}
      {config && (
        <p className="muted small">
          Modelo <code>{config.model_id}</code> · Región <code>{config.region}</code>
          {config.target_account && (
            <>
              {" "}
              · Cuenta <code>{config.target_account}</code>
            </>
          )}{" "}
          · Despliegue real {config.deploy_enabled ? <strong>activado</strong> : "desactivado (termina en el plan)"}
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
