# 多功能 Whisper 轉錄工具 (附 YouTube 下載功能)

這是一個基於 Python 與 OpenAI Whisper 的桌面應用程式，具備圖形介面 (GUI)，方便使用者將本機音訊/影片或 YouTube 連結轉錄為文字或 SRT 字幕檔。

## 功能特點

- **多模型支援**: 可選擇 `tiny`, `base`, `small`, `medium`, `large` 不同等級的 Whisper 模型。
- **多元輸入**: 支援本機媒體檔案 (mp3, wav, mp4, mov 等) 與 YouTube 連結。
- **自動下載**: 整合 `yt-dlp`，可直接輸入網址進行下載轉錄。
- **即時進度**: 具備 Console 輸出重定向，可在介面即時查看轉錄與下載進度。
- **字幕優化**: 提供自動斷句與移除標點符號功能。

## 安裝說明

### 1. 環境需求
- Python 3.8+
- **FFmpeg**: 系統必須安裝 FFmpeg 才能處理媒體轉換（專案內建 `imageio-ffmpeg` 會協助管理，但某些環境仍建議手動安裝）。
- **GPU 支援 (選配)**: 若要加速運算，請安裝支援 CUDA 的 PyTorch 版本。

### 2. 安裝依賴庫
```bash
pip install -r requirements.txt
```

## 使用方式

執行 `main_app.py` 啟動圖形介面：
```bash
python main_app.py
```

1. 選擇 Whisper 模型等級。
2. 選擇輸入類型（檔案或 YouTube 連結）。
3. 設定輸出格式（純文字或 SRT）。
4. 設定輸出目錄與檔名。
5. 按下 **「開始轉錄」**。

## 專案架構

- `main_app.py`: Tkinter GUI 主要邏輯。
- `whisper_engine.py`: 封裝 Whisper 與下載邏輯。
- `srt_utils.py`: SRT 時間處理與自動斷句。
- `srt_processor.py`: SRT 格式與文字內容精加工。

## 授權
[請在此填寫授權資訊，如 MIT]
