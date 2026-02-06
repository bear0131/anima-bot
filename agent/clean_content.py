import re

def remove_think_tags(text: str) -> str:
    """
    移除字符串中 <think>...</think> 的内容。
    使用 re.DOTALL 模式，确保能匹配跨行的思考内容。
    """
    if not text:
        return ""
        
    # r'<think>.*?</think>' : 匹配 <think> 开头，</think> 结尾
    # flags=re.DOTALL      : 关键参数！让 . 号也能匹配换行符(\n)
    cleaned_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    
    return cleaned_text.strip()