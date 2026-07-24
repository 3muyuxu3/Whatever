"""文本处理服务：分块（chunking）。"""

from ..config import config

# 句子边界分隔符（优先在这些位置断开，得到语义更完整的文本块，）
_SENTENCE_SEPS = ["。", "！", "？", ".\n", "!\n",
                  "?\n", "\n\n", ". ", "! ", "? ", "\n"]


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """将长文本按固定大小切分为带重叠的块，并尽量在句子边界处断开。

    :param text:       原始文本
    :param chunk_size: 每块字符数（默认 config.DEFAULT_CHUNK_SIZE=500）
    :param overlap:    相邻块重叠字符数（默认 config.DEFAULT_CHUNK_OVERLAP=50）
    """
    chunk_size = chunk_size or config.DEFAULT_CHUNK_SIZE
    overlap = overlap or config.DEFAULT_CHUNK_OVERLAP
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        # 未到文本末尾时，尝试在窗口内最靠后的句子边界处断开
        # （边界须落在窗口 30% 之后，避免切出过短的块）
        if end < n:
            window = text[start:end]
            best = -1
            for sep in _SENTENCE_SEPS:
                pos = window.rfind(sep)
                if pos != -1 and pos > chunk_size * 0.3:
                    best = max(best, pos + len(sep))
            if best != -1:
                end = start + best
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        # 下一块从重叠位置开始；确保 start 前进以避免死循环
        nxt = end - overlap
        start = nxt if nxt > start else end
    return chunks
