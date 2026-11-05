#!/usr/bin/env bash
# Зависимости для обучения openWakeWord (версии как в официальном примере automatic_model_training.ipynb)
set -euo pipefail
W=${W:-/mnt/ww}
cd "$W"
sudo apt-get update -q >/dev/null && sudo apt-get install -y -q espeak-ng libsndfile1 >/dev/null
# форк с generate_samples.py в корне — его ждёт openwakeword/train.py
git clone -q https://github.com/dscripka/piper-sample-generator
wget -q -O piper-sample-generator/models/en-us-libritts-high.pt \
  https://github.com/rhasspy/piper-sample-generator/releases/download/v1.0.0/en-us-libritts-high.pt
git clone -q https://github.com/dscripka/openWakeWord oww
pip install -q --upgrade pip
pip install -q torch==2.1.2 torchaudio==2.1.2 --index-url https://download.pytorch.org/whl/cpu
pip install -q "numpy<2" piper-phonemize espeak-phonemizer webrtcvad mutagen==1.47.0 torchinfo==1.8.0 torchmetrics==1.2.0 \
  speechbrain==0.5.14 audiomentations==0.33.0 torch-audiomentations==0.11.0 acoustics==0.2.6 \
  pronouncing==0.2.0 deep-phonemizer==0.0.19 onnx onnxruntime soundfile pyarrow huggingface_hub pyyaml tqdm scipy
pip install -q -e ./oww
mkdir -p oww/openwakeword/resources/models
for f in embedding_model.onnx melspectrogram.onnx; do
  wget -q -O "oww/openwakeword/resources/models/$f" "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/$f"
done
python -c "import openwakeword, torch, speechbrain, pronouncing; print('deps ok', torch.__version__)"
