# -*- coding: utf-8 -*-
"""Ed25519 (RFC 8032) на чистом Python — для проверки ключей лицензии без внешних пакетов.
Медленно (~30 мс на проверку), но нужно один раз при запуске."""
import hashlib

p = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
d = -121665 * pow(121666, p - 2, p) % p
SQRT_M1 = pow(2, (p - 1) // 4, p)


def _inv(x):
    return pow(x, p - 2, p)


def _xrecover(y):
    xx = (y * y - 1) * _inv(d * y * y + 1) % p
    x = pow(xx, (p + 3) // 8, p)
    if (x * x - xx) % p:
        x = x * SQRT_M1 % p
    if (x * x - xx) % p:
        raise ValueError("точка не на кривой")
    return x


_By = 4 * _inv(5) % p
_Bx = _xrecover(_By)
if _Bx & 1:
    _Bx = p - _Bx
B = (_Bx, _By, 1, _Bx * _By % p)
ZERO = (0, 1, 1, 0)


def _add(P, Q):
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    a = (y1 - x1) * (y2 - x2) % p
    b = (y1 + x1) * (y2 + x2) % p
    c = t1 * 2 * d * t2 % p
    dd = z1 * 2 * z2 % p
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % p, g * h % p, f * g % p, e * h % p)


def _mul(s, P):
    Q = ZERO
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _encode(P):
    x, y, z, _ = P
    zi = _inv(z)
    x, y = x * zi % p, y * zi % p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decode(s):
    if len(s) != 32:
        raise ValueError("длина")
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= p:
        raise ValueError("y")
    x = _xrecover(y)
    if (x & 1) != sign:
        if x == 0:
            raise ValueError("x")
        x = p - x
    return (x, y, 1, x * y % p)


def _eq(P, Q):
    return (P[0] * Q[2] - Q[0] * P[2]) % p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % p == 0


def _h(m):
    return hashlib.sha512(m).digest()


def _expand(sk):
    h = _h(sk)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(sk: bytes) -> bytes:
    return _encode(_mul(_expand(sk)[0], B))


def sign(sk: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(sk)
    A = _encode(_mul(a, B))
    r = int.from_bytes(_h(prefix + msg), "little") % L
    R = _encode(_mul(r, B))
    k = int.from_bytes(_h(R + A + msg), "little") % L
    return R + int.to_bytes((r + k * a) % L, 32, "little")


def verify(pk: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        if len(sig) != 64:
            return False
        A = _decode(pk)
        R = _decode(sig[:32])
        s = int.from_bytes(sig[32:], "little")
        if s >= L:
            return False
        k = int.from_bytes(_h(sig[:32] + pk + msg), "little") % L
        return _eq(_mul(s, B), _add(R, _mul(k, A)))
    except Exception:
        return False
