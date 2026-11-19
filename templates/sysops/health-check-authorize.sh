#!/usr/bin/env sh
# Health check de auth-service: con un token nuevo, 3 solicitudes dan 00 y la cuarta 65.
#
# - El token debe tener el formato tok_... (el servicio rechaza otros con 400).
# - Se usa un token distinto en cada corrida: con uno fijo, una segunda corrida dentro del
#   mismo minuto empezaría con el contador lleno y fallaría.
# - La ventana es fija por minuto: si las 4 solicitudes caen justo en el cambio de minuto,
#   la cuarta puede dar 00. Por eso se reintenta una vez con otro token.
set -eu

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL es obligatorio}"

post() {
  curl --fail-with-body --silent --show-error --max-time 10 --request POST "$HEALTHCHECK_URL" \
    --header 'content-type: application/json' \
    --data "{\"merchant_id\":\"health-check\",\"amount\":100,\"currency\":\"ARS\",\"card_token\":\"$1\"}"
}

has_code() {
  printf '%s' "$1" | grep -q "\"response_code\"[[:space:]]*:[[:space:]]*\"$2\""
}

check_once() {
  token="tok_hc_$(date +%s)_$$_$1"
  for n in 1 2 3; do
    response="$(post "$token")" || { echo "solicitud $n falló: $response"; return 1; }
    has_code "$response" 00 || { echo "solicitud $n: se esperaba 00: $response"; return 1; }
  done
  response="$(post "$token")" || { echo "solicitud 4 falló: $response"; return 1; }
  has_code "$response" 65 || { echo "solicitud 4: se esperaba 65: $response"; return 1; }
  echo "health check OK (token $token)"
}

check_once a || { echo "reintento con otro token"; check_once b; }
