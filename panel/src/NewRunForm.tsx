import { useEffect, useState } from "react";
import type { Config, NewRun, Service } from "./types";

type Mode = "repo" | "local";

const REPO_URL = /^https:\/\/github\.com\/[A-Za-z0-9-]{1,39}\/[A-Za-z0-9._-]{1,100}?(\.git)?\/?$/;

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
  const [mode, setMode] = useState<Mode>("repo");
  const [repoUrl, setRepoUrl] = useState(config?.demo_repo ?? "");
  const [repoRef, setRepoRef] = useState("");
  const [service, setService] = useState(services[0]?.name ?? "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [criteria, setCriteria] = useState("");
  const [name, setName] = useState(defaultName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = services.find((s) => s.name === service) ?? null;
  // El repo de la demo es la API de comercios: se usa su requerimiento de ejemplo.
  const repoDemo = services.find((s) => s.name === "merchants-api")?.demo ?? null;

  function loadDemo() {
    const demo = mode === "repo" ? repoDemo : selected?.demo;
    if (!demo) return;
    setTitle(demo.title);
    setDescription(demo.description);
    setCriteria(demo.acceptance_criteria.join("\n"));
  }

  useEffect(() => {
    if (!repoUrl && config?.demo_repo) setRepoUrl(config.demo_repo);
  }, [config, repoUrl]);

  useEffect(() => {
    if (!service && services.length) setService(services[0].name);
  }, [services, service]);

  useEffect(() => {
    loadDemo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, service, services.length]);

  const criteriaList = criteria.split("\n").map((c) => c.trim()).filter(Boolean);
  const repoOk = REPO_URL.test(repoUrl.trim());
  const sourceOk = mode === "repo" ? repoOk : !!service;
  const valid =
    sourceOk && title.trim().length >= 3 && description.trim().length >= 10 && criteriaList.length > 0 && name.trim();

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
        affected_service: mode === "local" ? service : "merchants-api",
        requested_by: name.trim(),
        ...(mode === "repo" ? { source_repo: repoUrl.trim(), source_ref: repoRef.trim() || undefined } : {}),
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
        <button type="button" className="btn btn-small" onClick={loadDemo}>
          Cargar ejemplo
        </button>
      </div>
      <p className="muted">
        Pasá tu código y describí qué necesitás. El Arquitecto aplica los lineamientos de la empresa, el Desarrollador
        implementa y abre el pull request, y SysOps prepara el despliegue con las plantillas homologadas. Cada etapa
        espera tu aprobación.
      </p>

      <div className="tabs" role="tablist">
        <button type="button" role="tab" aria-selected={mode === "repo"} className={`tab ${mode === "repo" ? "tab-on" : ""}`}
          onClick={() => setMode("repo")}>
          Repositorio de GitHub
        </button>
        <button type="button" role="tab" aria-selected={mode === "local"} className={`tab ${mode === "local" ? "tab-on" : ""}`}
          onClick={() => setMode("local")}>
          Código de este proyecto
        </button>
      </div>

      {mode === "repo" ? (
        <>
          <div className="row">
            <label className="grow">
              URL del repositorio
              <input value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/dueño/repo"
                spellCheck={false} />
            </label>
            <label className="narrow">
              Rama (opcional)
              <input value={repoRef} onChange={(e) => setRepoRef(e.target.value)} placeholder="main" spellCheck={false} />
            </label>
          </div>
          {repoUrl && !repoOk && <p className="error small">Debe ser https://github.com/&lt;dueño&gt;/&lt;repo&gt;</p>}
          <p className="muted small">
            Se clona en un espacio aislado de esta ejecución. Dueños permitidos:{" "}
            {config?.allowed_owners?.length ? config.allowed_owners.map((o) => <code key={o} className="kv">{o}</code>) : "—"}
            {config && (
              <>
                {" "}
                · Pull request:{" "}
                {config.github_token ? <strong>se abrirá en el repo</strong> : "sin GITHUB_TOKEN, la rama queda local"}
              </>
            )}
          </p>
        </>
      ) : (
        <>
          <label>
            Servicio
            <select value={service} onChange={(e) => setService(e.target.value)}>
              {services.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {selected?.summary && <p className="muted small service-summary">{selected.summary}</p>}
        </>
      )}

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
        <p className="error">La API no tiene credenciales AWS: los agentes no podrán llamar a Bedrock.</p>
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
          {busy ? (mode === "repo" ? "Clonando y lanzando…" : "Lanzando…") : "▶ Lanzar agentes"}
        </button>
        <button className="btn" type="button" onClick={onCancel} disabled={busy}>
          Cancelar
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  );
}
