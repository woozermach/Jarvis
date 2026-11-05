# -*- coding: utf-8 -*-
"""Конфиг обучения openWakeWord для «Hey Oswin» на основе examples/custom_model.yml."""
import sys
import yaml

src, dst, work = sys.argv[1], sys.argv[2], sys.argv[3]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 15000
steps = int(sys.argv[5]) if len(sys.argv) > 5 else 30000
shards = int(sys.argv[6]) if len(sys.argv) > 6 else 1   # на сколько машин делится генерация (n — уже доля одной)
c = yaml.safe_load(open(src))
c.update({
    "model_name": "hey_oswin",
    # «Hey Oswin» и просто «Oswin» (так зовут по-русски/по-польски: «Освин, …»)
    "target_phrase": ["hey oswin", "oswin"],
    # похожие слова, на которые модель НЕ должна срабатывать (кроме автоматически подобранных по фонемам)
    "custom_negative_phrases": ["austin", "hey austin", "boston", "houston", "osborne", "oswald", "awesome",
                                "own win", "so win", "always win", "hey siri", "hey google", "hey jarvis",
                                "hey alexa", "o's win", "hey jasmine", "us win", "oz", "wins"],
    "n_samples": n,
    "n_samples_val": max(20, max(min(1000, n * shards), n * shards // 8) // shards),
    "tts_batch_size": 50,
    "augmentation_batch_size": 16,
    "augmentation_rounds": 2,
    "piper_sample_generator_path": f"{work}/piper-sample-generator",
    "output_dir": f"{work}/model",
    "rir_paths": [f"{work}/data/mit_rirs"],
    "background_paths": [f"{work}/data/background"],
    "background_paths_duplication_rate": [1],
    "false_positive_validation_data_path": f"{work}/validation_set_features.npy",
    "feature_data_files": {"ACAV100M_sample": f"{work}/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"},
    "batch_n_per_class": {"ACAV100M_sample": 1024, "adversarial_negative": 70, "positive": 70},
    "steps": steps,
    "target_false_positives_per_hour": 0.2,
})
yaml.safe_dump(c, open(dst, "w"), allow_unicode=True)
print(yaml.safe_dump(c, allow_unicode=True))
