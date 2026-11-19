# infra

El stack `DeliveryCrewAuthService` crea el servicio demo de autorización sintética: API Gateway `POST /authorize`, Lambda y DynamoDB on-demand con TTL. No incluye credenciales ni IDs de cuenta.

Antes de desplegar, validar el stack con el perfil aprobado:

```powershell
cd infra
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
npx aws-cdk@2 synth --profile default
npx aws-cdk@2 diff --profile default
```

`deploy` requiere aprobación explícita de SysOps documentada en `runs/<id>/04-despliegue.md`.
