"""
知识库分块与文档加载测试 — test_knowledge_base.py

覆盖 core/knowledge_base.py 的纯函数：
  _split_into_chunks / _read_file / load_documents

注意：
  - 不测 KnowledgeBase 类（依赖模型 + FAISS，属集成测试）。
  - import core.knowledge_base 会连带加载 faiss/sentence-transformers/torch，
    单测约需 10 秒，这是已知代价（方案 A：接受）。
"""

from core.knowledge_base import _read_file, _split_into_chunks, load_documents


# ── _split_into_chunks ───────────────────────────────────

def test_split_short_text_not_split():
    """长度 < chunk_size 的短文本返回单个块。"""
    text = "这是一个超过二十个字符的短文本，不需要切分。"
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [text]


def test_split_paragraph_boundary():
    """段落边界（双换行）优先于硬切。"""
    text = "a" * 25 + "\n\n" + "b" * 60
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [
        "a" * 25,
        "b" * 38,
        "b" * 22,
    ]


def test_split_sentence_boundary():
    """句子边界（句号后跟换行）处切分。"""
    text = "c" * 20 + "。\n" + "d" * 50
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [
        "c" * 20 + "。",
        "d" * 39,
        "d" * 11,
    ]


def test_split_line_break_boundary():
    """简单换行处切分。"""
    text = "e" * 25 + "\n" + "f" * 60
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [
        "e" * 25,
        "f" * 39,
        "f" * 21,
    ]


def test_split_hard_cut():
    """无任何断点时，在 chunk_size 处硬切。"""
    text = "x" * 110
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [
        "x" * 40,
        "x" * 40,
        "x" * 30,
    ]


def test_split_overlap():
    """overlap 生效：相邻块之间重叠 overlap 个字符。"""
    text = "0123456789" * 12  # 120 字符，chunk_size=40, overlap=8
    chunks = _split_into_chunks(text, chunk_size=40, overlap=8)
    # 第 1 块末 8 字符 == 第 2 块首 8 字符
    assert chunks[0][-8:] == chunks[1][:8]
    # 精确断言分块结果
    assert chunks == [
        "0123456789012345678901234567890123456789",
        "2345678901234567890123456789012345678901",
        "4567890123456789012345678901234567890123",
        "678901234567890123456789",
    ]


def test_split_keeps_short_last_chunk():
    """最后一块即使 <20 字符也保留（不经过短碎片过滤）。"""
    text = "y" * 85
    assert _split_into_chunks(text, chunk_size=40, overlap=0) == [
        "y" * 40,
        "y" * 40,
        "y" * 5,
    ]


# ── _read_file ───────────────────────────────────────────

def test_read_file_utf8(tmp_path):
    """正常 UTF-8 文件读取。"""
    p = tmp_path / "doc.txt"
    p.write_text("内容", encoding="utf-8")
    assert _read_file(str(p)) == "内容"


def test_read_file_binary_returns_none(tmp_path):
    """非 UTF-8 字节 → 返回 None。"""
    p = tmp_path / "bin.bin"
    p.write_bytes(b"\xff\xfe\x00\x01")
    assert _read_file(str(p)) is None


# ── load_documents ───────────────────────────────────────

def test_load_documents(tmp_path):
    """加载支持格式，跳过过短文件与不支持格式。"""
    (tmp_path / "doc.txt").write_text("这是一段超过五十个字符的文档内容。" * 4, encoding="utf-8")
    (tmp_path / "short.md").write_text("太短", encoding="utf-8")
    (tmp_path / "bad.pdf").write_text("pdf content that is long enough" * 5, encoding="utf-8")

    docs = load_documents(str(tmp_path))

    # 只有 doc.txt 被加载（short.md 过短、bad.pdf 格式不支持）
    assert len(docs) == 1
    assert docs[0]["source"] == "doc.txt"
    assert docs[0]["id"] == "doc.txt#chunk0"
    assert docs[0]["text"].startswith("这是一段超过五十个字")
