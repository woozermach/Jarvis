# -*- coding: utf-8 -*-
"""Случайная выборка из признаков ACAV100M (16 ГБ, ~2000 часов) — около четверти, чтобы файл целиком
помещался в память машины GitHub (16 ГБ) и обучение не упиралось в случайное чтение с диска."""
import sys
import numpy as np
from numpy.lib.format import open_memmap

src, dst = sys.argv[1], sys.argv[2]
frac = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
x = np.load(src, mmap_mode="r")
n = x.shape[0]
block = 20000                                  # берём блоками: быстро и сохраняет разнообразие
starts = np.arange(0, n, block)
rng = np.random.default_rng(7)
pick = np.sort(rng.choice(starts, size=max(1, int(len(starts) * frac)), replace=False))
total = sum(min(block, n - s) for s in pick)
out = open_memmap(dst, mode="w+", dtype=x.dtype, shape=(total,) + x.shape[1:])
i = 0
for s in pick:
    e = min(n, s + block)
    out[i:i + e - s] = x[s:e]
    i += e - s
out.flush()
print(f"{src}: {x.shape} → {dst}: {out.shape}")
