# main_app.py

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import time
import sys
import io
from whisper_engine import WhisperEngine, FunASREngine, SenseVoiceEngine
import srt_utils
import run_logger

_ENGINE_MODELS = {
    "Whisper":    WhisperEngine.MODELS,
    "FunASR":     FunASREngine.MODELS,
    "SenseVoice": SenseVoiceEngine.MODELS,
}
_ENGINE_DEFAULT_MODEL = {
    "Whisper":    "turbo",
    "FunASR":     "paraformer-zh",
    "SenseVoice": "SenseVoiceSmall",
}
_ENGINE_HINTS = {
    "Whisper":    "OpenAI Whisper，多語言，本地運行",
    "FunASR":     "阿里達摩院 Paraformer，中文/台語精度極高，本地運行",
    "SenseVoice": "阿里 SenseVoice，多語言極速，支援情緒偵測，本地運行",
}

try:
    from srt_processor import fix_and_process_srt
except ImportError:
    def fix_and_process_srt(content):
        print("警告: srt_processor.py 未找到，跳過校正。")
        return content


class StdoutRedirector(io.TextIOBase):
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.text_widget.update_idletasks()

    def write(self, string):
        self.text_widget.after(0, self.insert_text, string)
        return len(string)

    def insert_text(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)

    def flush(self):
        pass


class CollapsibleSection:
    """可展開 / 收合的區塊元件"""

    def __init__(self, parent, title, expanded=True):
        self._title = title
        self.expanded = expanded

        self.outer = ttk.Frame(parent)
        self.outer.pack(fill=tk.X, padx=6, pady=3)

        self.toggle_btn = ttk.Button(
            self.outer,
            text=self._label(expanded),
            command=self._toggle,
            style="Section.TButton",
        )
        self.toggle_btn.pack(fill=tk.X)

        self.content = ttk.Frame(self.outer, padding=(12, 6))
        if expanded:
            self.content.pack(fill=tk.X)

    def _label(self, expanded):
        arrow = "▼" if expanded else "▶"
        return f"  {arrow}  {self._title}"

    def _toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.content.pack(fill=tk.X)
        else:
            self.content.pack_forget()
        self.toggle_btn.config(text=self._label(self.expanded))


class WhisperApp:
    def __init__(self, master):
        self.master = master
        master.title("多功能 Whisper 轉錄工具")
        master.geometry("860x780")
        master.minsize(700, 520)

        self.engine = WhisperEngine()
        self.asr_engines = {
            "Whisper":    self.engine,
            "FunASR":     FunASREngine(),
            "SenseVoice": SenseVoiceEngine(),
        }
        self.transcription_result = None
        self.stop_thread_flag = False
        self.stop_download_flag = False
        self.input_source = None

        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 10, "bold"))
        style.configure("Section.TButton", font=("Arial", 10, "bold"),
                        anchor="w", padding=5, relief="groove")

        main_frame = ttk.Frame(master, padding="6")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ══════════════════════════════════════════════════
        #  區塊一：語音辨識
        # ══════════════════════════════════════════════════
        asr_sec = CollapsibleSection(main_frame, "語音辨識", expanded=True)
        asr = asr_sec.content
        asr.columnconfigure(1, weight=1)

        # 辨識引擎
        ttk.Label(asr, text="辨識引擎:").grid(row=0, column=0, padx=5, pady=3, sticky="w")
        self.engine_var = tk.StringVar(value="Whisper")
        self.engine_var.trace_add("write", self.on_engine_change)
        ttk.Combobox(asr, textvariable=self.engine_var,
                     values=list(_ENGINE_MODELS.keys()),
                     state="readonly", width=18
                     ).grid(row=0, column=1, padx=5, pady=3, sticky="w")
        self.engine_hint = ttk.Label(asr, text=_ENGINE_HINTS["Whisper"], foreground="gray")
        self.engine_hint.grid(row=0, column=2, columnspan=2, padx=5, sticky="w")

        # 模型選擇
        ttk.Label(asr, text="選擇模型:").grid(row=1, column=0, padx=5, pady=3, sticky="w")
        self.model_var = tk.StringVar(value="turbo")
        self.model_menu = ttk.Combobox(asr, textvariable=self.model_var,
                                       values=WhisperEngine.MODELS,
                                       state="readonly", width=18)
        self.model_menu.grid(row=1, column=1, padx=5, pady=3, sticky="w")

        # 輸入類型
        ttk.Label(asr, text="輸入類型:").grid(row=2, column=0, padx=5, pady=3, sticky="w")
        self.input_type_var = tk.StringVar(value="檔案")
        self.input_type_var.trace_add("write", self.on_input_type_change)
        ttk.Radiobutton(asr, text="檔案 (音訊/影片)",
                        variable=self.input_type_var, value="檔案"
                        ).grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(asr, text="YouTube 連結",
                        variable=self.input_type_var, value="YouTube"
                        ).grid(row=2, column=2, sticky="w")

        # 動態輸入區（row=3）
        self.file_frame = ttk.Frame(asr)
        self.file_button = ttk.Button(self.file_frame, text="選擇檔案", command=self.select_file)
        self.file_button.pack(side=tk.LEFT, padx=(0, 8))
        self.file_label = ttk.Label(self.file_frame, text="尚未選擇檔案")
        self.file_label.pack(side=tk.LEFT)

        self.youtube_frame = ttk.Frame(asr)
        ttk.Label(self.youtube_frame, text="貼上連結:").pack(side=tk.LEFT, padx=(0, 6))
        self.youtube_entry = ttk.Entry(self.youtube_frame, width=52)
        self.youtube_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.download_video_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.youtube_frame, text="同時下載影片",
                        variable=self.download_video_var).pack(side=tk.LEFT)

        # 上下文提示（Whisper 專用）
        self.prompt_label = ttk.Label(asr, text="上下文/提示:")
        self.prompt_label.grid(row=4, column=0, padx=5, pady=3, sticky="nw")
        self.prompt_text = tk.Text(asr, height=3, wrap=tk.WORD)
        self.prompt_text.grid(row=4, column=1, columnspan=3, padx=5, pady=3, sticky="ew")

        # 輸出格式
        ttk.Label(asr, text="輸出格式:").grid(row=5, column=0, padx=5, pady=3, sticky="w")
        self.output_format_var = tk.StringVar(value="SRT")
        self.output_format_var.trace_add("write", self.on_output_format_change)
        ttk.Radiobutton(asr, text="純文字",
                        variable=self.output_format_var, value="純文字"
                        ).grid(row=5, column=1, sticky="w")
        ttk.Radiobutton(asr, text="SRT 字幕檔",
                        variable=self.output_format_var, value="SRT"
                        ).grid(row=5, column=2, sticky="w")

        # 輸出資料夾
        ttk.Label(asr, text="輸出資料夾:").grid(row=6, column=0, padx=5, pady=3, sticky="w")
        self.output_dir_var = tk.StringVar()
        ttk.Entry(asr, textvariable=self.output_dir_var
                  ).grid(row=6, column=1, columnspan=2, padx=5, sticky="ew")
        ttk.Button(asr, text="瀏覽...", command=self.browse_output_dir
                   ).grid(row=6, column=3, padx=5)

        # 輸出檔名
        ttk.Label(asr, text="輸出檔名:").grid(row=7, column=0, padx=5, pady=3, sticky="w")
        self.output_filename_var = tk.StringVar()
        ttk.Entry(asr, textvariable=self.output_filename_var
                  ).grid(row=7, column=1, columnspan=2, padx=5, sticky="ew")

        # 操作按鈕
        asr_btn = ttk.Frame(asr)
        asr_btn.grid(row=8, column=1, columnspan=3, pady=(8, 2), sticky="w")
        self.transcribe_button = ttk.Button(asr_btn, text="開始轉錄",
                                            command=self.start_transcription_thread,
                                            style="Accent.TButton")
        self.transcribe_button.pack(side=tk.LEFT, padx=(0, 8))
        self.autofix_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(asr_btn, text="自動校正 SRT",
                        variable=self.autofix_var).pack(side=tk.LEFT, padx=(0, 8))
        self.stop_button = ttk.Button(asr_btn, text="終止運算",
                                      command=self.stop_transcription, state="disabled")
        self.stop_button.pack(side=tk.LEFT)

        # ══════════════════════════════════════════════════
        #  區塊二：YouTube 下載（預設收合）
        # ══════════════════════════════════════════════════
        dl_sec = CollapsibleSection(main_frame, "YouTube 下載", expanded=False)
        dl = dl_sec.content
        dl.columnconfigure(1, weight=1)

        ttk.Label(dl, text="影片連結:").grid(row=0, column=0, padx=5, pady=3, sticky="w")
        self.dl_url_entry = ttk.Entry(dl)
        self.dl_url_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=3, sticky="ew")

        ttk.Label(dl, text="儲存位置:").grid(row=1, column=0, padx=5, pady=3, sticky="w")
        self.dl_dir_var = tk.StringVar()
        ttk.Entry(dl, textvariable=self.dl_dir_var
                  ).grid(row=1, column=1, columnspan=2, padx=5, sticky="ew")
        ttk.Button(dl, text="瀏覽...", command=self.browse_download_dir
                   ).grid(row=1, column=3, padx=5)

        ttk.Label(dl, text="下載格式:").grid(row=2, column=0, padx=5, pady=3, sticky="w")
        self.dl_format_var = tk.StringVar(value="video")
        ttk.Radiobutton(dl, text="影片 (MP4)",
                        variable=self.dl_format_var, value="video").grid(row=2, column=1, sticky="w")
        ttk.Radiobutton(dl, text="僅音訊 (MP3)",
                        variable=self.dl_format_var, value="audio").grid(row=2, column=2, sticky="w")

        dl_btn = ttk.Frame(dl)
        dl_btn.grid(row=3, column=1, columnspan=2, pady=(8, 2), sticky="w")
        self.dl_start_btn = ttk.Button(dl_btn, text="開始下載",
                                       command=self.start_download_thread,
                                       style="Accent.TButton")
        self.dl_start_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.dl_stop_btn = ttk.Button(dl_btn, text="停止下載",
                                      command=self.stop_download, state="disabled")
        self.dl_stop_btn.pack(side=tk.LEFT)

        # ══════════════════════════════════════════════════
        #  執行過程與結果預覽
        # ══════════════════════════════════════════════════
        result_frame = ttk.Frame(main_frame, padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 0))
        ttk.Label(result_frame, text="執行過程與結果預覽:").pack(anchor="w")
        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, height=10)
        self.result_text.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        btn_row = ttk.Frame(result_frame)
        btn_row.pack(fill=tk.X, pady=6)
        ttk.Button(btn_row, text="預覽結果", command=self.preview_result).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="查看紀錄", command=self.open_run_log).pack(side=tk.LEFT, padx=(8, 0))
        self.save_button = ttk.Button(btn_row, text="儲存至指定路徑", command=self.save_result)
        self.save_button.pack(side=tk.RIGHT)

        self.on_input_type_change()

    # ── 輸入類型切換 ──────────────────────────────────────────────

    def on_engine_change(self, *args):
        engine = self.engine_var.get()
        models = _ENGINE_MODELS.get(engine, [])
        self.model_menu.config(values=models)
        self.model_var.set(_ENGINE_DEFAULT_MODEL.get(engine, models[0] if models else ""))
        self.engine_hint.config(text=_ENGINE_HINTS.get(engine, ""))
        if engine == "Whisper":
            self.prompt_label.grid()
            self.prompt_text.grid()
        else:
            self.prompt_label.grid_remove()
            self.prompt_text.grid_remove()

    def on_input_type_change(self, *args):
        if self.input_type_var.get() == "檔案":
            self.youtube_frame.grid_remove()
            self.file_frame.grid(row=3, column=0, columnspan=4, padx=5, pady=3, sticky="ew")
        else:
            self.file_frame.grid_remove()
            self.youtube_frame.grid(row=3, column=0, columnspan=4, padx=5, pady=3, sticky="ew")
        self.update_suggested_filename()

    def on_output_format_change(self, *args):
        self.update_suggested_filename()

    # ── 瀏覽目錄 ─────────────────────────────────────────────────

    def browse_output_dir(self):
        path = filedialog.askdirectory(title="選擇輸出資料夾")
        if path:
            self.output_dir_var.set(path)

    def browse_download_dir(self):
        path = filedialog.askdirectory(title="選擇下載儲存位置")
        if path:
            self.dl_dir_var.set(path)

    # ── 選擇本地檔案 ──────────────────────────────────────────────

    def select_file(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("媒體檔案", "*.mp3 *.wav *.m4a *.mp4 *.mov *.mkv"),
                       ("所有檔案", "*.*")]
        )
        if filepath:
            self.input_source = filepath
            self.file_label.config(text=os.path.basename(filepath))
            self.output_dir_var.set(os.path.dirname(filepath))
            self.update_suggested_filename()

    def update_suggested_filename(self):
        if self.input_type_var.get() == "檔案" and self.input_source:
            base, _ = os.path.splitext(os.path.basename(self.input_source))
            suffix = ".srt" if self.output_format_var.get() == "SRT" else ".txt"
            self.output_filename_var.set(f"{base}_transcript{suffix}")
        elif self.input_type_var.get() == "YouTube":
            suffix = ".srt" if self.output_format_var.get() == "SRT" else ".txt"
            self.output_filename_var.set(f"youtube_transcript{suffix}")

    # ── YouTube 獨立下載 ──────────────────────────────────────────

    def stop_download(self):
        self.stop_download_flag = True
        self.result_text.insert(tk.END, "\n--- 收到停止下載請求... ---\n")

    def start_download_thread(self):
        url = self.dl_url_entry.get().strip()
        if not url or not url.startswith(('http://', 'https://')):
            messagebox.showwarning("輸入錯誤", "請輸入一個有效的影片連結。")
            return
        dl_dir = self.dl_dir_var.get()
        if not dl_dir or not os.path.isdir(dl_dir):
            messagebox.showwarning("路徑錯誤", "請選擇一個有效的儲存位置。")
            return
        self.stop_download_flag = False
        self.dl_start_btn.config(state="disabled")
        self.dl_stop_btn.config(state="normal")
        self.update_result("")
        threading.Thread(target=self.run_download, daemon=True).start()

    def run_download(self):
        url = self.dl_url_entry.get().strip()
        dl_dir = self.dl_dir_var.get()
        dl_format = self.dl_format_var.get()
        start_time = time.time()
        try:
            self.master.after(0, lambda: self.result_text.insert(tk.END, f"開始下載: {url}\n"))
            self.engine.download_youtube(
                url, dl_dir, dl_format,
                progress_hook=self.yt_dlp_progress_hook,
                stop_flag_check=lambda: self.stop_download_flag,
            )
            if not self.stop_download_flag:
                elapsed = time.time() - start_time
                msg = f"\n--- 下載完成！總耗時: {elapsed:.2f} 秒 ---\n"
                self.master.after(0, lambda: self.result_text.insert(tk.END, msg))
            else:
                self.master.after(0, lambda: self.result_text.insert(tk.END, "\n--- 下載已停止 ---\n"))
        except Exception as e:
            import traceback
            err = f"下載失敗:\n{e}\n\n{traceback.format_exc()}"
            self.master.after(0, lambda: self.result_text.insert(tk.END, err))
        finally:
            self.master.after(0, lambda: self.dl_start_btn.config(state="normal"))
            self.master.after(0, lambda: self.dl_stop_btn.config(state="disabled"))

    # ── 語音轉錄 ─────────────────────────────────────────────────

    def stop_transcription(self):
        self.stop_thread_flag = True
        self.result_text.insert(tk.END, "\n\n--- 收到終止請求，正在嘗試停止任務... ---\n")

    def start_transcription_thread(self):
        if self.input_type_var.get() == "檔案":
            if not self.input_source:
                messagebox.showwarning("輸入錯誤", "請先選擇一個有效的檔案。")
                return
            _, ext = os.path.splitext(self.input_source)
            self.internal_input_type = (
                'video' if ext.lower() not in ['.mp3', '.wav', '.m4a', '.ogg'] else 'audio'
            )
        else:
            self.input_source = self.youtube_entry.get().strip()
            if not self.input_source or not self.input_source.startswith(('http://', 'https://')):
                messagebox.showwarning("輸入錯誤", "請輸入一個有效的 YouTube 連結。")
                return
            self.internal_input_type = 'youtube'

        self.stop_thread_flag = False
        self.transcribe_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.transcription_result = None
        self.update_result("")
        threading.Thread(target=self.run_transcription, daemon=True).start()

    def yt_dlp_progress_hook(self, d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total_bytes > 0:
                percent_str = ''.join(
                    c for c in d.get('_percent_str', '0.0%') if c.isdigit() or c in '%.'
                )
                speed_str = d.get('_speed_str', 'N/A').strip()
                eta_str = d.get('_eta_str', 'N/A').strip()
                line = f"[下載] {percent_str}  {total_bytes/1024/1024:.1f}MB  速度:{speed_str}  剩餘:{eta_str}\n"
                self.master.after(0, lambda: self.result_text.insert(tk.END, line))
                self.master.after(0, lambda: self.result_text.see(tk.END))
        elif d['status'] == 'finished':
            fn = os.path.basename(d.get('filename', ''))
            self.master.after(0, lambda: self.result_text.insert(tk.END, f"\n『{fn}』下載完成。\n"))
        elif d['status'] == 'error':
            self.master.after(0, lambda: self.result_text.insert(tk.END, "\n[錯誤] 下載過程中發生錯誤。\n"))

    def run_transcription(self):
        original_stdout = sys.stdout
        start_time = time.time()
        engine_name = self.engine_var.get()
        model_size = self.model_var.get()
        asr_engine = self.asr_engines[engine_name]
        extra_args = {
            'stop_flag_check': lambda: self.stop_thread_flag,
            'download_video': self.download_video_var.get(),
            'output_dir': self.output_dir_var.get(),
            'progress_hook': self.yt_dlp_progress_hook,
            'asr_engine': asr_engine,
        }
        try:
            self.master.after(0, self.update_result,
                              f"引擎: {engine_name}  |  模型: {model_size}\n正在載入模型...\n")
            asr_engine.load_model(model_size)

            if self.stop_thread_flag:
                raise InterruptedError("任務在模型載入後被終止")

            prompt = self.prompt_text.get("1.0", tk.END).strip()
            self.master.after(0, lambda: self.result_text.insert(tk.END, "模型載入完畢，準備處理輸入源...\n"))

            if self.stop_thread_flag:
                raise InterruptedError("任務在處理輸入源前被終止")

            if engine_name == "Whisper":
                self.master.after(0, lambda: self.result_text.insert(
                    tk.END, "\n--- 開始轉錄，即時進度如下 ---\n"))
            else:
                self.master.after(0, lambda: self.result_text.insert(
                    tk.END, "\n--- 辨識中，請稍候... ---\n"))

            sys.stdout = StdoutRedirector(self.result_text)

            self.transcription_result = self.engine.process_input(
                self.input_source,
                self.internal_input_type,
                prompt,
                **extra_args,
            )

            if self.stop_thread_flag:
                raise InterruptedError("任務在轉錄過程中被終止")

        except InterruptedError as e:
            sys.stdout = original_stdout
            self.master.after(0, self.update_result, f"任務已終止：{e}")
        except Exception as e:
            sys.stdout = original_stdout
            import traceback
            err = f"轉錄過程中發生錯誤:\n{e}\n\n{traceback.format_exc()}"
            self.master.after(0, self.update_result, err)
        finally:
            sys.stdout = original_stdout
            if self.transcription_result and not self.stop_thread_flag:
                elapsed = time.time() - start_time
                msg = f"\n\n--- 任務完成！總耗時: {elapsed:.2f} 秒 ---\n"
                self.master.after(0, lambda: self.result_text.insert(tk.END, msg))
                self.master.after(0, self._show_preview)
                try:
                    run_logger.save(engine_name, model_size,
                                    self.input_source or "", elapsed,
                                    self.transcription_result)
                except Exception:
                    pass
            self.master.after(0, lambda: self.transcribe_button.config(state="normal"))
            self.master.after(0, lambda: self.stop_button.config(state="disabled"))

    # ── 預覽 / 輸出 / 儲存 ────────────────────────────────────────

    def preview_result(self):
        if not self.transcription_result:
            messagebox.showinfo("尚無結果", "請先執行轉錄，才能預覽結果。")
            return
        self.result_text.delete(1.0, tk.END)
        self._show_preview()

    def _show_preview(self):
        content = self.generate_output_content()
        if not content:
            return
        fmt = self.output_format_var.get()
        sep = f"\n{'─' * 50}\n▼ 預覽（{fmt}）\n{'─' * 50}\n"
        self.result_text.insert(tk.END, sep)
        self.result_text.insert(tk.END, content)
        self.result_text.see(tk.END)

    def update_result(self, text):
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)

    def generate_output_content(self):
        if not self.transcription_result:
            return ""
        if self.output_format_var.get() == "純文字":
            return self.transcription_result.get('text', "")
        elif self.output_format_var.get() == "SRT":
            segs = self.transcription_result.get('segments', [])
            refined = srt_utils.refine_srt_segments(segs, max_chars=20)
            return srt_utils.generate_srt_from_segments(refined)
        return ""

    def open_run_log(self):
        if not os.path.isfile(run_logger.LOG_PATH):
            messagebox.showinfo("尚無紀錄", "尚未有任何轉錄紀錄，執行一次轉錄後紀錄會自動建立。")
            return
        os.startfile(run_logger.LOG_PATH)

    def save_result(self):
        if not self.transcription_result:
            messagebox.showwarning("內容為空", "沒有可以儲存的內容。請先執行轉錄。")
            return
        output_dir = self.output_dir_var.get()
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("路徑錯誤", "請指定一個有效的輸出資料夾。")
            return
        output_filename = self.output_filename_var.get()
        if not output_filename:
            messagebox.showwarning("檔名錯誤", "請輸入輸出檔名。")
            return

        content = self.generate_output_content()
        if not content:
            messagebox.showwarning("內容為空", "無法生成有效的輸出內容。")
            return

        final_content = content
        correction_applied = False
        if self.output_format_var.get() == "SRT" and self.autofix_var.get():
            try:
                corrected = fix_and_process_srt(content)
                if corrected and corrected != content:
                    final_content = corrected
                    correction_applied = True
            except Exception as e:
                messagebox.showwarning("校正失敗",
                                       f"SRT 校正發生錯誤，將儲存未校正版本。\n{e}")

        full_path = os.path.join(output_dir, output_filename)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            label = "校正並儲存" if correction_applied else "儲存"
            messagebox.showinfo("儲存成功", f"檔案已成功{label}至:\n{full_path}")
        except Exception as e:
            messagebox.showerror("儲存失敗", f"儲存檔案時發生錯誤:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = WhisperApp(root)
    root.mainloop()
