"""python -m delivery_crew.api [--port 8000] [--runs-dir runs] [--target-account 123456789012]"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys


def _active_account() -> str | None:
    """Cuenta de las credenciales activas, para usarla como destino del plan si no se indica otra."""
    try:
        import boto3

        from ..bedrock import region

        return boto3.client("sts", region_name=region()).get_caller_identity()["Account"]
    except Exception:  # noqa: BLE001 - sin credenciales el panel funciona igual, solo sin agentes
        return None


def main() -> None:
    from ..dotenv import load_and_report

    load_and_report()  # .env antes de leer cualquier variable (AWS, GitHub, despliegue)
    parser = argparse.ArgumentParser(description="API del panel de Delivery Crew")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runs-dir", default=None)
    parser.add_argument("--repo", default=None, help="raíz del repositorio (para el agente Desarrollador)")
    parser.add_argument("--target-account", default=None,
                        help="cuenta de despliegue para el plan; por defecto, la de las credenciales activas")
    parser.add_argument("--deploy", action="store_true",
                        help="tras aprobar el plan, desplegar de verdad (requiere permisos completos en la cuenta)")
    args = parser.parse_args()

    if args.deploy:
        os.environ["DELIVERY_CREW_DEPLOY"] = "1"
    if os.environ.get("DELIVERY_CREW_DEPLOY", "").lower() in ("1", "true", "si", "sí"):
        print("Despliegue real ACTIVADO: al aprobar el plan se crea el stack en AWS.")
    else:
        print("Despliegue real desactivado: el flujo termina en el plan aprobado (use --deploy para activarlo).")

    from ..workspace import github_token

    token = github_token()
    if not token and sys.stdin.isatty():
        try:
            token = getpass.getpass("Token de GitHub para abrir y mergear PRs (Enter para omitir; no se muestra): ").strip()
        except (EOFError, KeyboardInterrupt):
            token = ""
        if token:
            os.environ["GITHUB_TOKEN"] = token
    token = github_token()
    if token:
        print(f"GitHub: token cargado (termina en ...{token[-4:]}). Se abrirán y mergearán PRs.")
    else:
        print("GitHub: sin token. Las ramas quedan locales (sin PR ni merge).")

    if args.runs_dir:
        os.environ["DELIVERY_CREW_RUNS_DIR"] = args.runs_dir
    if args.repo:
        os.environ["DELIVERY_CREW_REPO"] = args.repo
    account = args.target_account or os.environ.get("DELIVERY_CREW_TARGET_ACCOUNT") or _active_account()
    if account:
        if not re.fullmatch(r"\d{12}", account):
            parser.error("--target-account debe tener 12 dígitos")
        os.environ["DELIVERY_CREW_TARGET_ACCOUNT"] = account
        print(f"Cuenta de despliegue para los planes: {account}")
    else:
        print("ATENCIÓN: sin credenciales AWS. El panel funciona, pero los agentes no podrán llamar a Bedrock.")

    import uvicorn

    uvicorn.run("delivery_crew.api.app:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
