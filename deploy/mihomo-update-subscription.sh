#!/usr/bin/env bash
set -euo pipefail

: "${MIHOMO_SUBSCRIPTION_URL:?MIHOMO_SUBSCRIPTION_URL is not set}"

TMP_CONFIG="$(mktemp /etc/mihomo/config.yaml.XXXXXX)"
trap 'rm -f "${TMP_CONFIG}"' EXIT

python3 /usr/local/libexec/convert_subscription_to_mihomo.py \
  "${MIHOMO_SUBSCRIPTION_URL}" \
  --regions "${MIHOMO_ALLOWED_REGIONS:-US,DE,JP,KR,SG}" \
  -o "${TMP_CONFIG}"

/usr/local/bin/mihomo -t -f "${TMP_CONFIG}" >/dev/null
install -m 600 "${TMP_CONFIG}" /etc/mihomo/config.yaml

if systemctl is-active --quiet mihomo.service; then
  systemctl restart mihomo.service
fi
