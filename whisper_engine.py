# whisper_engine.py

import whisper
import torch
import os
import tempfile
from moviepy import VideoFileClip
import yt_dlp

_YT_EXTRACTOR_ARGS = {'youtube': {'player_client': ['ios', 'mweb']}}


class WhisperEngine:
    """Whisper 本地模型（OpenAI），同時負責 YouTube 下載與影片音訊擷取"""

    MODELS = ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "turbo"]

    def __init__(self):
        self.model = None
        self.model_size = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Whisper 引擎將在以下裝置上運行: {self.device.upper()}")

    def load_model(self, model_size="turbo"):
        if self.model is not None and self.model_size == model_size:
            print(f"Whisper 模型 '{model_size}' 已經載入。")
            return
        print(f"正在載入 Whisper 模型 '{model_size}'... (首次使用需下載)")
        self.model_size = model_size
        self.model = whisper.load_model(self.model_size, device=self.device)
        print("Whisper 模型載入成功。")

    def transcribe(self, audio_path: str, prompt: str = "") -> dict:
        if self.model is None:
            raise RuntimeError("模型尚未載入。請先呼叫 load_model()。")
        print(f"[Whisper] 開始轉錄: {os.path.basename(audio_path)}")
        result = self.model.transcribe(
            audio_path,
            initial_prompt=prompt,
            fp16=torch.cuda.is_available(),
            verbose=True,
        )
        print("[Whisper] 轉錄完成。")
        return result  # {'text': str, 'segments': [...]}

    def process_input(self, input_source: str, input_type: str, prompt: str = "",
                      asr_engine=None, **kwargs):
        """
        預處理輸入（YT 下載、影片音訊擷取），然後呼叫 asr_engine.transcribe()。
        asr_engine 預設為 self（Whisper）。
        """
        if asr_engine is None:
            asr_engine = self

        stop_flag_check = kwargs.get('stop_flag_check', lambda: False)
        progress_hook = kwargs.get('progress_hook', lambda d: None)

        if stop_flag_check():
            return None

        if input_type in ['audio', 'video']:
            if not os.path.exists(input_source):
                raise FileNotFoundError(f"找不到檔案: {input_source}")

            if input_type == 'audio':
                if stop_flag_check():
                    return None
                return asr_engine.transcribe(input_source, prompt)

            elif input_type == 'video':
                print(f"正在從影片 '{os.path.basename(input_source)}' 中提取音訊...")
                audio_path = None
                try:
                    with VideoFileClip(input_source) as video:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                            video.audio.write_audiofile(tmp.name, codec='libmp3lame')
                            audio_path = tmp.name
                    print("音訊提取完成。")
                    if stop_flag_check():
                        return None
                    return asr_engine.transcribe(audio_path, prompt)
                finally:
                    if audio_path and os.path.exists(audio_path):
                        os.remove(audio_path)

        elif input_type == 'youtube':
            download_video = kwargs.get('download_video', False)
            output_dir = kwargs.get('output_dir', tempfile.gettempdir())

            print(f"處理 YouTube 連結: {input_source}")
            audio_path_for_asr = None
            try:
                if download_video:
                    print("下載策略：下載完整影片...")
                    if not os.path.isdir(output_dir):
                        raise FileNotFoundError(f"指定的輸出資料夾不存在: {output_dir}")
                    ydl_opts = {
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                        'progress_hooks': [progress_hook],
                        'extractor_args': _YT_EXTRACTOR_ARGS,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        if stop_flag_check():
                            return None
                        info = ydl.extract_info(input_source, download=True)
                        video_path = ydl.prepare_filename(info)
                    print(f"正在從已下載的影片提取音訊...")
                    with VideoFileClip(video_path) as video_clip:
                        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                            video_clip.audio.write_audiofile(tmp.name, codec='libmp3lame')
                            audio_path_for_asr = tmp.name
                    print("音訊提取完成。")

                else:
                    print("下載策略：僅下載音訊...")
                    temp_template = os.path.join(tempfile.gettempdir(), '%(id)s.%(ext)s')
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': temp_template,
                        'progress_hooks': [progress_hook],
                        'extractor_args': _YT_EXTRACTOR_ARGS,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }],
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        if stop_flag_check():
                            return None
                        info = ydl.extract_info(input_source, download=True)
                        base, _ = os.path.splitext(ydl.prepare_filename(info))
                        audio_path_for_asr = base + '.mp3'

                if stop_flag_check():
                    return None
                if not audio_path_for_asr or not os.path.exists(audio_path_for_asr):
                    raise RuntimeError("無法獲取用於轉錄的音訊檔案。")
                return asr_engine.transcribe(audio_path_for_asr, prompt)

            finally:
                if not download_video and audio_path_for_asr and os.path.exists(audio_path_for_asr):
                    print(f"清理暫存音訊檔: {audio_path_for_asr}")
                    os.remove(audio_path_for_asr)

        else:
            raise ValueError(f"不支援的輸入類型: {input_type}")

    def download_youtube(self, url: str, output_dir: str, download_format: str = 'video',
                         progress_hook=None, stop_flag_check=None):
        if stop_flag_check is None:
            stop_flag_check = lambda: False
        if progress_hook is None:
            progress_hook = lambda d: None

        if not os.path.isdir(output_dir):
            raise FileNotFoundError(f"指定的輸出資料夾不存在: {output_dir}")

        if download_format == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'extractor_args': _YT_EXTRACTOR_ARGS,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [progress_hook],
                'extractor_args': _YT_EXTRACTOR_ARGS,
            }

        print(f"開始下載: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if stop_flag_check():
                print("下載已取消。")
                return
            ydl.download([url])
        print("下載完成。")


class FunASREngine:
    """FunASR Paraformer（阿里達摩院），中文/台語辨識精度極高"""

    MODELS = ["paraformer-zh", "paraformer-en"]

    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name="paraformer-zh"):
        if self.model is not None and self.model_name == model_name:
            print(f"FunASR 模型 '{model_name}' 已載入。")
            return
        try:
            from funasr import AutoModel
        except ImportError:
            raise ImportError("請先安裝 FunASR：pip install funasr modelscope")

        print(f"正在載入 FunASR 模型 '{model_name}'... (首次使用需自動下載)")
        self.model = AutoModel(
            model=model_name,
            trust_remote_code=True,
            disable_update=True,
        )
        self.model_name = model_name
        print("FunASR 模型載入成功。")

    def transcribe(self, audio_path: str, prompt: str = "") -> dict:
        if self.model is None:
            raise RuntimeError("FunASR 模型尚未載入。")
        print(f"[FunASR] 開始辨識: {os.path.basename(audio_path)}")
        result = self.model.generate(
            input=audio_path,
            batch_size_s=300,
            sentence_timestamp=True,
        )
        print("[FunASR] 辨識完成。")
        return self._to_whisper_format(result)

    def _to_whisper_format(self, result) -> dict:
        raw = result[0]
        full_text = raw.get('text', '')
        sentences = raw.get('sentence_info', [])
        char_ts = raw.get('timestamp', [])  # [[start_ms, end_ms], ...] 字元級

        segments = []

        if sentences:
            for s in sentences:
                seg_text = s.get('text', '').strip()
                if seg_text:
                    segments.append({
                        'start': s.get('start', 0) / 1000.0,
                        'end':   s.get('end',   0) / 1000.0,
                        'text':  seg_text,
                    })

        if not segments and char_ts and full_text:
            segments = self._segments_from_char_ts(full_text, char_ts)

        if not segments:
            segments = [{'start': 0.0, 'end': 0.0, 'text': full_text}]

        return {'text': full_text, 'segments': segments}

    def _segments_from_char_ts(self, text, char_ts, chunk=25):
        """字元級時間戳 → 按標點或固定長度分段"""
        PUNCT = set('，。、？！…\n,.?!')
        segments, buf, seg_start = [], [], None
        for i, char in enumerate(text):
            if i >= len(char_ts):
                break
            ms_s, ms_e = char_ts[i][0], char_ts[i][1]
            if seg_start is None:
                seg_start = ms_s
            buf.append(char)
            if char in PUNCT or len(buf) >= chunk:
                t = ''.join(buf).strip()
                if t:
                    segments.append({'start': seg_start / 1000.0,
                                     'end': ms_e / 1000.0, 'text': t})
                buf, seg_start = [], None
        if buf and seg_start is not None:
            last_e = char_ts[min(len(text) - 1, len(char_ts) - 1)][1]
            t = ''.join(buf).strip()
            if t:
                segments.append({'start': seg_start / 1000.0,
                                 'end': last_e / 1000.0, 'text': t})
        return segments


class SenseVoiceEngine:
    """SenseVoice Small（阿里），多語言、速度快，支援情緒偵測"""

    MODELS = ["SenseVoiceSmall"]

    def __init__(self):
        self.model = None
        self.model_name = None

    def load_model(self, model_name="SenseVoiceSmall"):
        if self.model is not None and self.model_name == model_name:
            print(f"SenseVoice 模型 '{model_name}' 已載入。")
            return
        try:
            from funasr import AutoModel
        except ImportError:
            raise ImportError("請先安裝 FunASR：pip install funasr modelscope")

        print(f"正在載入 SenseVoice 模型 '{model_name}'... (首次使用需自動下載)")
        model_id = f"iic/{model_name}"
        self.model = AutoModel(
            model=model_id,
            trust_remote_code=True,
            disable_update=True,
        )
        self.model_name = model_name
        print("SenseVoice 模型載入成功。")

    def transcribe(self, audio_path: str, prompt: str = "") -> dict:
        if self.model is None:
            raise RuntimeError("SenseVoice 模型尚未載入。")
        print(f"[SenseVoice] 開始辨識: {os.path.basename(audio_path)}")
        result = self.model.generate(
            input=audio_path,
            language="auto",
            use_itn=True,
            batch_size_s=60,
            sentence_timestamp=True,
        )
        print("[SenseVoice] 辨識完成。")
        return self._to_whisper_format(result)

    def _to_whisper_format(self, result) -> dict:
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            clean = rich_transcription_postprocess
        except ImportError:
            import re
            def clean(t):
                return re.sub(r'<\|[^|]+\|>', '', t).strip()

        raw = result[0]
        full_text = clean(raw.get('text', ''))
        sentences = raw.get('sentence_info', [])
        char_ts = raw.get('timestamp', [])

        segments = []

        if sentences:
            for s in sentences:
                seg_text = clean(s.get('text', '')).strip()
                if seg_text:
                    segments.append({
                        'start': s.get('start', 0) / 1000.0,
                        'end':   s.get('end',   0) / 1000.0,
                        'text':  seg_text,
                    })

        if not segments and char_ts and full_text:
            segments = self._segments_from_char_ts(full_text, char_ts, clean)

        if not segments:
            segments = [{'start': 0.0, 'end': 0.0, 'text': full_text}]

        return {'text': full_text, 'segments': segments}

    def _segments_from_char_ts(self, text, char_ts, clean_fn=None, chunk=25):
        if clean_fn is None:
            clean_fn = lambda t: t
        PUNCT = set('，。、？！…\n,.?!')
        segments, buf, seg_start = [], [], None
        for i, char in enumerate(text):
            if i >= len(char_ts):
                break
            ms_s, ms_e = char_ts[i][0], char_ts[i][1]
            if seg_start is None:
                seg_start = ms_s
            buf.append(char)
            if char in PUNCT or len(buf) >= chunk:
                t = clean_fn(''.join(buf)).strip()
                if t:
                    segments.append({'start': seg_start / 1000.0,
                                     'end': ms_e / 1000.0, 'text': t})
                buf, seg_start = [], None
        if buf and seg_start is not None:
            last_e = char_ts[min(len(text) - 1, len(char_ts) - 1)][1]
            t = clean_fn(''.join(buf)).strip()
            if t:
                segments.append({'start': seg_start / 1000.0,
                                 'end': last_e / 1000.0, 'text': t})
        return segments
