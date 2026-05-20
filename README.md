# linux-vpn-service

A small Ubuntu Server / CLI-only VPN service project built around **Mihomo**, **TUN mode**, and **systemd**.

## How it works

This project implements the VPN service in four layers:

1. **Subscription conversion**
   - `src/convert_subscription_to_mihomo.py` fetches a generic airport subscription URL.
   - It decodes the subscription, parses supported `ss://` nodes, removes announcement-style entries, and keeps only the configured regions.
   - It emits a Mihomo config with:
     - `tun.enable: true`
     - `auto-route: true`
     - `auto-redirect: true`
     - `dns-hijack`
     - `AUTO` `url-test` group for automatic failover / best-node selection

2. **System-wide traffic takeover**
   - Mihomo runs in **TUN mode** so the server can proxy outbound traffic without any desktop GUI.
   - DNS is handled inside Mihomo with `fake-ip` mode and DNS hijacking for stable CLI/server usage.

3. **Long-running service management**
   - `deploy/mihomo.service` runs Mihomo under `systemd`.
   - `Restart=always` keeps it running across failures.
   - `enable` makes it start automatically on boot.

4. **Automatic subscription refresh**
   - `deploy/mihomo-subscription-update.service` regenerates `/etc/mihomo/config.yaml`.
   - `deploy/mihomo-subscription-update.timer` refreshes the subscription every 6 hours and after boot.

## Current region policy

The default allowed regions are:

- `US`
- `DE`
- `JP`
- `KR`
- `SG`

You can override them with `MIHOMO_ALLOWED_REGIONS`, for example:

```bash
MIHOMO_ALLOWED_REGIONS=US,JP,SG
```

## Project layout

```text
linux-vpn-services/
├── README.md
├── bin/
├── deploy/
│   ├── install.sh
│   ├── mihomo.service
│   ├── mihomo-subscription-update.service
│   ├── mihomo-subscription-update.timer
│   └── mihomo-update-subscription.sh
├── env/
│   └── subscription.env.example
└── src/
    └── convert_subscription_to_mihomo.py
```

## Prerequisites

- Ubuntu 22.04 or similar Linux with `systemd`
- `python3`
- `gzip`
- root access for installation

## Install

1. Put your subscription settings in `env/subscription.env`, or export them in the shell.
2. Optionally provide a local Mihomo binary, or let the installer download one automatically.
3. Run the installer as root.

Example:

```bash
cd ~/linux-vpn-services
cp env/subscription.env.example env/subscription.env
# edit env/subscription.env and set your real subscription URL
sudo ./deploy/install.sh
```

You can still use shell environment variables, but note that plain `sudo` may drop them. If you prefer that route, use `sudo -E` after exporting:

```bash
export MIHOMO_SUBSCRIPTION_URL='https://example.com/subscription'
export MIHOMO_ALLOWED_REGIONS='US,DE,JP,KR,SG'
sudo -E ./deploy/install.sh
```

Installer behavior:

- If `bin/mihomo` exists, it uses that.
- If `MIHOMO_BINARY_SOURCE` is set, it uses that path.
- Otherwise it downloads a matching Mihomo binary from the official GitHub release for the current Linux architecture.
- Download fallback order is: `curl` -> `wget` -> `python3 urllib`.

If the binary is elsewhere:

```bash
export MIHOMO_BINARY_SOURCE=/path/to/mihomo
sudo ./deploy/install.sh
```

If you want a specific Mihomo release tag instead of the latest:

```bash
export MIHOMO_VERSION=v1.19.25
sudo ./deploy/install.sh
```

If you need to force a custom binary URL:

```bash
export MIHOMO_DOWNLOAD_URL='https://github.com/MetaCubeX/mihomo/releases/download/v1.19.25/mihomo-linux-amd64-compatible-v1.19.25.gz'
sudo ./deploy/install.sh
```

## Common operations

```bash
sudo systemctl start mihomo
sudo systemctl stop mihomo
sudo systemctl restart mihomo
systemctl status mihomo --no-pager
journalctl -u mihomo -f
```

Subscription refresh:

```bash
sudo systemctl start mihomo-subscription-update.service
systemctl status mihomo-subscription-update.timer --no-pager
```

## Notes

- This project does **not** store your real subscription token in source files.
- The installed runtime configuration lives in:
  - `/etc/mihomo/config.yaml`
  - `/etc/mihomo/subscription.env`
- The default auto-selection behavior uses Mihomo's `url-test` group, so node switching is automatic for new connections when a better or still-alive node is found.
