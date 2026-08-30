import logging
import time

import openai
from openai import OpenAI
from abc import ABC, abstractmethod

from core.config import LLM_Config

logger = logging.getLogger(__name__)


# ── LLM 重试配置 ─────────────────────────────────────────────────
MAX_RETRIES = 3            # 最大尝试次数
RETRY_BACKOFF = [2, 4, 8]  # 指数退避间隔（秒）


def _is_retryable_error(e: Exception) -> bool:
    """
    判断异常是否值得重试。

    只重试「瞬时错误」：网络连接、超时、限流(429)、服务端 5xx。
    认证失败(401/403)、参数错误(4xx) 等确定性错误不重试，立即失败。
    """
    # APIConnectionError 已涵盖 APITimeoutError（超时是其子类）
    if isinstance(e, openai.APIConnectionError):
        return True
    # 有状态码的错误：429 限流 与 5xx 服务端故障可重试
    if isinstance(e, openai.APIStatusError):
        return e.status_code == 429 or e.status_code >= 500
    return False


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""
    def __init__(self, model: str):
        self.model = model
    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """抽象方法，用于与 LLM 进行聊天"""
        pass
    def answer(self, question: str, context: str = "", system_prompt: str = "") -> str:
        """根据问题和上下文生成答案"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"上下文信息：{context}\n问题：{question}"})
        return self.chat(messages)
    

class DeepSeekClient(BaseLLMClient):
    def __init__(self,model: str =  None):
        """
        初始化DeepSeekClient实例，设置API密钥和基础URL。
        """
        config = LLM_Config["deepseek"]
        super().__init__(model or config["model"])
        self.client = OpenAI(api_key=config["api_key"], base_url=config["url"])

    def chat(self, messages: list[dict],**kwargs) -> str:
        """
        使用DeepSeek API进行聊天。

        参数:
            messages (list[dict]): 消息列表，每个消息包含角色和内容。
            **kwargs: 其他传递给API的参数。

        返回:
            str: DeepSeek返回的回复。
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )
        return response.choices[0].message.content

    def chat_completion_with_retry(self, **kwargs):
        """
        带重试的底层 completion 调用（供 agent 主循环使用）。

        与 chat() 的区别：返回完整的 response 对象而非纯文本，
        便于上层处理 tool_calls；失败时自动重试并最终返回 None。

        重试策略：
          - 只重试瞬时错误（网络/超时/限流/5xx），指数退避 2s→4s→8s
          - 认证/参数等确定性错误（4xx）不重试，立即放弃
          - 重试耗尽返回 None，绝不抛异常（对齐项目「不抛异常」风格）

        参数:
            **kwargs: 透传给 client.chat.completions.create 的参数
                      （model / messages / tools 等）

        返回:
            完整 response 对象；调用失败返回 None。
        """
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return self.client.chat.completions.create(**kwargs)
            except Exception as e:
                last_error = e
                if not _is_retryable_error(e):
                    break  # 不可重试错误，重试无意义，立即放弃
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF[attempt])

        # 重试耗尽：记录错误日志，返回 None 让上层降级
        logger.error(
            "LLM 调用失败（%s）：%s", type(last_error).__name__, last_error,
        )
        return None

def get_llm_client(provider: str = "deepseek", **kwargs) -> BaseLLMClient:
    """
    根据供应商名称获取对应的LLM客户端实例。

    参数:
        provider (str): LLM供应商名称，默认为"deepseek"。
        model (str): 可选的模型名称，如果未提供，将使用默认模型。
    """
    clients={"deepseek": DeepSeekClient,}
    if provider not in clients:
        raise ValueError(f"不支持的 LLM 供应商: {provider}，可选: {list(clients.keys())}")
    return clients[provider](**kwargs)