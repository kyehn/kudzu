#!/usr/bin/env bash
# Capture real opencode zen wire data for overlays/maki/opencode/.
#
# What this does, end to end:
#   1. starts a mitmproxy CONNECT proxy on 127.0.0.1:8897
#   2. points a real `opencode` CLI (npm i -g opencode-ai@latest) at it via
#      HTTPS_PROXY / SSL_CERT_FILE (the CLI's own bun TLS ClientHello is the
#      one being fingerprinted, and its requests are decrypted by mitmproxy)
#   3. runs one chat-completions model (mimo) and one responses model (muse)
#      so both zen wires get real captures
#   4. saves the raw original request/response pairs + TLS fingerprint
#
# Raw original data only — no notes, no processing (per overlays/maki/README).
# Custom attributes follow OpenTelemetry field naming + RFC original HTTP/TLS fields.
#
# Prerequisites:
#   npm i -g opencode-ai@latest
#   pip install mitmproxy
#
# Usage:
#   cd overlays/maki/opencode && ./capture.sh
#
# Output files (written next to this script unless OUT_DIR is set):
#   chat-completions.json       — chat-completions wire (mimo-v2.5-free)
#   chat-completions-title.json — title-generation POST, chat-completions wire
#   responses.json              — responses wire (muse-spark-1.3-contributor-free)
#   responses-title.json        — title-generation POST, responses wire
#   tls-fingerprint.json        — real bun ClientHello (ja3/ja4 + raw fields)

set -euo pipefail

PROXY_PORT="${PROXY_PORT:-8897}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="${OUT_DIR:-$SCRIPT_DIR}"
CA_CERT="${MITMPROXY_CA:-$HOME/.mitmproxy/mitmproxy-ca-cert.pem}"

command -v opencode >/dev/null || { echo "need: npm i -g opencode-ai@latest" >&2; exit 1; }
command -v mitmdump >/dev/null || { echo "need: pip install mitmproxy" >&2; exit 1; }
[[ -f "$CA_CERT" ]] || { echo "trust $CA_CERT with your system CA store, or run mitmproxy once" >&2; exit 1; }

ADDON=$(mktemp /tmp/opencode-capture-addon-XXXXXX.py)
cat > "$ADDON" << 'PYEOF'
"""Real opencode zen capture addon (see capture.sh header for context)."""
import hashlib
import json
import os
import traceback
from datetime import datetime, timezone

OUT = os.environ.get("OUT_DIR", ".")
GREASE = {0x0a0a, 0x1a1a, 0x2a2a, 0x3a3a, 0x4a4a, 0x5a5a, 0x6a6a, 0x7a7a}
TLS_MAPPER = {0x0300: "10", 0x0301: "11", 0x0302: "12", 0x0303: "13", 0x0304: "13"}
EXT_NAMES = {
    0: "server_name", 5: "status_request", 10: "supported_groups",
    11: "ec_point_formats", 13: "signature_algorithms",
    16: "alpn", 18: "signed_certificate_timestamp",
    23: "extended_master_secret", 34: "session_ticket", 35: "pre_shared_key",
    43: "supported_versions", 44: "cookie", 45: "psk_key_exchange_modes",
    50: "signature_algorithms_cert", 51: "key_share", 65281: "renegotiation_info",
}
_flows = []


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ja4_tls(version, sni_is_domain, ciphers, extensions, sigalgs, alpn_list):
    c = [f"{x:04x}" for x in ciphers if x not in GREASE]
    cipher_len = "{:02d}".format(min(len(c), 99))
    cipher_hash = hashlib.sha256(",".join(sorted(c)).encode()).hexdigest()[:12]
    e = [f"{x:04x}" for x in extensions if x not in GREASE]
    ext_len = "{:02d}".format(min(len(e), 99))
    e2 = [x for x in e if x not in ("0000", "0010")]
    ext_str = ",".join(sorted(e2))
    if sigalgs:
        ext_str += "_" + ",".join(f"{x:04x}" for x in sigalgs)
    ext_hash = hashlib.sha256(ext_str.encode()).hexdigest()[:12]
    alpn = alpn_list[0] if alpn_list else "00"
    if len(alpn) > 2:
        alpn = alpn[0] + alpn[-1]
    v = TLS_MAPPER.get(version, "00")
    sni = "d" if sni_is_domain else "i"
    return f"t{v}{sni}{cipher_len}{ext_len}{alpn}_{cipher_hash}_{ext_hash}"


def _vec16(body):
    out = []
    if len(body) >= 2:
        n = int.from_bytes(body[:2], "big")
        off = 2
        while off + 2 <= min(2 + n, len(body)):
            out.append(int.from_bytes(body[off:off + 2], "big"))
            off += 2
    return out


def tls_clienthello(data):
    try:
        ch = data.client_hello
        try:
            sni = ch.sni
        except Exception:
            sni = None
        alpn = [p.decode() if isinstance(p, bytes) else p for p in ch.alpn_protocols]
        ciphers = list(ch.cipher_suites)
        exts, groups, sigalgs, versions = [], [], [], []
        for t, body in ch.extensions:
            exts.append(t)
            if t == 10:
                groups = _vec16(body)
            elif t == 13:
                sigalgs = _vec16(body)
            elif t == 43:
                # supported_versions: 2-byte versions, no length prefix (ClientHello)
                for off in range(0, len(body) - 1, 2):
                    versions.append(int.from_bytes(body[off:off + 2], "big"))
        body = ch.raw_bytes(wrap_in_record=False)
        # raw ClientHello begins with the 2-byte legacy_version
        ver = int.from_bytes(body[0:2], "big") if len(body) >= 2 else 0x0303
        ja3_string = f"{ver},{','.join(map(str, ciphers))},{','.join(map(str, exts))},{','.join(map(str, groups))},0"
        ja3 = hashlib.md5(ja3_string.encode()).hexdigest()
        ja4_ver = max(versions) if versions else ver
        sni_is_domain = bool(sni) and not all(c.isdigit() or c == "." for c in sni)
        ja4 = ja4_tls(ja4_ver, sni_is_domain, ciphers, exts, sigalgs, alpn)
        try:
            client = data.context.client
            addr = client.address if hasattr(client, "address") and client.address else client.peername
            client_addr = f"{addr[0]}:{addr[1]}"
        except Exception:
            client_addr = "unknown"
        fp = {
            "event": "client_hello",
            "client_addr": client_addr,
            "sni": sni,
            "alpn": alpn,
            "cipher_suites": ciphers,
            "cipher_suites_hex": [f"{x:04x}" for x in ciphers],
            "extensions": exts,
            "extension_names": [EXT_NAMES.get(t, f"0x{t:04x}") for t in exts],
            "groups": groups,
            "groups_hex": [f"{x:04x}" for x in groups],
            "sigalgs": sigalgs,
            "sigalgs_hex": [f"{x:04x}" for x in sigalgs],
            "ja3": ja3,
            "ja3_string": ja3_string,
            "ja4": ja4,
            "ts": now_iso(),
        }
        if sni and (sni == "opencode.ai" or sni.endswith("opencode.ai") or "zenmux" in sni):
            with open(os.path.join(OUT, "tls-fingerprint.json"), "w") as f:
                json.dump(fp, f, indent="\t", ensure_ascii=False)
                f.write("\n")
            print("TLS fingerprint saved:", sni, ja3, ja4, flush=True)
    except Exception:
        traceback.print_exc()


def _save(flow, name):
    body = flow.request.get_text() or ""
    resp_text = flow.response.get_text() if flow.response else ""
    entry = {
        "request": {
            "timestamp": now_iso(),
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "scheme_tls": flow.request.scheme == "https",
            "headers": {k: v for k, v in flow.request.headers.items()},
            "body": body,
            "content_length": len(body.encode("utf8")),
        },
        "response": {
            "timestamp": now_iso(),
            "status": flow.response.status_code if flow.response else 0,
            "reason": flow.response.reason if flow.response else "",
            "headers": {k: v for k, v in flow.response.headers.items()} if flow.response else {},
            "body": resp_text,
            "content_length": len(resp_text.encode("utf8")),
        },
    }
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(entry, f, indent="\t", ensure_ascii=False)
        f.write("\n")
    print("saved:", name, entry["request"]["url"], entry["request"]["content_length"],
          "req bytes,", entry["response"]["content_length"], "resp bytes", flush=True)


def request(flow):
    if flow.request.method == "POST" and ("/chat/completions" in flow.request.path or "/responses" in flow.request.path):
        _flows.append(flow)


def response(flow):
    global _flows
    if flow not in _flows:
        return
    _flows.remove(flow)
    try:
        body = flow.request.get_text() or ""
        if "/chat/completions" in flow.request.path:
            if "title generator" in body:
                _save(flow, "chat-completions-title.json")
            else:
                _save(flow, "chat-completions.json")
        elif "/responses" in flow.request.path:
            if "title generator" in body:
                _save(flow, "responses-title.json")
            else:
                _save(flow, "responses.json")
    except Exception:
        traceback.print_exc()
PYEOF

echo "=== opencode zen capture ==="
echo "Proxy:  http://127.0.0.1:$PROXY_PORT  (CONNECT; CLI TLS terminated by mitmproxy)"
echo "CA:     $CA_CERT"
echo "Output: $OUT_DIR"
echo ""

export OUT_DIR SSL_CERT_FILE="$CA_CERT"
export HTTPS_PROXY="http://127.0.0.1:$PROXY_PORT"
export HTTP_PROXY="$HTTPS_PROXY" ALL_PROXY="$HTTPS_PROXY"

FRESH_HOME=$(mktemp -d /tmp/opencode-capture-home-XXXXXX)
mitmdump -q -s "$ADDON" --listen-host 127.0.0.1 --listen-port "$PROXY_PORT" \
    --set confdir="$HOME/.mitmproxy" >/tmp/opencode-mitm.log 2>&1 &
PROXY_PID=$!
trap 'kill $PROXY_PID 2>/dev/null || true; rm -f "$ADDON"; rm -rf "$FRESH_HOME"' EXIT

sleep 3

# chat-completions wire
HOME="$FRESH_HOME" timeout 300 opencode run --model opencode/mimo-v2.5-free --format json \
  "Reply with exactly: HI" >/dev/null 2>&1 || true
# responses wire
HOME="$FRESH_HOME" timeout 300 opencode run --model opencode/muse-spark-1.3-contributor-free --format json \
  "Reply with exactly: HI" >/dev/null 2>&1 || true

# give aborted title flows time to finish; most complete within seconds
sleep 30

kill $PROXY_PID 2>/dev/null || true
wait $PROXY_PID 2>/dev/null || true
trap - EXIT
rm -f "$ADDON"
rm -rf "$FRESH_HOME"

echo ""
echo "=== captured ==="
for f in chat-completions.json chat-completions-title.json responses.json responses-title.json tls-fingerprint.json; do
    if [[ -f "$OUT_DIR/$f" ]]; then
        echo "  $OUT_DIR/$f  ($(stat -c%s "$OUT_DIR/$f") bytes)"
    else
        echo "  (missing) $f — rerun with a longer prompt if a title flow aborted"
    fi
done

# quick self-check: every saved capture must be real zen TLS traffic
python3 - << 'PY'
import json, os, sys
ok = True
for name in ("chat-completions.json", "chat-completions-title.json", "responses.json", "responses-title.json"):
    p = os.path.join(os.environ.get("OUT_DIR", "."), name)
    if not os.path.exists(p):
        continue
    d = json.load(open(p))
    r = d["request"]
    ok &= r["scheme_tls"] is True
    ok &= "opencode.ai/zen/v1" in r["url"]
    sys.stderr.write(f"{name}: tls={r['scheme_tls']} url={r['url']} req={r['content_length']} resp={d['response']['content_length']}\n")
print("SELF-CHECK:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
PY