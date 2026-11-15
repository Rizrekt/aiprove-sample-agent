"""Minimal EIP-191 personal_sign signer/verifier using pycryptodome only.

Implements secp256k1 point math via Crypto.PublicKey.ECC, Keccak-256 via
Crypto.Hash.keccak, deterministic RFC6979 ECDSA via Crypto.Signature.DSS,
and ecrecover for self-verification. No private key is printed anywhere.
"""
import sys
from Crypto.Hash import keccak, SHA256
from Crypto.PublicKey import ECC
from Crypto.Signature import DSS

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def keccak256(b: bytes) -> bytes:
    h = keccak.new(digest_bits=256)
    h.update(b)
    return h.digest()


def priv_to_pub_point(priv: int):
    return _point_mul(priv, G)


def priv_to_address(priv: int) -> str:
    x, y = priv_to_pub_point(priv)
    pub = x.to_bytes(32, "big") + y.to_bytes(32, "big")
    return "0x" + keccak256(pub)[-20:].hex()


def checksum(addr_hex_lower: str) -> str:
    a = addr_hex_lower.lower().replace("0x", "")
    h = keccak256(a.encode()).hex()
    out = "0x"
    for c, hh in zip(a, h):
        out += c.upper() if int(hh, 16) >= 8 else c
    return out


def eip191_hash(msg: bytes) -> bytes:
    prefix = b"\x19Ethereum Signed Message:\n" + str(len(msg)).encode()
    return keccak256(prefix + msg)


def _point_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    y3 = (lam * (x1 - x3) - y1) % P
    return x3, y3


def _point_mul(k, point):
    r = None
    a = point
    while k:
        if k & 1:
            r = _point_add(r, a)
        a = _point_add(a, a)
        k >>= 1
    return r


G = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)


def ecrecover(msg_hash: bytes, r: int, s: int, v: int) -> str:
    """v in {0,1}. Returns lowercase address."""
    x = r + (v >> 1) * N
    if x >= P:
        raise ValueError("x out of range")
    alpha = (pow(x, 3, P) + 7) % P
    y = pow(alpha, (P + 1) // 4, P)
    if (y & 1) != (v & 1):
        y = P - y
    R = (x, y)
    e = int.from_bytes(msg_hash, "big")
    rinv = pow(r, -1, N)
    # Q = r^-1 (s*R - e*G)
    sR = _point_mul(s, R)
    eG = _point_mul(e % N, G)
    neg_eG = (eG[0], (-eG[1]) % P)
    Q = _point_mul(rinv, _point_add(sR, neg_eG))
    pub = Q[0].to_bytes(32, "big") + Q[1].to_bytes(32, "big")
    return "0x" + keccak256(pub)[-20:].hex()


def personal_sign(priv: int, msg: bytes) -> str:
    h = eip191_hash(msg)
    key = ECC.construct(curve="secp256k1", d=priv)
    signer = DSS.new(key, "deterministic-rfc6979", encoding="binary")
    sig = signer.sign(SHA256.new(h))  # DSS hashes again; see sign_digest below
    raise RuntimeError("use personal_sign_digest")


def personal_sign_digest(priv: int, msg: bytes) -> str:
    """Sign the EIP-191 digest directly (DSS over the raw 32-byte digest
    treated as the message hash via a pre-hashed construction).

    pycryptodome DSS always hashes the input; to sign an existing digest we
    do ECDSA manually with an RFC6979 nonce derived via HMAC-SHA256
    (RFC 6979 section 3.2, same construction eth_account/coincurve use).
    """
    import hmac as hmac_mod
    import hashlib

    digest = eip191_hash(msg)
    z = int.from_bytes(digest, "big")
    x = priv.to_bytes(32, "big")
    h1 = (z % N).to_bytes(32, "big")
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac_mod.new(k, v + b"\x00" + x + h1, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    k = hmac_mod.new(k, v + b"\x01" + x + h1, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac_mod.new(k, v, hashlib.sha256).digest()
        nonce = int.from_bytes(v, "big")
        if 1 <= nonce < N:
            break
        k = hmac_mod.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac_mod.new(k, v, hashlib.sha256).digest()
    R = _point_mul(nonce, G)
    r = R[0] % N
    s = (pow(nonce, -1, N) * (z + r * priv)) % N
    recid = R[1] & 1
    if R[0] >= N:
        recid |= 2
    if s > N // 2:
        s = N - s
        recid ^= 1
    v_out = 27 + recid
    sig = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v_out])
    # self-verify
    rec = ecrecover(digest, r, s, recid)
    assert rec == priv_to_address(priv), f"recover mismatch {rec} vs {priv_to_address(priv)}"
    return "0x" + sig.hex()


if __name__ == "__main__":
    # Test vectors (public, well-known):
    # privkey 1 -> 0x7e5f4552091a69125d5dfcb7b8c2659029395bdf
    a1 = priv_to_address(1)
    assert a1 == "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf", a1
    assert checksum(a1) == "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
    sig = personal_sign_digest(1, b"hello world")
    print("selftest OK:", checksum(a1), "sig len", (len(sig) - 2) // 2)
