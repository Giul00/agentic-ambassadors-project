import type { AuditEntry, Config, NewRun, RunDetail, RunSummary, Service } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail))
        detail = body.detail.map((d: { msg?: string } | string) => (typeof d === "string" ? d : d.msg)).join("; ");
    } catch {
      /* se deja el mensaje por defecto */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  config: () => request<Config>("/api/config"),
  services: () => request<Service[]>("/api/services"),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  audit: (id: string) => request<AuditEntry[]>(`/api/runs/${encodeURIComponent(id)}/audit`),
  createRun: (body: NewRun) => request<RunDetail>("/api/runs", json(body)),
  resume: (id: string, retryRejected: boolean) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(id)}/resume`, json({ retry_rejected: retryRejected })),
  decide: (id: string, step: number, body: { status: "aprobado" | "rechazado"; by: string; reason?: string }) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(id)}/stages/${step}/decision`, json(body)),
};
