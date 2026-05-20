#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SOURCE_DIR}/.." && pwd)"
BINARY_SOURCE="${MIHOMO_BINARY_SOURCE:-${PROJECT_DIR}/bin/mihomo}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

if [[ ! -x "${BINARY_SOURCE}" ]]; then
  echo "missing Mihomo binary: ${BINARY_SOURCE}" >&2
  echo "place a binary at ${PROJECT_DIR}/bin/mihomo or set MIHOMO_BINARY_SOURCE" >&2
  exit 1
fi

mkdir -p /usr/local/bin /usr/local/libexec /etc/mihomo

install -m 755 "${BINARY_SOURCE}" /usr/local/bin/mihomo
install -m 755 "${PROJECT_DIR}/src/convert_subscription_to_mihomo.py" /usr/local/libexec/convert_subscription_to_mihomo.py
install -m 755 "${SOURCE_DIR}/mihomo-update-subscription.sh" /usr/local/libexec/mihomo-update-subscription
install -m 644 "${SOURCE_DIR}/mihomo.service" /etc/systemd/system/mihomo.service
install -m 644 "${SOURCE_DIR}/mihomo-subscription-update.service" /etc/systemd/system/mihomo-subscription-update.service
install -m 644 "${SOURCE_DIR}/mihomo-subscription-update.timer" /etc/systemd/system/mihomo-subscription-update.timer

if [[ -n "${MIHOMO_SUBSCRIPTION_URL:-}" ]]; then
  umask 077
  cat > /etc/mihomo/subscription.env <<EOF
MIHOMO_SUBSCRIPTION_URL=${MIHOMO_SUBSCRIPTION_URL}
MIHOMO_ALLOWED_REGIONS=${MIHOMO_ALLOWED_REGIONS:-US,DE,JP,KR,SG}
EOF
fi

if [[ ! -f /etc/mihomo/subscription.env ]]; then
  echo "missing /etc/mihomo/subscription.env; set MIHOMO_SUBSCRIPTION_URL before running this installer" >&2
  exit 1
fi

systemctl daemon-reload
systemctl start mihomo-subscription-update.service
systemctl enable --now mihomo-subscription-update.timer
systemctl enable --now mihomo.service
