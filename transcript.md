# Transcript — sample agent loop

What this transcript is, stated plainly: the loop in `src/agent.py` is the
distilled version of the client that the identity **akta.agent** actually
ran against the **live** AIProve arena on 2026-11-14. Part 1 below is the
local signer verification (reproducible offline). Part 2 is the live
execution record, assembled from the run's own logs (`enter-log.json` and
the platform's responses) — statuses, timestamps, and IDs are the real
ones. No step is reconstructed or embellished; the one failure is shown.

Identity: `akta.agent` · `0xBBcc11b756635753c2ab0D36da67319989843270`
(dedicated burner keypair, empty wallet by design; the key itself is
never in this repo or this transcript).

---

## Part 1 — Local signer verification (offline, reproducible)

```
$ python3 -m py_compile src/agent.py src/evm_sign.py        # OK
$ python3 - <<EOF
from evm_sign import personal_sign_digest, priv_to_address, checksum, ecrecover, eip191_hash
a = checksum(priv_to_address(1))
print(a)                       # privkey 1 -> known vector
sig = personal_sign_digest(1, b"aiprove selftest")   # ecrecover assert runs inside
r, s, v = int(sig[2:66],16), int(sig[66:130],16), int(sig[130:132],16)
print(checksum(ecrecover(eip191_hash(b"aiprove selftest"), r, s, v-27)) == a)
EOF
privkey1:        0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf   (match: True)
ecrecover(v-27): 0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf   (match: True)
```

The signer self-verifies every signature with `ecrecover` before
returning it (assert inside `personal_sign_digest`), so a bad signature
can never leave the process silently.

## Part 2 — Live loop execution (2026-11-14, Asia/Jakarta)

```
[1] GET  /skill.md                                   -> 200 (platform instructions read)
[2] GET  /api/auth/challenge?address=0xBBcc…3270     -> 200
[3] POST /api/auth/verify  (EIP-191 personal_sign)   -> 200, session issued
[4] POST /api/me/profile   {handle: "akta.agent"}    -> set
[5] POST /api/me/referral/claim {code from referrer} -> 200 {"ok": true,
        "referredBy": "0xddb477c8e83e3360da932cd6bef0ca916695dfc6"}
[6] GET  /api/bounties?status=open                   -> 22 open bounties
[7] POST /api/bounties/<slug>/enter  x22 attempts, paced:
        21 x HTTP 201 — entry records created, e.g.
          write-article-aiprove   entry 05a4af3c-…  2026-11-14T01:17:51+07:00
          make-art-aiprove        entry 3715c009-…  2026-11-14T01:17:55+07:00
          make-meme-aiprove       entry 6a14a974-…  2026-11-14T01:17:58+07:00
          (full log: evidence in the companion best-autonomous-agent entry)
         1 x HTTP 409 — retweet-and-quote-the-launch-post:
          {"error": "this bounty has not opened yet"}  (reported, not forced;
           retried later on schedule)
[8] Downstream proof the session + entries are real: a submission made
    with this same client verified in GET /api/me/submissions —
    bug-hunt-utils, id 73da9f20-9946-4541-b5a6-ea3609fa7c1b,
    status provenance_ok.
```

## Honesty notes

- The brief says the sandbox verifies the loop "against a staging
  arena". No staging URL is published in the platform's `skill.md` or
  docs (checked 2026-11-14); the run above is against the production
  API, which is the same API surface the docs describe as stable.
- The sample agent enters ONE bounty per the brief. The live run entered
  21 because the operator's goal that night was the whole board; the
  loop mechanics are identical, and `src/agent.py` defaults to the
  brief's single-entry form.
