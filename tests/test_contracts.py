from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from deployment_agent.contracts import ContractError, parse_approved_change, render_deployment_plan


class ContractTests(unittest.TestCase):
    def test_parses_an_approved_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory) / "03-cambio.md"
            handoff.write_text("""# Cambio
rama: feature/rejection-code
enlace al pull request: https://example.test/pr/42
archivos modificados:
- src/api.py
- infra/service.py
resultado de las pruebas: 12 pruebas pasaron
estado de aprobación humana: aprobado
""", encoding="utf-8")

            change = parse_approved_change("demo-42", handoff)
            plan = render_deployment_plan(change, datetime(2026, 1, 1, tzinfo=timezone.utc))

        self.assertEqual(change.changed_files, ("src/api.py", "infra/service.py"))
        self.assertIn("Estado de aprobación humana: **pendiente**", plan)
        self.assertIn("No se ejecutaron comandos AWS", plan)


    def test_rejects_unapproved_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            handoff = Path(directory) / "03-cambio.md"
            handoff.write_text("estado de aprobación humana: pendiente", encoding="utf-8")

            with self.assertRaisesRegex(ContractError, "aprobación humana"):
                parse_approved_change("demo-42", handoff)
