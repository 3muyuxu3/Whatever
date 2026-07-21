"""文本处理服务：分块（chunking）。"""

from ..config import config


def chunk_text(text: str, chunk_size: int | None = None, overlap: int | None = None) -> list[str]:
    """将长文本按固定大小切分为带重叠的块。

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
    step = max(1, chunk_size - overlap)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append(text[start:end])
        if end >= n:
            break
        start += step
    return chunks
