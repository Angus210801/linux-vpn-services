#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SOURCE_DIR}/.." && pwd)"
BINARY_SOURCE="${MIHOMO_BINARY_SOURCE:-${PROJECT_DIR}/bin/mihomo}"
MIHOMO_VERSION="${MIHOMO_VERSION:-latest}"

download_file() {
  local url output
  url="$1"
  output="$2"

  if type -P curl >/dev/null 2>&1; then
    curl -fsSL "${url}" -o "${output}"
    return 0
  fi

  if type -P wget >/dev/null 2>&1; then
    wget -qO "${output}" "${url}"
    return 0
  fi

  if type -P python3 >/dev/null 2>&1; then
    python3 - "${url}" "${output}" <<'PY'
import sys
import urllib.request

url = sys.argv[1]
output = sys.argv[2]

with urllib.request.urlopen(url, timeout=60) as response, open(output, "wb") as file:
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        file.write(chunk)
PY
    return 0
  fi

  echo "missing downloader: install curl or wget, or provide python3" >&2
  exit 1
}

download_mihomo_binary() {
  local os arch asset_name api_url download_url tmp_gz

  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"

  case "${arch}" in
    x86_64|amd64)
      asset_name='mihomo-linux-amd64-compatible'
      ;;
    aarch64|arm64)
      asset_name='mihomo-linux-arm64'
      ;;
    armv7l|armv7)
      asset_name='mihomo-linux-armv7'
      ;;
    armv6l|armv6)
      asset_name='mihomo-linux-armv6'
      ;;
    i386|i686)
      asset_name='mihomo-linux-386'
      ;;
    *)
      echo "unsupported architecture: ${arch}" >&2
      echo "set MIHOMO_BINARY_SOURCE or MIHOMO_DOWNLOAD_URL manually" >&2
      exit 1
      ;;
  esac

  if [[ "${os}" != "linux" ]]; then
    echo "unsupported operating system: ${os}" >&2
    echo "set MIHOMO_BINARY_SOURCE or MIHOMO_DOWNLOAD_URL manually" >&2
    exit 1
  fi

  if [[ -n "${MIHOMO_DOWNLOAD_URL:-}" ]]; then
    download_url="${MIHOMO_DOWNLOAD_URL}"
  else
    if [[ "${MIHOMO_VERSION}" == "latest" ]]; then
      api_url='https://api.github.com/repos/MetaCubeX/mihomo/releases/latest'
    else
      api_url="https://api.github.com/repos/MetaCubeX/mihomo/releases/tags/${MIHOMO_VERSION}"
    fi

    download_url="$(python3 - "${api_url}" "${asset_name}" <<'PY'
import json
import sys
import urllib.request

api_url = sys.argv[1]
asset_prefix = sys.argv[2]

with urllib.request.urlopen(api_url, timeout=30) as response:
    release = json.load(response)

assets = release.get("assets", [])
matches = [
    asset["browser_download_url"]
    for asset in assets
    if asset["name"].startswith(asset_prefix) and asset["name"].endswith(".gz")
]

if not matches:
    raise SystemExit(1)

def priority(url: str) -> tuple[int, str]:
    name = url.rsplit("/", 1)[-1]
    if "compatible" in name:
        return (0, name)
    if "-v1." in name:
        return (1, name)
    if "-v2." in name:
        return (2, name)
    if "-v3." in name:
        return (3, name)
    if "go123" in name:
        return (4, name)
    if "go120" in name:
        return (5, name)
    return (6, name)

print(sorted(matches, key=priority)[0])
PY
)"

    if [[ -z "${download_url}" ]]; then
      echo "failed to resolve a Mihomo release asset for ${asset_name}" >&2
      exit 1
    fi
  fi

  mkdir -p "${PROJECT_DIR}/bin"
  tmp_gz="$(mktemp "${PROJECT_DIR}/bin/mihomo.XXXXXX.gz")"
  trap 'rm -f "${tmp_gz}"' RETURN

  echo "downloading Mihomo from ${download_url}" >&2
  download_file "${download_url}" "${tmp_gz}"
  gzip -dc "${tmp_gz}" > "${PROJECT_DIR}/bin/mihomo"
  chmod 755 "${PROJECT_DIR}/bin/mihomo"
}

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

if [[ ! -x "${BINARY_SOURCE}" ]]; then
  download_mihomo_binary
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
