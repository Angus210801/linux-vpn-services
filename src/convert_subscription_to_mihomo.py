#!/usr/bin/env python3
import argparse
import base64
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request


DEFAULT_RULES = [
    "DOMAIN-SUFFIX,local,DIRECT",
    "IP-CIDR,127.0.0.0/8,DIRECT",
    "IP-CIDR,10.0.0.0/8,DIRECT",
    "IP-CIDR,172.16.0.0/12,DIRECT",
    "IP-CIDR,192.168.0.0/16,DIRECT",
    "IP-CIDR,169.254.0.0/16,DIRECT",
    "IP-CIDR6,::1/128,DIRECT",
    "GEOIP,CN,DIRECT",
    "MATCH,PROXY",
]

ANNOUNCEMENT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"TG频道",
        r"官网",
        r"导航",
        r"每日更新",
        r"本次更新",
        r"近期更新",
        r"服务及故障动态",
        r"节点选择",
        r"政策加紧",
        r"倍率",
        r"恢复",
        r"拔线",
        r"失联",
    ]
]

ANNOUNCEMENT_PREFIXES = (
    "📢",
    "❗",
    "💖",
    "❤",
    "💔",
    "🌐",
    "📴",
)

REGION_KEYWORDS = {
    "US": [
        r"🇺🇸",
        r"美国",
        r"美國",
        r"\bUS\b",
        r"洛杉矶",
        r"洛杉磯",
        r"硅谷",
        r"矽谷",
        r"西雅图",
        r"西雅圖",
        r"圣何塞",
        r"聖何塞",
        r"纽约",
        r"紐約",
        r"芝加哥",
    ],
    "DE": [r"🇩🇪", r"德国", r"德國", r"\bDE\b", r"法兰克福", r"法蘭克福", r"柏林", r"慕尼黑"],
    "JP": [r"🇯🇵", r"日本", r"\bJP\b", r"东京", r"東京", r"大阪", r"名古屋"],
    "KR": [r"🇰🇷", r"韩国", r"韓國", r"\bKR\b", r"Korea", r"Seoul", r"首尔", r"首爾"],
    "SG": [r"🇸🇬", r"新加坡", r"狮城", r"獅城", r"\bSG\b", r"Singapore"],
}


def decode_base64(value):
    compact = "".join(value.strip().split())
    compact += "=" * (-len(compact) % 4)
    return base64.urlsafe_b64decode(compact).decode("utf-8", errors="replace")


def fetch_text(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "mihomo-subscription-converter/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception:
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-fsSL",
                    "-A",
                    "ClashforWindows/0.20.39",
                    url,
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            return result.stdout.decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(
                "failed to fetch subscription URL; try downloading it in a browser and "
                "pass the saved file to this script"
            ) from exc


def parse_ss(uri):
    raw = uri[5:]
    name = ""
    if "#" in raw:
        raw, fragment = raw.split("#", 1)
        name = urllib.parse.unquote(fragment)

    plugin = None
    if "?" in raw:
        raw, query = raw.split("?", 1)
        params = urllib.parse.parse_qs(query)
        plugin_values = params.get("plugin")
        if plugin_values:
            plugin = plugin_values[0]

    if "@" in raw:
        userinfo, server_part = raw.rsplit("@", 1)
        method_password = decode_base64(userinfo)
    else:
        decoded = decode_base64(raw)
        method_password, server_part = decoded.rsplit("@", 1)

    method, password = method_password.split(":", 1)
    host, port = server_part.rsplit(":", 1)
    proxy = {
        "name": name or f"{host}:{port}",
        "type": "ss",
        "server": host.strip("[]"),
        "port": int(port),
        "cipher": method,
        "password": password,
        "udp": True,
    }

    if plugin:
        if plugin.startswith("obfs-local"):
            proxy["plugin"] = "obfs"
            opts = dict(urllib.parse.parse_qsl(plugin.split(";", 1)[1] if ";" in plugin else ""))
            proxy["plugin-opts"] = {
                "mode": opts.get("obfs", "http"),
                "host": opts.get("obfs-host", ""),
            }
        else:
            raise ValueError(f"unsupported ss plugin: {plugin}")

    return proxy


def unique_names(proxies):
    seen = {}
    for proxy in proxies:
        name = proxy["name"]
        count = seen.get(name, 0)
        seen[name] = count + 1
        if count:
            proxy["name"] = f"{name} {count + 1}"
    return proxies


def parse_region_patterns(region_codes):
    patterns = []
    invalid = []
    for code in region_codes:
        normalized = code.strip().upper()
        keywords = REGION_KEYWORDS.get(normalized)
        if not keywords:
            invalid.append(code)
            continue
        patterns.extend(re.compile(pattern, re.IGNORECASE) for pattern in keywords)
    if invalid:
        raise ValueError(f"unsupported region codes: {', '.join(invalid)}")
    return patterns


def is_announcement_proxy(proxy):
    name = proxy["name"]
    return name.startswith(ANNOUNCEMENT_PREFIXES) or any(
        pattern.search(name) for pattern in ANNOUNCEMENT_PATTERNS
    )


def is_allowed_region_proxy(proxy, region_patterns):
    name = proxy["name"]
    return any(pattern.search(name) for pattern in region_patterns)


def filter_proxies(proxies, region_patterns):
    filtered = [proxy for proxy in proxies if not is_announcement_proxy(proxy)]
    filtered = [proxy for proxy in filtered if is_allowed_region_proxy(proxy, region_patterns)]
    if not filtered:
        raise RuntimeError("no proxies matched the requested allowed regions")
    return filtered


def parse_subscription(text):
    if "://" not in text[:200]:
        text = decode_base64(text)

    proxies = []
    skipped = []
    for line in text.replace("\r", "\n").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if line.startswith("ss://"):
                proxies.append(parse_ss(line))
            else:
                skipped.append(line.split("://", 1)[0])
        except Exception as exc:
            skipped.append(f"{line.split('://', 1)[0]} ({exc})")

    return unique_names(proxies), skipped


def build_config(proxies):
    names = [proxy["name"] for proxy in proxies]
    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "unified-delay": True,
        "tcp-concurrent": True,
        "log-level": "info",
        "external-controller": "127.0.0.1:9090",
        "profile": {
            "store-selected": True,
            "store-fake-ip": True,
        },
        "dns": {
            "enable": True,
            "listen": "127.0.0.1:1053",
            "ipv6": False,
            "enhanced-mode": "fake-ip",
            "fake-ip-range": "198.18.0.1/16",
            "nameserver": ["223.5.5.5", "119.29.29.29"],
            "fallback": ["1.1.1.1", "8.8.8.8"],
        },
        "tun": {
            "enable": True,
            "stack": "system",
            "dns-hijack": ["any:53", "tcp://any:53"],
            "auto-route": True,
            "auto-redirect": True,
            "auto-detect-interface": True,
        },
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "PROXY",
                "type": "select",
                "proxies": ["AUTO", "DIRECT"] + names,
            },
            {
                "name": "AUTO",
                "type": "url-test",
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": names,
            },
        ],
        "rules": DEFAULT_RULES,
    }


def write_yaml(value, indent=0):
    prefix = " " * indent
    lines = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.extend(write_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}{key}: {json.dumps(item, ensure_ascii=False)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(write_yaml(item, indent + 2))
            else:
                lines.append(f"{prefix}- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append(f"{prefix}{json.dumps(value, ensure_ascii=False)}")
    return lines


def main():
    parser = argparse.ArgumentParser(description="Convert a Base64 subscription to a Mihomo config.")
    parser.add_argument("source", help="subscription URL or local subscription file")
    parser.add_argument("-o", "--output", default="config.yaml", help="output Mihomo config path")
    parser.add_argument(
        "--regions",
        default="US,DE,JP,KR,SG",
        help="comma-separated region codes to keep (default: US,DE,JP,KR,SG)",
    )
    args = parser.parse_args()

    if args.source.startswith(("http://", "https://")):
        text = fetch_text(args.source)
    else:
        with open(args.source, "r", encoding="utf-8") as file:
            text = file.read()

    proxies, skipped = parse_subscription(text)
    if not proxies:
        print("no supported proxies found", file=sys.stderr)
        return 1

    region_codes = [item.strip() for item in args.regions.split(",") if item.strip()]
    region_patterns = parse_region_patterns(region_codes)
    proxies = filter_proxies(proxies, region_patterns)
    config = build_config(proxies)
    with open(args.output, "w", encoding="utf-8") as file:
        file.write("\n".join(write_yaml(config)))
        file.write("\n")

    print(f"wrote {args.output} with {len(proxies)} proxies")
    if skipped:
        print(f"skipped {len(skipped)} unsupported or invalid entries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
