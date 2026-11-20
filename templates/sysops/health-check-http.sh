#!/usr/bin/env sh
set -eu

# Generic, non-domain-specific health check. The generated CI supplies the endpoint
# through a protected/environment-scoped variable; it never belongs in the template.
url="${1:?Se requiere HEALTHCHECK_URL}"
expected_status="${2:-200}"
status="$(curl --fail --silent --show-error --output /dev/null --write-out '%{http_code}' "$url")"

test "$status" = "$expected_status"
echo "Health check OK: $url ($status)"
