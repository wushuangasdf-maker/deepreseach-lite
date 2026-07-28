"""
私有知识库模块 — knowledge_base.py

使用 FAISS + bge-small-zh 实现本地文档的向量检索。

功能：
  1. 文档摄入：从目录加载文档 → 分块 → 向量化 → FAISS 索引
  2. 查询检索：查询向量化 → FAISS 相似度搜索 → 返回 top-k 文本块

设计原则：
  - 延迟加载模型：只有首次 search()/build() 时才加载 SentenceTransformer
  - 向量归一化：内积索引 + 归一化向量 → 等价于余弦相似度
  - 持久化：索引和文档元数据保存到磁盘，重启无需重建

用法：
    # 构建索引
    python core/knowledge_base.py --build --doc_dir ./my_knowledge --index_dir ./kb_index

    # 查询
    python core/knowledge_base.py --query "什么是RAG" --index_dir ./kb_index
"""

import os
import sys
import pickle
from typing import Optional

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from modelscope import snapshot_download

# Windows 控制台 UTF-8 编码支持
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# 配置常量
# ═══════════════════════════════════════════════════════════════

EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"  # 384 维向量，中英文都支持
CHUNK_SIZE = 512       # 每块字符数（bge-small 最大 512 tokens）
CHUNK_OVERLAP = 80     # 块之间重叠字符数，防止关键信息落在边界
TOP_K = 5              # 默认返回 top-5 结果

# bge 系列模型专用：查询时加指令前缀可提升检索精度 1-3%
# 文档编码时不加，查询编码时才加（非对称策略）
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："

# 支持的文件格式
SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".rst", ".json", ".csv", ".yaml", ".yml"}


# ═══════════════════════════════════════════════════════════════
# 文档加载与分块
# ═══════════════════════════════════════════════════════════════

def _read_file(filepath: str) -> Optional[str]:
    """用 UTF-8 读取文件，失败返回 None（跳过二进制文件）"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except (UnicodeDecodeError, IOError):
        return None


def _split_into_chunks(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """
    将长文本切分为有重叠的块。

    切分优先级（在每块末尾附近找最佳断点）：
      1. 段落边界（\\n\\n）—— 最自然，保持语义完整
      2. 句子边界（。！？后跟换行或空格）
      3. 简单换行
      4. 兜底：固定长度硬切
    """
    chunks: list[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # 最后一块，直接取到尾
        if end >= text_len:
            chunks.append(text[start:])
            break

        # 在 chunk 末尾附近找最佳切分点
        segment = text[start:end]

        # 优先级 1：段落边界（双换行）
        para_break = segment.rfind("\n\n")
        if para_break > chunk_size * 0.5:
            end = start + para_break
        else:
            # 优先级 2：句子边界
            best_sentence = 0
            for punct in ["。\n", "。 ", "！\n", "！ ", "？\n", "？ "]:
                idx = segment.rfind(punct)
                if idx > best_sentence:
                    best_sentence = idx
            if best_sentence > chunk_size * 0.3:
                end = start + best_sentence + 1
            else:
                # 优先级 3：简单换行
                line_break = segment.rfind("\n")
                if line_break > chunk_size * 0.5:
                    end = start + line_break
                # 优先级 4：找不到合适断点 → 硬切在 chunk_size 处

        chunk_text = text[start:end].strip()
        if len(chunk_text) > 20:  # 过滤太短的碎片
            chunks.append(chunk_text)

        start = end - overlap

    return chunks


def load_documents(doc_dir: str) -> list[dict]:
    """
    从目录递归加载所有支持的文档，分块后返回。

    参数:
        doc_dir: 文档根目录

    返回:
        [{"id": "相对路径#chunk序号", "text": "文本内容", "source": "相对路径"}, ...]
    """
    documents: list[dict] = []

    for root, _, files in os.walk(doc_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            text = _read_file(filepath)
            if not text or len(text.strip()) < 50:  # 太短的文件跳过
                continue

            chunks = _split_into_chunks(text)
            rel_path = os.path.relpath(filepath, doc_dir)

            for i, chunk in enumerate(chunks):
                documents.append({
                    "id": f"{rel_path}#chunk{i}",
                    "text": chunk,
                    "source": rel_path,
                })

    return documents


# ═══════════════════════════════════════════════════════════════
# KnowledgeBase 主类
# ═══════════════════════════════════════════════════════════════

class KnowledgeBase:
    """
    FAISS + bge-small 向量知识库。

    特性：
      - 延迟加载模型：首次 search()/build() 时才加载 SentenceTransformer
      - 自动加载索引：构造时如果磁盘已有索引则自动恢复
      - 查询时加 bge 指令前缀：提升检索精度

    用法:
        kb = KnowledgeBase("./kb_index")
        results = kb.search("查询文本", top_k=5)
        for r in results:
            print(f"[{r['score']:.2f}] {r['source']}: {r['text'][:80]}...")
    """

    def __init__(self, index_dir: str):
        self.index_dir = index_dir
        self.model: Optional[SentenceTransformer] = None   # 延迟加载
        self.index: Optional[faiss.Index] = None
        self.documents: list[dict] = []

        # 如果磁盘已有索引，自动加载
        if os.path.exists(os.path.join(index_dir, "index.faiss")):
            self._load_disk(index_dir)

    # ── 延迟加载模型 ──────────────────────────────────

    def _get_model(self) -> SentenceTransformer:
        """首次调用时才加载模型（通过 ModelScope 下载，国内无障碍）"""
        if self.model is None:
            # 从 ModelScope 下载模型到本地缓存（国内网络稳定）
            model_dir = snapshot_download(EMBEDDING_MODEL)
            self.model = SentenceTransformer(model_dir)
        return self.model

    # ── 构建索引 ──────────────────────────────────────

    def build(self, doc_dir: str):
        """
        从文档目录构建 FAISS 索引并持久化到磁盘。

        参数:
            doc_dir: 包含文档的目录路径
        """
        print(f"📂 正在加载文档：{doc_dir}")
        documents = load_documents(doc_dir)
        if not documents:
            raise ValueError(
                f"目录 {doc_dir} 中未找到有效文档"
                f"（支持的格式：{SUPPORTED_EXTENSIONS}）"
            )
        print(f"  共 {len(documents)} 个文本块")

        # 向量化
        print(f"🧮 正在使用 {EMBEDDING_MODEL} 生成向量...")
        model = self._get_model()
        texts = [d["text"] for d in documents]

        # normalize_embeddings=True → 向量归一化 → 内积 = 余弦相似度
        embeddings = model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        dim = embeddings.shape[1]  # bge-small = 384

        # 构建 FAISS 索引
        # IndexFlatIP：暴力精确搜索（内积），数据量 < 10 万时最合适
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))  # FAISS 要求 float32

        # 持久化到磁盘
        os.makedirs(self.index_dir, exist_ok=True)
        self._save_disk(index, documents)

        self.index = index
        self.documents = documents
        print(f"✅ 索引构建完成：{index.ntotal} 个向量，维度 {dim}")
        print(f"   已保存到 {self.index_dir}")

    # ── 单条查询 ─────────────────────────────────────

    def search(self, query: str, top_k: int = TOP_K) -> list[dict]:
        """
        在知识库中检索与查询最相关的文本块。

        参数:
            query: 自然语言查询
            top_k: 返回的最大结果数

        返回:
            [{"id": str, "text": str, "source": str, "score": float}, ...]
            按 score（余弦相似度，0~1）从高到低排列。
            索引未加载时返回空列表。
        """
        if self.index is None:
            return []

        model = self._get_model()

        # 查询时加 bge 指令前缀（文档编码时不加——非对称策略）
        query_embedding = model.encode(
            [BGE_QUERY_PREFIX + query],
            normalize_embeddings=True,
        ).astype(np.float32)

        top_k = min(top_k, self.index.ntotal)
        scores, indices = self.index.search(query_embedding, top_k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.documents):
                continue
            doc = self.documents[idx]
            results.append({
                "id": doc["id"],
                "text": doc["text"],
                "source": doc["source"],
                "score": float(score),
            })

        return results

    # ── 批量查询 ────────────────────────────────────

    def search_batch(self, queries: list[str], top_k: int = TOP_K) -> list[list[dict]]:
        """
        批量查询。比逐个调 search() 快（一次编码所有查询）。

        适合：同时研究多个子问题时，一次性查完所有相关的 KB 内容。

        参数:
            queries: 查询文本列表
            top_k:   每个查询返回的结果数

        返回:
            [[{...}, ...], ...] — 每个查询的结果列表
        """
        if self.index is None:
            return [[] for _ in queries]

        model = self._get_model()
        query_embeddings = model.encode(
            [BGE_QUERY_PREFIX + q for q in queries],
            normalize_embeddings=True,
        ).astype(np.float32)

        top_k = min(top_k, self.index.ntotal)
        all_scores, all_indices = self.index.search(query_embeddings, top_k)

        all_results: list[list[dict]] = []
        for scores, indices in zip(all_scores, all_indices):
            results: list[dict] = []
            for score, idx in zip(scores, indices):
                if idx < 0 or idx >= len(self.documents):
                    continue
                doc = self.documents[idx]
                results.append({
                    "id": doc["id"],
                    "text": doc["text"],
                    "source": doc["source"],
                    "score": float(score),
                })
            all_results.append(results)

        return all_results

    # ── 属性 ─────────────────────────────────────────

    @property
    def is_loaded(self) -> bool:
        """索引是否已加载"""
        return self.index is not None

    @property
    def size(self) -> int:
        """索引中的向量总数"""
        return self.index.ntotal if self.index else 0

    # ── 持久化 ───────────────────────────────────────

    def _save_disk(self, index: faiss.Index, documents: list[dict]):
        """将索引和文档元数据写入磁盘"""
        faiss.write_index(index, os.path.join(self.index_dir, "index.faiss"))
        with open(os.path.join(self.index_dir, "documents.pkl"), "wb") as f:
            pickle.dump(documents, f)

    def _load_disk(self, index_dir: str):
        """从磁盘加载索引和文档元数据"""
        faiss_path = os.path.join(index_dir, "index.faiss")
        docs_path = os.path.join(index_dir, "documents.pkl")

        if not os.path.exists(faiss_path):
            raise FileNotFoundError(f"索引文件不存在：{faiss_path}")

        self.index = faiss.read_index(faiss_path)
        self.index_dir = index_dir

        if os.path.exists(docs_path):
            with open(docs_path, "rb") as f:
                self.documents = pickle.load(f)

        print(f"📦 已加载知识库索引：{self.index.ntotal} 个向量")


# ═══════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="私有知识库构建与查询（FAISS + bge-small-zh）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python core/knowledge_base.py --build --doc_dir ./my_knowledge
  python core/knowledge_base.py --query "RAG 的实现方式"
  python core/knowledge_base.py --query "向量检索" --top_k 10
        """,
    )
    parser.add_argument("--build", action="store_true", help="构建 FAISS 索引")
    parser.add_argument("--doc_dir", default="./docs", help="文档目录（--build 时使用）")
    parser.add_argument("--index_dir", default="./kb_index", help="索引保存/加载目录")
    parser.add_argument("--query", type=str, help="在知识库中搜索")
    parser.add_argument("--top_k", type=int, default=TOP_K,
                        help=f"返回结果数（默认 {TOP_K}）")

    args = parser.parse_args()

    if args.build:
        kb = KnowledgeBase(args.index_dir)
        kb.build(args.doc_dir)

    if args.query:
        kb = KnowledgeBase(args.index_dir)
        if not kb.is_loaded:
            print("❌ 知识库索引不存在，请先运行 --build 构建索引")
            exit(1)
        results = kb.search(args.query, top_k=args.top_k)
        print(f"\n🔍 查询：「{args.query}」")
        print(f"{'=' * 65}")
        if not results:
            print("（未找到相关结果）")
        else:
            for i, r in enumerate(results, 1):
                print(f"\n[{i}] {r['source']}  (相似度: {r['score']:.3f})")
                preview = r['text'][:200]
                if len(r['text']) > 200:
                    preview += "..."
                print(f"    {preview}")
