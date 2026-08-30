"""
LLM 重试机制测试 — test_llm_retry.py

覆盖 core/llm.py 的 _is_retryable_error 与 chat_completion_with_retry。

特点：
  - mock 掉 client.chat.completions.create，不真调 DeepSeek。
  - mock 掉 time.sleep，记录调用次数与间隔，不真等待。
  - 异常用 openai 2.45 真实异常类构造，确保 isinstance 分支命中。
"""

import httpx
import openai

from core.llm import DeepSeekClient, _is_retryable_error


# ── 辅助：构造 openai 异常 ───────────────────────────────

def _req() -> httpx.Request:
    return httpx.Request("POST", "http://x")


def _conn_error() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=_req())


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=_req())


def _status_error(code: int) -> openai.APIStatusError:
    resp = httpx.Response(code, request=_req())
    return openai.APIStatusError("msg", response=resp, body=None)


# ── 辅助：构造带假 client 的 DeepSeekClient ──────────────

class _FakeCompletions:
    def __init__(self, create_fn):
        self._create_fn = create_fn

    def create(self, **kwargs):
        return self._create_fn(**kwargs)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, chat):
        self.chat = chat


def _make_client(create_fn) -> DeepSeekClient:
    """构造 DeepSeekClient，并将其 client 替换为假对象，create 行为由 create_fn 决定。"""
    client = DeepSeekClient()
    client.client = _FakeClient(_FakeChat(_FakeCompletions(create_fn)))
    return client


# ── _is_retryable_error ──────────────────────────────────

def test_is_retryable_connection_error():
    assert _is_retryable_error(_conn_error()) is True


def test_is_retryable_timeout():
    """APITimeoutError 是 APIConnectionError 子类，应可重试。"""
    assert _is_retryable_error(_timeout_error()) is True


def test_is_retryable_429():
    assert _is_retryable_error(_status_error(429)) is True


def test_is_retryable_5xx():
    assert _is_retryable_error(_status_error(500)) is True


def test_is_not_retryable_401():
    assert _is_retryable_error(_status_error(401)) is False


def test_is_not_retryable_400():
    assert _is_retryable_error(_status_error(400)) is False


def test_is_not_retryable_generic():
    assert _is_retryable_error(ValueError("x")) is False


# ── chat_completion_with_retry ───────────────────────────

def test_retry_success_first_try(monkeypatch):
    """首次成功：直接返回，不 sleep。"""
    sleeps = []
    monkeypatch.setattr("core.llm.time.sleep", sleeps.append)
    response = object()
    client = _make_client(lambda **kw: response)

    assert client.chat_completion_with_retry() is response
    assert sleeps == []


def test_retry_success_after_transient(monkeypatch):
    """前 2 次连接错误、第 3 次成功：sleep 两次，间隔 2、4。"""
    sleeps = []
    monkeypatch.setattr("core.llm.time.sleep", sleeps.append)

    attempts = {"n": 0}
    response = object()

    def create(**kw):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _conn_error()
        return response

    client = _make_client(create)

    assert client.chat_completion_with_retry() is response
    assert attempts["n"] == 3
    assert sleeps == [2, 4]


def test_retry_exhausted_returns_none(monkeypatch):
    """3 次全 429：返回 None，sleep 两次，间隔 2、4。"""
    sleeps = []
    monkeypatch.setattr("core.llm.time.sleep", sleeps.append)

    attempts = {"n": 0}

    def create(**kw):
        attempts["n"] += 1
        raise _status_error(429)

    client = _make_client(create)

    assert client.chat_completion_with_retry() is None
    assert attempts["n"] == 3
    assert sleeps == [2, 4]


def test_retry_non_retryable_no_sleep(monkeypatch):
    """确定性错误 401：立即放弃，不 sleep。"""
    sleeps = []
    monkeypatch.setattr("core.llm.time.sleep", sleeps.append)

    attempts = {"n": 0}

    def create(**kw):
        attempts["n"] += 1
        raise _status_error(401)

    client = _make_client(create)

    assert client.chat_completion_with_retry() is None
    assert attempts["n"] == 1  # 只调了一次就放弃
    assert sleeps == []
