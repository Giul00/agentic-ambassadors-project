import type { AuditEntry, RunDetail, RunSummary } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* se deja el mensaje por defecto */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  audit: (id: string) => request<AuditEntry[]>(`/api/runs/${encodeURIComponent(id)}/audit`),
  decide: (id: string, step: number, body: { status: "aprobado" | "rechazado"; by: string; reason?: string }) =>
    request<RunDetail>(`/api/runs/${encodeURIComponent(id)}/stages/${step}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
};
