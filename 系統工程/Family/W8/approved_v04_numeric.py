"""v0.4 numeric producer definitions, approved by Owner 2026-10-27.
Extracted without changes from the supplied reference; Decimal precision is
set by the calling localcontext, never a process-global setting.
"""
from decimal import Decimal
D=Decimal

def sma(xs, n):
    out = []
    for i in range(len(xs)):
        w = xs[max(0, i-n+1):i+1]
        out.append(sum(w, D(0))/D(n) if len(w) == n and None not in w else None)
    return out

def ema(xs, alpha, min_periods):
    out, value, count = [], None, 0
    for x in xs:
        if x is None:
            value, count = None, 0
        else:
            value = x if value is None else alpha*x + (D(1)-alpha)*value
            count += 1
        out.append(value if count >= min_periods else None)
    return out

def kd(h, l, c):
    rsv = []
    for i in range(len(c)):
        hh, ll = h[max(0, i-8):i+1], l[max(0, i-8):i+1]
        if i < 8 or None in hh or None in ll or c[i] is None:
            rsv.append(None)
        else:
            top, bottom = max(hh), min(ll)
            rsv.append(D(50) if top == bottom else D(100)*(c[i]-bottom)/(top-bottom))
    k = sma(rsv, 3)
    return rsv, k, sma(k, 3)

def macd(c):
    e12, e26 = ema(c, D(2)/13, 12), ema(c, D(2)/27, 26)
    dif = [None if x is None or y is None else x-y for x, y in zip(e12, e26)]
    dea = ema(dif, D(2)/10, 9)
    hist = [None if x is None or y is None else x-y for x, y in zip(dif, dea)]
    return e12, e26, dif, dea, hist

def atr(h, l, c):
    tr = []
    for i in range(len(c)):
        if h[i] is None or l[i] is None or c[i] is None:
            tr.append(None)
        elif i == 0 or c[i-1] is None or (i and tr[-1] is None):
            tr.append(h[i]-l[i])
        else:
            tr.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    return tr, ema(tr, D(1)/14, 14)

def rsi(c):
    delta = [None] + [None if x is None or y is None else x-y for y, x in zip(c, c[1:])]
    gains = [None if x is None else max(x, D(0)) for x in delta]
    losses = [None if x is None else max(-x, D(0)) for x in delta]
    gain, loss = ema(gains, D(1)/14, 14), ema(losses, D(1)/14, 14)
    result = []
    for g, d in zip(gain, loss):
        if g is None or d is None:
            result.append(None)
        elif g == d == 0:
            result.append(D(50))
        elif d == 0:
            result.append(D(100))
        elif g == 0:
            result.append(D(0))
        else:
            result.append(D(100)-D(100)/(D(1)+g/d))
    return gain, loss, result

def emv(h, l, v):
    raw = [None]
    for i in range(1, len(h)):
        dep = (h[i], l[i], h[i-1], l[i-1], v[i])
        if None in dep or v[i] <= 0:
            raw.append(None)
        else:
            mid = (h[i]+l[i])/2
            prior = (h[i-1]+l[i-1])/2
            raw.append((mid-prior)*(h[i]-l[i])*D(100000000)/v[i])
    fast = sma(raw, 3)
    return raw, fast, sma(fast, 3)

def td_count(c):
    """Public counts require 13 contiguous Closes. Never infer unknown prior=0."""
    if len(c) < 13 or None in c[-13:]:
        return None
    signs = [(x > y)-(x < y) for y, x in zip(c[-13:-4], c[-9:])]
    side, length = signs[-1], 0
    for s in reversed(signs):
        if s != side or s == 0:
            break
        length += 1
    return (length if side > 0 else 0, length if side < 0 else 0)

def td_first9(c, side=0):
    current, previous = td_count(c), td_count(c[:-1])
    if current is None:
        return None
    if current[side] != 9:
        return False
    return None if previous is None else previous[side] < 9

def cross(up, down):
    if len(up) < 2 or len(down) < 2:
        return None
    # Short circuit FALSE AND UNKNOWN per specified Kleene semantics.
    if up[-1] is not None and down[-1] is not None and up[-1] <= down[-1]:
        return False
    if None in up[-2:] + down[-2:]:
        return None
    return up[-2] <= down[-2] and up[-1] > down[-1]
