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

export interface RunnerStatus {
  active: boolean;
  started_at: string;
  finished_at: string | null;
  outcome: "completed" | "waiting_approval" | "rejected" | "blocked" | "invalid" | "failed" | null;
  step: number | null;
  reason: string | null;
}

export interface RunDetail {
  run_id: string;
  state: RunState;
  stages: Stage[];
  metrics: Metrics;
  runner: RunnerStatus | null;
}

export interface Config {
  target_account: string | null;
  region: string;
  model_id: string;
}

export interface NewRun {
  title: string;
  description: string;
  acceptance_criteria: string[];
  affected_service: string;
  requested_by: string;
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
  [key: string]: unknown;
}

export interface DeploymentComponent {
  name: string;
  kind: string;
  depends_on: string[];
  configuration: Record<string, string>;
}

export interface DeploymentSpec {
  environment: "dev" | "qa" | "uat" | "prod";
  components: DeploymentComponent[];
  network_exposure: "private" | "internal" | "public";
  data_classification: "synthetic" | "internal" | "confidential";
  health_check: string;
  rollback_strategy: string;
  observability: string[];
}

export interface Deliverable {
  component: string;
  kind: "zip" | "container" | "static" | "package";
  source_path: string;
  build_command: string;
  entrypoint: string | null;
}
