# srt_processor.py SRT 格式與文字精加工工具（處理標點等）
import srt
import re

def fix_and_process_srt(srt_content: str, remove_punctuation: bool = True) -> str:
    """
    一個整合的 SRT 處理函式。
    1. 解析 SRT 字串，處理可能存在的格式錯誤。
    2. 去除每句末尾的標點符號。
    3. 將處理後的結果重新組合成標準的 SRT 字串。

    :param srt_content: 原始的 SRT 內容字串。
    :param remove_punctuation: 是否要移除句尾標點。
    :return: 處理過的 SRT 內容字串。
    """
    try:
        # 1. 解析 SRT
        # srt.parse 對格式要求嚴格，我們可以在此加入一些預處理來提高成功率
        # 例如，移除多餘的空行
        cleaned_content = "\n".join(line for line in srt_content.strip().splitlines() if line.strip())
        subs = list(srt.parse(cleaned_content))
        
        if not subs:
            return "" # 如果沒有內容，返回空字串

        # 2. 處理每一句字幕
        punctuations_to_remove = '.,。?!！?？'
        
        for sub in subs:
            # 去除前後空白
            modified_content = sub.content.strip()
            
            # 移除句尾標點
            if remove_punctuation:
                modified_content = modified_content.rstrip(punctuations_to_remove)
            
            # 更新字幕內容
            sub.content = modified_content.strip()

        # 3. 重新組合成 SRT 字串
        # srt.compose 會生成格式非常標準的 SRT 內容
        return srt.compose(subs)

    except Exception as e:
        print(f"SRT 處理過程中發生錯誤: {e}")
        # 如果發生任何解析或處理錯誤，為了不丟失資料，返回原始（清理過的）內容
        return cleaned_content if 'cleaned_content' in locals() else srt_content