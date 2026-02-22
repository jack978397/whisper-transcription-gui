# whisper_engine.py (已修改版)

import whisper
import torch
import os
import tempfile
from moviepy import VideoFileClip # 用於從本地影片提取音訊
import yt_dlp

class WhisperEngine:
    def __init__(self):
        self.model = None
        self.model_size = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Whisper 引擎將在以下裝置上運行: {self.device.upper()}")

    def load_model(self, model_size="base"):
        if self.model is not None and self.model_size == model_size:
            print(f"模型 '{model_size}' 已經載入。")
            return
        
        print(f"正在載入 Whisper 模型 '{model_size}'... (第一次可能需要一些時間)")
        self.model_size = model_size
        self.model = whisper.load_model(self.model_size, device=self.device)
        print("模型載入成功。")

    def _transcribe_audio(self, audio_path: str, prompt: str = ""):
        if self.model is None:
            raise RuntimeError("模型尚未載入。請先呼叫 load_model()。")

        print(f"開始轉錄音訊: {os.path.basename(audio_path)}")
        
        # verbose=True 會透過 print 輸出進度，這會被 main_app 的 StdoutRedirector 捕捉
        result = self.model.transcribe(
            audio_path, 
            initial_prompt=prompt,
            fp16=torch.cuda.is_available(),
            verbose=True 
        )
        print("轉錄完成。")
        return result

    def process_input(self, input_source: str, input_type: str, prompt: str = "", **kwargs):
        stop_flag_check = kwargs.get('stop_flag_check', lambda: False)
        # 從 kwargs 獲取 progress_hook，如果沒有就給一個什麼都不做的假函式
        progress_hook = kwargs.get('progress_hook', lambda d: None)

        if stop_flag_check(): return None

        if input_type in ['audio', 'video']:
            if not os.path.exists(input_source):
                raise FileNotFoundError(f"找不到檔案: {input_source}")
            
            if input_type == 'audio':
                if stop_flag_check(): return None
                return self._transcribe_audio(input_source, prompt)
            
            elif input_type == 'video':
                print(f"正在從影片 '{os.path.basename(input_source)}' 中提取音訊...")
                audio_path = None
                try:
                    with VideoFileClip(input_source) as video:
                        # 使用 .mp3 作為暫存檔，更通用
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_audio:
                            video.audio.write_audiofile(tmp_audio.name, codec='libmp3lame')
                            audio_path = tmp_audio.name
                    print("音訊提取完成。")
                    if stop_flag_check(): return None
                    result = self._transcribe_audio(audio_path, prompt)
                    return result
                finally:
                    if audio_path and os.path.exists(audio_path):
                        os.remove(audio_path)

        elif input_type == 'youtube':
            download_video = kwargs.get('download_video', False)
            output_dir = kwargs.get('output_dir', tempfile.gettempdir())

            print(f"處理 YouTube 連結: {input_source}")
            
            audio_path_for_transcription = None
            try:
                if download_video:
                    print("下載策略：下載完整影片...")
                    if not os.path.isdir(output_dir):
                        raise FileNotFoundError(f"指定的輸出資料夾不存在: {output_dir}")
                    
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                        # 將 progress_hook 連接上
                        'progress_hooks': [progress_hook],
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        if stop_flag_check(): return None
                        info = ydl.extract_info(input_source, download=True)
                        video_path = ydl.prepare_filename(info)
                    
                    print(f"正在從已下載的影片 '{os.path.basename(video_path)}' 中提取音訊...")
                    with VideoFileClip(video_path) as video_clip:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_audio:
                            video_clip.audio.write_audiofile(tmp_audio.name, codec='libmp3lame')
                            audio_path_for_transcription = tmp_audio.name
                    print("音訊提取完成。")

                else:
                    print("下載策略：僅下載音訊進行處理...")
                    temp_audio_template = os.path.join(tempfile.gettempdir(), '%(id)s.%(ext)s')
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': temp_audio_template,
                        # 將 progress_hook 連接上
                        'progress_hooks': [progress_hook],
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3', # 直接輸出 mp3
                            'preferredquality': '192',
                        }],
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        if stop_flag_check(): return None
                        info = ydl.extract_info(input_source, download=True)
                        base, _ = os.path.splitext(ydl.prepare_filename(info))
                        audio_path_for_transcription = base + '.mp3' # 最終檔案是 mp3

                if stop_flag_check(): return None
                
                if not audio_path_for_transcription or not os.path.exists(audio_path_for_transcription):
                    raise RuntimeError("無法獲取用於轉錄的音訊檔案。")
                
                result = self._transcribe_audio(audio_path_for_transcription, prompt)
                return result

            finally:
                if not download_video and audio_path_for_transcription and os.path.exists(audio_path_for_transcription):
                    print(f"清理暫存音訊檔: {audio_path_for_transcription}")
                    os.remove(audio_path_for_transcription)
            
        else:
            raise ValueError(f"不支援的輸入類型: {input_type}")