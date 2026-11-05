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

# 2) Background: two AudioSet balanced-train shards (speech, music, noise)
bg = out / "background"
bg.mkdir(parents=True, exist_ok=True)
m = 0
for shard in ("bal_train09.tar", "bal_train03.tar"):
    p = hf_hub_download("agkphysics/AudioSet", f"data/{shard}", repo_type="dataset")
    with tarfile.open(p) as tar:
        for mem in tar:
            if not mem.name.endswith(".flac"):
                continue
            try:
                x, sr = sf.read(io.BytesIO(tar.extractfile(mem).read()), dtype="float32")
                sf.write(bg / (Path(mem.name).stem + ".wav"), to16k(x, sr), 16000)
                m += 1
            except Exception as e:
                print("skip", mem.name, e)
print("background:", m)
