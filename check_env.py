# check_env.py 確認環境的文件是否適合運行 Whisper 引擎
import torch
import sys

print("--- 環境檢查報告 ---")
print(f"Python 版本: {sys.version}")
print(f"PyTorch 版本: {torch.__version__}")
print("-" * 20)

if torch.cuda.is_available():
    print("✅ 成功：偵測到可用的 CUDA 裝置！")
    print(f"CUDA 版本: {torch.version.cuda}")
    print(f"GPU 數量: {torch.cuda.device_count()}")
    print(f"目前使用的 GPU: {torch.cuda.get_device_name(0)}")
    print("\n您的 Whisper 應用程式將會使用 GPU 運行，速度會非常快。")
else:
    print("❌ 警告：未偵測到可用的 CUDA 裝置。")
    print("\n您的 Whisper 應用程式將會使用 CPU 運行。")
    print("這可能是因為：")
    print("1. 您的電腦沒有 NVIDIA 顯示卡。")
    print("2. 您沒有安裝支援 CUDA 的 PyTorch 版本。")
    print("3. NVIDIA 驅動程式或 CUDA Toolkit 有問題。")
    print("請參考 PyTorch 官網的指令重新安裝。")

print("\n--- 檢查完畢 ---")