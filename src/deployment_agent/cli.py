"""Command-line entry point. Planning is intentionally separated from deployment."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .contracts import ContractError, parse_approved_change, render_deployment_plan, validate_run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el plan de despliegue de un handoff aprobado.")
    parser.add_argument("run_id", help="Identificador de runs/<run_id>/")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"), help="Directorio raíz de ejecuciones (default: runs)")
    args = parser.parse_args(argv)
    try:
        run_id = validate_run_id(args.run_id)
        run_directory = args.runs_dir / run_id
        change = parse_approved_change(run_id, run_directory / "03-cambio.md")
        output = run_directory / "04-despliegue.md"
        output.write_text(render_deployment_plan(change), encoding="utf-8")
    except ContractError as error:
        print(f"Error de contrato: {error}", file=sys.stderr)
        return 2
    print(f"Plan generado: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
