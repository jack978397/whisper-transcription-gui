# run_logger.py

import csv
import os
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_log.csv")

_COLUMNS = [
    "timestamp",
    "engine",
    "model",
    "source",
    "audio_sec",
    "process_sec",
    "rtf",
    "segments",
    "chars",
]


def save(engine: str, model: str, source: str,
         process_sec: float, result: dict) -> None:
    """轉錄完成後呼叫，自動追加一筆紀錄到 run_log.csv"""

    # 從最後一個 segment 的 end 估算音訊長度
    segs = result.get("segments", [])
    audio_sec = segs[-1]["end"] if segs else 0.0
    rtf = round(process_sec / audio_sec, 3) if audio_sec > 0 else ""

    full_text = result.get("text", "")

    row = {
        "timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "engine":      engine,
        "model":       model,
        "source":      os.path.basename(source) if os.path.exists(source) else source[:80],
        "audio_sec":   round(audio_sec, 1),
        "process_sec": round(process_sec, 1),
        "rtf":         rtf,
        "segments":    len(segs),
        "chars":       len(full_text.replace(" ", "")),
    }

    file_exists = os.path.isfile(LOG_PATH)
    with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)
