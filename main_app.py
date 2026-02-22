# main_app.py GUI跟主要運作的程式 (已修改整合版)

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import time
import sys
import io
from whisper_engine import WhisperEngine
import srt_utils
# 假設您的 srt_corrector.py 中有一個主函式叫 fix_and_process_srt
# 如果沒有，請替換成您實際的函式名，或暫時註解掉
try:
    from srt_processor import fix_and_process_srt
except ImportError:
    # 如果 srt_processor.py 不存在或函式名不同，提供一個假函式以避免啟動錯誤
    def fix_and_process_srt(content):
        print("警告: srt_processor.py 或 fix_and_process_srt 函式未找到，跳過校正。")
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

class WhisperApp:
    def __init__(self, master):
        self.master = master
        master.title("多功能 Whisper 轉錄工具")
        master.geometry("850x750")

        self.engine = WhisperEngine()
        self.transcription_result = None
        self.stop_thread_flag = False

        # --- UI 元素 ---
        top_frame = ttk.Frame(master, padding="10")
        top_frame.pack(fill=tk.X)
        bottom_frame = ttk.Frame(master, padding="10")
        bottom_frame.pack(fill=tk.BOTH, expand=True)

        # --- 控制項 ---
        ttk.Label(top_frame, text="選擇模型:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.model_var = tk.StringVar(value="large") # <--- 預設值改為 large
        model_options = ["tiny", "base", "small", "medium", "large"]
        self.model_menu = ttk.Combobox(top_frame, textvariable=self.model_var, values=model_options, state="readonly")
        self.model_menu.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        ttk.Label(top_frame, text="輸入類型:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.input_type_var = tk.StringVar(value="檔案")
        self.input_type_var.trace_add("write", self.on_input_type_change)
        ttk.Radiobutton(top_frame, text="檔案 (音訊/影片)", variable=self.input_type_var, value="檔案").grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(top_frame, text="YouTube 連結", variable=self.input_type_var, value="YouTube").grid(row=1, column=2, sticky="w")

        self.file_frame = ttk.Frame(top_frame)
        self.youtube_frame = ttk.Frame(top_frame)
        
        self.file_button = ttk.Button(self.file_frame, text="選擇檔案", command=self.select_file)
        self.file_button.pack(side=tk.LEFT, padx=5)
        self.file_label = ttk.Label(self.file_frame, text="尚未選擇檔案")
        self.file_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(self.youtube_frame, text="貼上連結:").pack(side=tk.LEFT, padx=5)
        self.youtube_entry = ttk.Entry(self.youtube_frame, width=60)
        self.youtube_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        self.download_video_var = tk.BooleanVar(value=False)
        self.download_video_check = ttk.Checkbutton(self.youtube_frame, text="下載影片", variable=self.download_video_var)
        self.download_video_check.pack(side=tk.LEFT)

        ttk.Label(top_frame, text="上下文/提示:").grid(row=3, column=0, padx=5, pady=5, sticky="nw")
        self.prompt_text = tk.Text(top_frame, height=4, width=60, wrap=tk.WORD)
        self.prompt_text.grid(row=3, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        ttk.Label(top_frame, text="輸出格式:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.output_format_var = tk.StringVar(value="SRT")
        self.output_format_var.trace_add("write", self.on_output_format_change)
        ttk.Radiobutton(top_frame, text="純文字", variable=self.output_format_var, value="純文字").grid(row=4, column=1, sticky="w")
        ttk.Radiobutton(top_frame, text="SRT 字幕檔", variable=self.output_format_var, value="SRT").grid(row=4, column=2, sticky="w")

        self.output_dir_label = ttk.Label(top_frame, text="輸出資料夾:")
        self.output_dir_label.grid(row=5, column=0, padx=5, pady=5, sticky="w")
        self.output_dir_var = tk.StringVar()
        self.output_dir_entry = ttk.Entry(top_frame, textvariable=self.output_dir_var, width=60)
        self.output_dir_entry.grid(row=5, column=1, columnspan=3, sticky="ew")
        self.browse_button = ttk.Button(top_frame, text="瀏覽...", command=self.browse_output_dir)
        self.browse_button.grid(row=5, column=4, padx=5)

        self.output_filename_label = ttk.Label(top_frame, text="輸出檔名:")
        self.output_filename_label.grid(row=6, column=0, padx=5, pady=5, sticky="w")
        self.output_filename_var = tk.StringVar()
        self.output_filename_entry = ttk.Entry(top_frame, textvariable=self.output_filename_var, width=60)
        self.output_filename_entry.grid(row=6, column=1, columnspan=3, sticky="ew")

        action_frame = ttk.Frame(top_frame)
        action_frame.grid(row=7, column=1, pady=15, columnspan=2, sticky="w")
        self.transcribe_button = ttk.Button(action_frame, text="開始轉錄", command=self.start_transcription_thread, style="Accent.TButton")
        self.transcribe_button.pack(side=tk.LEFT, padx=5)
        self.autofix_var = tk.BooleanVar(value=True)
        self.autofix_check = ttk.Checkbutton(action_frame, text="自動校正 SRT", variable=self.autofix_var)
        self.autofix_check.pack(side=tk.LEFT, padx=10)
        self.stop_button = ttk.Button(action_frame, text="終止運算", command=self.stop_transcription, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=5)

        ttk.Label(bottom_frame, text="執行過程與結果預覽:").pack(anchor="w")
        self.result_text = scrolledtext.ScrolledText(bottom_frame, wrap=tk.WORD, height=10)
        self.result_text.pack(pady=5, fill=tk.BOTH, expand=True)
        self.save_button = ttk.Button(bottom_frame, text="儲存至指定路徑", command=self.save_result)
        self.save_button.pack(pady=10, anchor="e")

        self.input_source = None
        self.on_input_type_change()
        style = ttk.Style()
        style.configure("Accent.TButton", font=("Arial", 10, "bold"))

    def on_input_type_change(self, *args):
        if self.input_type_var.get() == "檔案":
            self.youtube_frame.grid_remove()
            self.file_frame.grid(row=2, column=0, columnspan=4, sticky="ew")
        else:
            self.file_frame.grid_remove()
            self.youtube_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=5)
        self.update_suggested_filename()

    def on_output_format_change(self, *args):
        self.update_suggested_filename()

    def browse_output_dir(self):
        dir_path = filedialog.askdirectory(title="選擇輸出資料夾")
        if dir_path:
            self.output_dir_var.set(dir_path)

    def select_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("媒體檔案", "*.mp3 *.wav *.m4a *.mp4 *.mov *.mkv"), ("所有檔案", "*.*")])
        if filepath:
            self.input_source = filepath
            filename = os.path.basename(filepath)
            self.file_label.config(text=filename)
            self.output_dir_var.set(os.path.dirname(filepath))
            self.update_suggested_filename()

    def update_suggested_filename(self):
        if self.input_type_var.get() == "檔案" and self.input_source:
            base_name, _ = os.path.splitext(os.path.basename(self.input_source))
            suffix = ".srt" if self.output_format_var.get() == "SRT" else ".txt"
            self.output_filename_var.set(f"{base_name}_transcript{suffix}")
        elif self.input_type_var.get() == "YouTube":
            suffix = ".srt" if self.output_format_var.get() == "SRT" else ".txt"
            self.output_filename_var.set(f"youtube_transcript{suffix}")

    def stop_transcription(self):
        print("收到終止請求...")
        self.stop_thread_flag = True
        self.result_text.insert(tk.END, "\n\n--- 收到終止請求，正在嘗試停止任務... ---\n")

    def start_transcription_thread(self):
        input_type_choice = self.input_type_var.get()
        if input_type_choice == "檔案":
            if not self.input_source or not isinstance(self.input_source, str):
                messagebox.showwarning("輸入錯誤", "請先選擇一個有效的檔案。")
                return
            _, ext = os.path.splitext(self.input_source)
            self.internal_input_type = 'video' if ext.lower() not in ['.mp3', '.wav', '.m4a', '.ogg'] else 'audio'
        else:
            self.input_source = self.youtube_entry.get()
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

    # <--- 新增的YT下載進度回報函式 ---
    def yt_dlp_progress_hook(self, d):
        """這個函式會被 yt-dlp 在下載過程中從背景執行緒呼叫"""
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded_bytes = d.get('downloaded_bytes', 0)
            
            if total_bytes > 0:
                percent_str = d.get('_percent_str', '0.0%')
                # 移除 ANSI 顏色代碼
                percent_str = ''.join(filter(lambda char: char.isdigit() or char in '%.', percent_str))
                
                speed_str = d.get('_speed_str', ' N/A').strip()
                eta_str = d.get('_eta_str', 'N/A').strip()
                
                status_str = f"[download] {percent_str}% of {total_bytes/1024/1024:.2f}MB at {speed_str} ETA {eta_str}\n"
                
                # 使用 after() 方法，安全地從背景執行緒更新 GUI
                self.master.after(0, lambda: self.result_text.insert(tk.END, status_str))
                self.master.after(0, lambda: self.result_text.see(tk.END))

        elif d['status'] == 'finished':
            filename = d.get('filename', '')
            status_str = f"\n檔案 '{os.path.basename(filename)}' 下載完成。\n"
            self.master.after(0, lambda: self.result_text.insert(tk.END, status_str))

        elif d['status'] == 'error':
            status_str = "\n[錯誤] 下載過程中發生錯誤。\n"
            self.master.after(0, lambda: self.result_text.insert(tk.END, status_str))

    def run_transcription(self):
        original_stdout = sys.stdout
        start_time = time.time()
        
        # <--- 修改：準備好要傳遞給引擎的額外參數 ---
        extra_args = {
            'stop_flag_check': lambda: self.stop_thread_flag,
            'download_video': self.download_video_var.get(),
            'output_dir': self.output_dir_var.get(),
            'progress_hook': self.yt_dlp_progress_hook  # <--- 在這裡新增了這一行
        }
        
        try:
            model_size = self.model_var.get()
            self.master.after(0, self.update_result, f"正在載入 {model_size} 模型...\n")
            self.engine.load_model(model_size)
            
            if self.stop_thread_flag: raise InterruptedError("任務在模型載入後被終止")

            prompt = self.prompt_text.get("1.0", tk.END).strip()
            self.master.after(0, lambda: self.result_text.insert(tk.END, "模型載入完畢，準備處理輸入源...\n"))
            
            if self.stop_thread_flag: raise InterruptedError("任務在處理輸入源前被終止")

            self.master.after(0, lambda: self.result_text.insert(tk.END, "\n--- 開始轉錄，即時進度如下 ---\n"))
            sys.stdout = StdoutRedirector(self.result_text)

            # 使用 **extra_args 傳遞所有參數
            self.transcription_result = self.engine.process_input(
                self.input_source, 
                self.internal_input_type, 
                prompt,
                **extra_args
            )
            
            if self.stop_thread_flag:
                raise InterruptedError("任務在轉錄過程中被終止")

        except InterruptedError as e:
            sys.stdout = original_stdout
            print(e)
            self.master.after(0, self.update_result, "任務已成功終止。")
        except Exception as e:
            sys.stdout = original_stdout
            import traceback
            error_details = f"轉錄過程中發生錯誤:\n{e}\n\n{traceback.format_exc()}"
            self.master.after(0, self.update_result, error_details)
            print(error_details)
        finally:
            sys.stdout = original_stdout
            
            if self.transcription_result and not self.stop_thread_flag:
                end_time = time.time()
                elapsed_time = end_time - start_time
                time_report = f"\n\n--- 任務完成！總耗時: {elapsed_time:.2f} 秒 ---\n"
                self.master.after(0, lambda: self.result_text.insert(tk.END, time_report))

            self.master.after(0, lambda: self.transcribe_button.config(state="normal"))
            self.master.after(0, lambda: self.stop_button.config(state="disabled"))

    def update_result(self, text):
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)

    def generate_output_content(self):
        if not self.transcription_result: return ""
        output_format = self.output_format_var.get()
        if output_format == "純文字":
            return self.transcription_result.get('text', "")
        elif output_format == "SRT":
            original_segments = self.transcription_result.get('segments', [])
            refined_segments = srt_utils.refine_srt_segments(original_segments, max_chars=20)
            return srt_utils.generate_srt_from_segments(refined_segments)
        return ""

    def save_result(self):
        output_dir = self.output_dir_var.get()
        output_filename = self.output_filename_var.get()
        if not self.transcription_result:
            messagebox.showwarning("內容為空", "沒有可以儲存的內容。請先執行轉錄。")
            return
        if not output_dir or not os.path.isdir(output_dir):
            messagebox.showwarning("路徑錯誤", f"請指定一個有效的輸出資料夾。")
            return
        if not output_filename:
            messagebox.showwarning("檔名錯誤", "請輸入輸出檔名。")
            return
        full_filepath = os.path.join(output_dir, output_filename)
        content = self.generate_output_content()
        if not content:
            messagebox.showwarning("內容為空", "無法生成有效的輸出內容。")
            return
        final_content = content
        correction_applied = False
        if self.output_format_var.get() == "SRT" and self.autofix_var.get():
            try:
                print("正在執行 SRT 自動校正...")
                corrected_content = fix_and_process_srt(content)
                if corrected_content != content:
                    final_content = corrected_content
                    correction_applied = True
                    print("SRT 自動校正完成。")
                else:
                    print("SRT 內容無需校正或校正失敗。")
            except Exception as e:
                messagebox.showwarning("校正失敗", f"SRT 校正過程中發生錯誤，將儲存未校正的版本。\n錯誤: {e}")
        try:
            with open(full_filepath, 'w', encoding='utf-8') as f:
                f.write(final_content)
            success_message = f"檔案已成功儲存至:\n{full_filepath}"
            if correction_applied:
                success_message = f"檔案已成功校正並儲存至:\n{full_filepath}"
            messagebox.showinfo("儲存成功", success_message)
        except Exception as e:
            messagebox.showerror("儲存失敗", f"儲存檔案時發生錯誤:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = WhisperApp(root)
    root.mainloop()