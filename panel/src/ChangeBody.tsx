/** Resumen del agente y diff del cambio, a partir del cuerpo de 03-cambio.md. */

function section(body: string, title: string, nextTitle?: string): string | null {
  const marker = `## ${title}`;
  const start = body.indexOf(marker);
  if (start < 0) return null;
  const rest = body.slice(start + marker.length);
  // El texto del agente puede traer sus propios títulos "##": se corta en la sección conocida siguiente.
  const end = nextTitle ? rest.indexOf(`\n## ${nextTitle}`) : rest.search(/\n## /);
  return (end < 0 ? rest : rest.slice(0, end)).trim();
}

function diffOf(body: string): string | null {
  const m = body.match(/```diff\n([\s\S]*?)```/);
  return m ? m[1] : null;
}

function lineClass(line: string): string {
  if (line.startsWith("diff --git")) return "d-file";
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("index ")) return "d-meta";
  if (line.startsWith("@@")) return "d-hunk";
  if (line.startsWith("+")) return "d-add";
  if (line.startsWith("-")) return "d-del";
  return "";
}

export function ChangeBody({ body }: { body: string }) {
  const summary = section(body, "Resumen del agente", "Pruebas");
  const tests = section(body, "Pruebas", "Diff");
  const diff = diffOf(body);
  if (!summary && !diff) return null;
  const lines = diff ? diff.split("\n") : [];
  const added = lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length;
  const removed = lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length;
  return (
    <div className="change-body">
      {summary && (
        <>
          <h3>Resumen del agente</h3>
          <p className="prewrap">{summary}</p>
        </>
      )}
      {tests && <p className="muted">{tests}</p>}
      {diff && (
        <details open>
          <summary>
            Diff del código <span className="d-add">+{added}</span> <span className="d-del">−{removed}</span>
          </summary>
          <pre className="diff">
            {lines.map((l, i) => (
              <div key={i} className={lineClass(l)}>
                {l || " "}
              </div>
            ))}
          </pre>
        </details>
      )}
    </div>
  );
}
