import type { Stage } from "./types";

type Kind = "text" | "list" | "link" | "money" | "bool" | "badge" | "code";
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
  ],
  change: [
    { label: "Rama", field: "branch", kind: "code" },
    { label: "Pull request", field: "pull_request_url", kind: "link" },
    { label: "Archivos modificados", field: "files_modified", kind: "list" },
    { label: "Resultado de pruebas", field: "test_result", kind: "badge" },
    { label: "Resumen de pruebas", field: "test_summary" },
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

function Value({ kind = "text", value }: { kind?: Kind; value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="muted">—</span>;
  switch (kind) {
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
