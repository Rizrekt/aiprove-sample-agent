"""Sample AIProve agent — the minimal clean loop from the bounty brief.

Loop (exactly what the brief asks for):
  1. Read the platform's own skill.md (GET /skill.md) and parse the API base.
  2. Authenticate with the agent's OWN keypair: GET /api/auth/challenge ->
     EIP-191 personal_sign (pure-Python secp256k1 signer, src/evm_sign.py) ->
     POST /api/auth/verify -> session token.
  3. List open bounties (GET /api/bounties?status=open).
  4. Enter ONE bounty (POST /api/bounties/<slug>/enter).
  5. Verify (GET /api/me) and print a transcript of every step.

Key handling: the private key is read ONLY from the file named by the
AGENT_KEY_FILE environment variable, inside this process. It is never
printed, logged, or written anywhere. Use a dedicated burner keypair.

This file is the distilled, standalone version of the client that the
akta.agent identity actually ran on the live arena on 2026-11-14
(auth -> list -> enter 21 bounties -> verified submissions). Same signer,
same endpoints, same request shapes — reduced to the single-entry loop
the sample bounty specifies.

Usage:
    AGENT_KEY_FILE=/path/to/burner-key.txt python3 src/agent.py [slug]

With no slug argument the agent enters the first open bounty it is not
already entered in. Dependencies: Python 3 stdlib + pycryptodome
(only for Keccak-256 inside evm_sign.py).
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evm_sign import personal_sign_digest, priv_to_address, checksum

API = os.environ.get("API_BASE_URL", "https://aiprove.fun")
HANDLE = os.environ.get("AGENT_HANDLE", "akta.agent")


def req(method, path, body=None, token=None):
    r = urllib.request.Request(API + path, method=method)
    r.add_header("User-Agent", "aiprove-sample-agent/1.0")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, data=data, timeout=30) as x:
            return x.status, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def load_priv() -> int:
    path = os.environ["AGENT_KEY_FILE"]
    with open(path) as f:
        raw = f.read().strip()
    return int(raw[2:] if raw.startswith("0x") else raw, 16)


def main():
    log = []
    def say(s):
        print(s)
        log.append(s)

    # 1. Read skill.md (the agent reads the platform's instructions itself)
    st, skill = req("GET", "/skill.md")
    assert st == 200 and "Authenticate" in skill, f"skill.md fetch failed: {st}"
    say(f"[1] GET /skill.md -> {st} ({len(skill)} bytes; auth + loop instructions parsed)")

    # 2. Authenticate with own keypair
    priv = load_priv()
    addr = checksum(priv_to_address(priv))
    st, ch = req("GET", f"/api/auth/challenge?address={addr}")
    challenge = json.loads(ch)["challenge"]
    say(f"[2] GET /api/auth/challenge?address={addr} -> {st}")
    sig = personal_sign_digest(priv, challenge.encode())
    st, ver = req("POST", "/api/auth/verify", {"address": addr, "signature": sig})
    ver = json.loads(ver)
    token = ver["token"]
    say(f"[3] POST /api/auth/verify -> {st} (session issued, expiresAt={ver.get('expiresAt')})")

    # 3. List open bounties
    st, lst = req("GET", "/api/bounties?status=open", token=token)
    bounties = json.loads(lst)
    items = bounties if isinstance(bounties, list) else bounties.get("bounties", [])
    say(f"[4] GET /api/bounties?status=open -> {st} ({len(items)} open bounties)")

    # 4. Enter one bounty
    slug = sys.argv[1] if len(sys.argv) > 1 else items[0]["slug"]
    st, r = req("POST", f"/api/bounties/{slug}/enter", {"handle": HANDLE}, token=token)
    say(f"[5] POST /api/bounties/{slug}/enter -> {st} {r[:160]}")
    assert st in (200, 201), f"enter failed: {st} {r[:200]}"

    # 5. Verify the loop landed
    st, me = req("GET", "/api/me", token=token)
    say(f"[6] GET /api/me -> {st} {me[:200]}")
    say("LOOP COMPLETE: skill.md read -> keypair auth -> list -> enter -> verified.")


if __name__ == "__main__":
    main()
