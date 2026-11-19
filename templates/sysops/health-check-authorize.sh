#!/usr/bin/env sh
set -eu

: "${HEALTHCHECK_URL:?HEALTHCHECK_URL es obligatorio}"

payload='{"merchant_id":"demo-merchant","amount":100,"currency":"ARS","card_token":"sysops-health-token"}'
for attempt in 1 2 3; do
  response="$(curl --fail-with-body --silent --show-error --request POST "$HEALTHCHECK_URL" \
    --header 'content-type: application/json' --data "$payload")"
  printf '%s' "$response" | grep -q '"response_code"[[:space:]]*:[[:space:]]*"00"'
done

response="$(curl --fail-with-body --silent --show-error --request POST "$HEALTHCHECK_URL" \
  --header 'content-type: application/json' --data "$payload")"
printf '%s' "$response" | grep -q '"response_code"[[:space:]]*:[[:space:]]*"65"'
