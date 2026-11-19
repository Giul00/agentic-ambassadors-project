import type { Deliverable, DeploymentSpec, Stage } from "./types";

type Kind = "text" | "list" | "link" | "money" | "bool" | "badge" | "code" | "spec" | "deliverables";
interface Field {
  label: string;
  field: string;
  kind?: Kind;
}

const FIELDS: Record<Stage["key"], Field[]> = {
  requirement: [
    { label: "Título", field: "title" },
    { label: "Descripción", field: "description" },
    { label: "Criterios de aceptación", field: "acceptance_criteria", kind: "list" },
    { label: "Servicio afectado", field: "affected_service", kind: "code" },
  ],
  design: [
    { label: "Resumen", field: "summary" },
    { label: "Decisión", field: "decision" },
    { label: "Componentes", field: "components", kind: "list" },
    { label: "Riesgos", field: "risks", kind: "list" },
    { label: "Veredicto", field: "verdict", kind: "badge" },
    { label: "Estándares citados", field: "standards_cited", kind: "list" },
    { label: "Preguntas abiertas", field: "open_questions", kind: "list" },
    { label: "Especificación de despliegue", field: "deployment_spec", kind: "spec" },
  ],
  change: [
    { label: "Rama", field: "branch", kind: "code" },
    { label: "Pull request", field: "pull_request_url", kind: "link" },
    { label: "Archivos modificados", field: "files_modified", kind: "list" },
    { label: "Resultado de pruebas", field: "test_result", kind: "badge" },
    { label: "Resumen de pruebas", field: "test_summary" },
    { label: "Entregables", field: "deliverables", kind: "deliverables" },
  ],
  deployment: [
    { label: "Cuenta de despliegue", field: "target_account_id", kind: "code" },
    { label: "Región", field: "region", kind: "code" },
    { label: "Recursos", field: "resources", kind: "list" },
    { label: "Costo estimado", field: "estimated_cost_usd", kind: "money" },
    { label: "Plan de rollback", field: "rollback_plan" },
    { label: "Verificación de salud", field: "health_check", kind: "badge" },
    { label: "Revertido", field: "rolled_back", kind: "bool" },
  ],
};

function SpecView({ spec }: { spec: DeploymentSpec }) {
  return (
    <div className="nested">
      <p>
        Ambiente <code>{spec.environment}</code> · Exposición <code>{spec.network_exposure}</code> · Datos{" "}
        <code>{spec.data_classification}</code>
      </p>
      <table className="mini">
        <thead>
          <tr>
            <th>Componente</th>
            <th>Tipo</th>
            <th>Depende de</th>
            <th>Configuración</th>
          </tr>
        </thead>
        <tbody>
          {spec.components.map((c) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td>
                <code>{c.kind}</code>
              </td>
              <td>{c.depends_on.join(", ") || "—"}</td>
              <td>
                {Object.entries(c.configuration).length === 0
                  ? "—"
                  : Object.entries(c.configuration).map(([k, v]) => (
                      <code key={k} className="kv">
                        {k}={v}
                      </code>
                    ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>Health check: {spec.health_check}</p>
      <p>Rollback: {spec.rollback_strategy}</p>
      <p>Observabilidad: {spec.observability.join(", ")}</p>
    </div>
  );
}

function DeliverablesView({ items }: { items: Deliverable[] }) {
  if (items.length === 0) return <span className="muted">Ninguno</span>;
  return (
    <table className="mini">
      <thead>
        <tr>
          <th>Componente</th>
          <th>Tipo</th>
          <th>Ruta</th>
          <th>Entrypoint</th>
        </tr>
      </thead>
      <tbody>
        {items.map((d) => (
          <tr key={d.component}>
            <td>{d.component}</td>
            <td>
              <code>{d.kind}</code>
            </td>
            <td>
              <code>{d.source_path}</code>
            </td>
            <td>{d.entrypoint ? <code>{d.entrypoint}</code> : "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Value({ kind = "text", value }: { kind?: Kind; value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  switch (kind) {
    case "spec":
      return <SpecView spec={value as DeploymentSpec} />;
    case "deliverables":
      return <DeliverablesView items={value as Deliverable[]} />;
    case "list": {
      const items = value as string[];
      if (items.length === 0) return <span className="muted">Ninguno</span>;
      return (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    }
    case "link":
      return (
        <a href={String(value)} target="_blank" rel="noreferrer noopener">
          {String(value)}
        </a>
      );
    case "money":
      return <>US$ {Number(value).toFixed(2)}</>;
    case "bool":
      return <>{value ? "Sí" : "No"}</>;
    case "badge":
      return <span className={`pill pill-${String(value)}`}>{String(value)}</span>;
    case "code":
      return <code>{String(value)}</code>;
    default:
      return <>{String(value)}</>;
  }
}

export function ArtifactView({ stage }: { stage: Stage }) {
  if (stage.error) {
    return (
      <div className="callout callout-error">
        <strong>El archivo {stage.filename} no cumple el contrato.</strong>
        <pre>{stage.error}</pre>
      </div>
    );
  }
  if (!stage.artifact) {
    return (
      <p className="muted">
        {stage.state === "en_curso"
          ? "Un agente está trabajando en esta etapa. El resultado aparecerá aquí."
          : "Esta etapa empezará cuando la anterior sea aprobada."}
      </p>
    );
  }
  const artifact = stage.artifact;
  return (
    <dl className="fields">
      {FIELDS[stage.key].map(({ label, field, kind }) => (
        <div key={field} className="field">
          <dt>{label}</dt>
          <dd>
            <Value kind={kind} value={artifact[field]} />
          </dd>
        </div>
      ))}
    </dl>
  );
}
