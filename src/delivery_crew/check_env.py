"""Comprueba que el entorno está listo en la cuenta AWS activa.

Uso:  python -m delivery_crew.check_env [--expect-account 123456789012]

Cada integrante lo corre en su propia cuenta. Antes de desplegar, usar --expect-account
con el ID de la cuenta de despliegue para evitar desplegar en otra por error.
"""

from __future__ import annotations

import argparse
import sys

from . import bedrock


def main(argv: list[str] | None = None) -> int:
    from .dotenv import load_and_report

    load_and_report()
    parser = argparse.ArgumentParser(description="Comprobación de entorno de Delivery Crew")
    parser.add_argument("--expect-account", help="ID de cuenta esperado (12 dígitos)")
    parser.add_argument("--skip-model", action="store_true", help="no llamar a Bedrock")
    args = parser.parse_args(argv)

    ok = True
    print(f"Región: {bedrock.region()}")
    print(f"Modelo: {bedrock.model_id()}")

    try:
        import boto3

        identity = boto3.client("sts", region_name=bedrock.region()).get_caller_identity()
        account = identity["Account"]
        print(f"Cuenta activa: {account}")
        print(f"Identidad: {identity['Arn']}")
        if args.expect_account and args.expect_account != account:
            print(f"ERROR: se esperaba la cuenta {args.expect_account} y la activa es {account}")
            ok = False
    except Exception as exc:  # noqa: BLE001 - se informa cualquier fallo de credenciales
        print(f"ERROR: no se pudo validar la identidad AWS: {type(exc).__name__}: {exc}")
        return 1

    if not args.skip_model:
        try:
            answer = bedrock.ask("Responde solo con la palabra: ok", fast=True, max_tokens=20)
            print(f"Bedrock responde: {answer.strip()[:40]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: Bedrock no respondió: {type(exc).__name__}: {exc}")
            ok = False

    print("Entorno OK" if ok else "Entorno con errores")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
