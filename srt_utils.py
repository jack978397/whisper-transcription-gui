# srt_utils.py  SRT 內容生成與排版工具（處理斷句）
import datetime
import re

def format_srt_time(seconds: float) -> str:
    """
    將秒數轉換為 00:00:00,000 的 SRT 時間格式。
    """
    if seconds < 0:
        seconds = 0
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = delta.microseconds // 1000
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

def refine_srt_segments(segments: list, max_chars: int = 20) -> list:
    """
    對 Whisper 生成的 segments 進行精加工。
    1. 將超過長度限制的句子進行自然斷句。
    2. 重新計算斷句後的時間戳。
    3. 確保每個 segment 只有一句話。

    :param segments: Whisper 原始的 segments 列表。
    :param max_chars: 每句字幕的最大字元數限制。
    :return: 一個新的、經過精加工的 segments 列表。
    """
    new_segments = []
    
    # 優先在這些標點符號後面斷句
    punctuation = "，。、？！, . ! ? "

    for segment in segments:
        text = segment['text'].strip()
        
        if not text:
            continue

        # 如果句子本身不長，且沒有包含多個句子，就直接使用
        # 這裡簡化判斷，只看長度
        if len(text) <= max_chars:
            new_segments.append(segment)
            continue

        # 如果句子太長，則需要分割
        start_time = segment['start']
        end_time = segment['end']
        duration = end_time - start_time
        
        if duration <= 0:
            # 對於沒有時長的片段，直接使用原始文字，避免除以零錯誤
            new_segments.append(segment)
            continue

        # 使用正則表達式來分割，同時保留分隔符
        parts = re.split(f'([{punctuation}])', text)
        sub_sentences = []
        # 將文字和其後面的標點合併
        i = 0
        while i < len(parts):
            sentence_part = parts[i]
            i += 1
            if i < len(parts):
                sentence_part += parts[i]
                i += 1
            sub_sentences.append(sentence_part)

        current_sentence = ""
        total_len = len(text)

        for sub in sub_sentences:
            sub = sub.strip()
            if not sub:
                continue
            
            # 如果加上新的子句會超過長度限制，就先處理當前的句子
            if len(current_sentence) > 0 and len(current_sentence + sub) > max_chars:
                # 按字數比例計算這個句子的時間戳
                sentence_len = len(current_sentence)
                sentence_duration = (sentence_len / total_len) * duration
                new_end_time = start_time + sentence_duration
                
                new_segments.append({
                    'start': start_time,
                    'end': new_end_time,
                    'text': current_sentence
                })
                
                # 更新下一句的開始時間和文字
                start_time = new_end_time
                current_sentence = sub
            else:
                # 如果沒超長，就繼續合併
                current_sentence += (" " if current_sentence and sub else "") + sub

        # 處理最後剩下的句子
        if current_sentence:
            new_segments.append({
                'start': start_time,
                'end': end_time, # 最後一句直接使用原始的結束時間，確保時間軸連續
                'text': current_sentence
            })

    # 最後，為新的 segments 重新編號 id
    for i, seg in enumerate(new_segments):
        seg['id'] = i
        
    return new_segments

def generate_srt_from_segments(segments: list) -> str:
    """
    根據處理過的 segments 列表，生成最終的 SRT 格式字串。
    """
    srt_content = []
    for i, segment in enumerate(segments):
        start_time = format_srt_time(segment['start'])
        end_time = format_srt_time(segment['end'])
        text = segment['text'].strip()
        
        if text:
            srt_content.append(str(i + 1))
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(text)
            srt_content.append("") # 空行分隔
    
    return "\n".join(srt_content)