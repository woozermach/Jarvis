# -*- coding: utf-8 -*-
"""Данные для обучения слова активации (запускается в GitHub Actions, см. .github/workflows/wakeword.yml):
эхо комнат MIT (RIR) и фоновые шумы AudioSet → wav 16 кГц. Без пакета `datasets`: качаем файлы напрямую с Hugging Face."""
import io
import sys
import tarfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from huggingface_hub import hf_hub_download, list_repo_files

out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")


def to16k(x, sr):
    if x.ndim > 1:
        x = x.mean(axis=1)
    if sr != 16000:
        from math import gcd
        g = gcd(int(sr), 16000)
        x = resample_poly(x, 16000 // g, int(sr) // g)
    return (np.clip(x, -1, 1) * 32767).astype(np.int16)


# 1) Room impulse responses (MIT)
rir = out / "mit_rirs"
rir.mkdir(parents=True, exist_ok=True)
repo = "davidscripka/MIT_environmental_impulse_responses"
import pyarrow.parquet as pq
n = 0
for f in list_repo_files(repo, repo_type="dataset"):
    if f.endswith(".parquet"):
        t = pq.read_table(hf_hub_download(repo, f, repo_type="dataset")).to_pydict()
        for a in t["audio"]:
            x, sr = sf.read(io.BytesIO(a["bytes"]), dtype="float32")
            sf.write(rir / (Path(a.get("path") or f"rir{n}.wav").stem + ".wav"), to16k(x, sr), 16000)
            n += 1
    elif f.endswith(".wav"):
        x, sr = sf.read(hf_hub_download(repo, f, repo_type="dataset"), dtype="float32")
        sf.write(rir / Path(f).name, to16k(x, sr), 16000)
        n += 1
print("RIR:", n)

# 2) Background: несколько файлов сбалансированной части AudioSet (речь, музыка, шумы); формат репозитория менялся —
#    ищем и .tar (flac внутри), и .parquet (байты аудио в колонке)
bg = out / "background"
bg.mkdir(parents=True, exist_ok=True)
m = 0
files = sorted(f for f in list_repo_files("agkphysics/AudioSet", repo_type="dataset")
               if ("bal" in f.lower()) and f.endswith((".tar", ".parquet")))
print("AudioSet files:", len(files), files[:5])
want = int(sys.argv[2]) if len(sys.argv) > 2 else 6000  # сколько клипов по ~10 с (≈ 16 часов)


def put(raw, name):
    global m
    try:
        x, sr = sf.read(io.BytesIO(raw), dtype="float32")
        if len(x) / sr >= 1.0:
            sf.write(bg / (Path(name).stem + ".wav"), to16k(x, sr), 16000)
            m += 1
    except Exception as e:
        print("skip", name, e)


for f in files:
    if m >= want:
        break
    p = hf_hub_download("agkphysics/AudioSet", f, repo_type="dataset")
    if f.endswith(".tar"):
        with tarfile.open(p) as tar:
            for mem in tar:
                if mem.name.endswith((".flac", ".wav", ".mp3")) and m < want:
                    put(tar.extractfile(mem).read(), mem.name)
    else:
        pf = pq.ParquetFile(p)
        col = next((c for c in pf.schema_arrow.names if "audio" in c.lower() or c == "flac"), None)
        for batch in pf.iter_batches(columns=[col], batch_size=64):
            for i, a in enumerate(batch.to_pydict()[col]):
                if m >= want:
                    break
                if isinstance(a, dict):
                    put(a.get("bytes"), a.get("path") or f"as{m}.wav")
                elif isinstance(a, (bytes, bytearray)):
                    put(a, f"as{m}.wav")
    print(f, "→", m)
print("background:", m)
