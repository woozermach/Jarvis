# -*- coding: utf-8 -*-
"""Обёртка над openwakeword/train.py:
- своё случайное зерно для каждой параллельной машины (SHARD), иначе Piper повторяет одни и те же голоса;
- произношение «Oswin» в словаре CMU (DeepPhonemizer, которым openWakeWord угадывает новые слова, больше не скачивается).
Запуск: python run_train.py <path/to/train.py> --training_config cfg.yml --generate_clips"""
import os
import random
import runpy
import sys

import numpy as np
import torch

shard = int(os.environ.get("SHARD", "0"))
random.seed(1000 + shard)
np.random.seed(1000 + shard)
torch.manual_seed(1000 + shard)

import pronouncing  # noqa: E402

pronouncing.init_cmu()
for word, phones in {"oswin": ["AA1 Z W IH0 N", "AA1 S W IH0 N"]}.items():
    for ph in phones:
        if ph not in pronouncing.lookup[word]:
            pronouncing.lookup[word].append(ph)
            pronouncing.pronunciations.append((word, ph))

train_py = sys.argv[1]
sys.argv = [train_py] + sys.argv[2:]
try:
    runpy.run_path(train_py, run_name="__main__")
except ModuleNotFoundError as e:
    # train.py всегда пытается сделать .tflite (ошибка в argparse: default="False" — это истина); нам нужен только .onnx
    if e.name in ("onnx_tf", "tensorflow") and any(a == "--train_model" for a in sys.argv):
        print("tflite skipped:", e)
    else:
        raise
