from openai import OpenAI
from core.config import LLM_Config
from abc import ABC, abstractmethod

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