"""文件解析工具：支持 PDF / TXT / MD，兼容多种非 UTF-8 编码。"""

import os

from .logger import get_logger

logger = get_logger("file_parser")

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}


def _detect_and_decode(raw: bytes) -> str:
    """检测字节流编码并解码为字符串。

    优先使用 charset-normalizer，失败则回退到 chardet，最后回退到 UTF-8。
    """
    # 1) charset-normalizer
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(raw).best()
        if best is not None:
            return str(best)
    except Exception:  # noqa: BLE001
        pass

    # 2) chardet
    try:
        import chardet

        enc = chardet.detect(raw).get("encoding") or "utf-8"
        return raw.decode(enc, errors="replace")
    except Exception:  # noqa: BLE001
        # 3) 兜底
        return raw.decode("utf-8", errors="replace")


def _parse_pdf(path: str) -> str:
    """使用 PyMuPDF 提取 PDF 文本。"""
    import fitz  # PyMuPDF

    parts = []
    with fitz.open(path) as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts)


def parse_file(path: str) -> str:
    """解析文件并返回纯文本内容。"""
    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning("未知扩展名 %s，按文本文件处理", ext)

    if ext == ".pdf":
        return _parse_pdf(path)

    with open(path, "rb") as f:
        return _detect_and_decode(f.read())
