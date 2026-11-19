// Tipos del contrato de la API. Ver docs/api.md.

export type StageState =
  | "esperando"
  | "en_curso"
  | "por_aprobar"
  | "aprobado"
  | "rechazado"
  | "invalido";

export type RunState = "en_curso" | "esperando_aprobacion" | "completo" | "rechazado" | "invalido";

export interface Approval {
  status: "pendiente" | "aprobado" | "rechazado";
  by: string | null;
  at: string | null;
  reason: string | null;
}

export interface Stage {
  step: number;
  key: "requirement" | "design" | "change" | "deployment";
  label: string;
  filename: string;
  state: StageState;
  error: string | null;
  artifact: (Record<string, unknown> & { approval: Approval }) | null;
}

export interface Metrics {
  elapsed_seconds: number | null;
  human_approvals: number;
  automated_steps_done: number;
  automated_steps_total: number;
  audit_events: number;
}

export interface RunDetail {
  run_id: string;
  state: RunState;
  stages: Stage[];
  metrics: Metrics;
}

export interface RunSummary {
  run_id: string;
  state: RunState;
  started_at: string | null;
  stages: { step: number; state: StageState }[];
}

export interface AuditEntry {
  run_id: string;
  at: string;
  actor: string;
  action: string;
  artifact?: string;
  reason?: string;
}
