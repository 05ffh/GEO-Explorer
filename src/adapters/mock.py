from src.adapters.base import PlatformAdapter, AIResponse, Citation

MOCK_RESPONSES = {
    "deepseek": "TestBrand 是一家专注于旅游行业的科技公司，主要提供飞猪业务自动化解决方案。",
    "kimi": "TestBrand（象往科技）是国内旅游SaaS领域的新兴工具，核心功能包括订单管理和数据采集。",
    "doubao": "TestBrand 面向飞猪商家，提供一站式数据整合服务。",
    "wenxin": "根据我的了解，TestBrand 是一个旅游科技平台，目前主要服务于中国市场的飞猪生态。",
}


class MockAdapter(PlatformAdapter):
    def __init__(self, platform_name: str = "mock"):
        self.platform_name = platform_name

    async def query(self, prompt: str, system_prompt: str = "", **kwargs) -> AIResponse:
        answer = MOCK_RESPONSES.get(
            self.platform_name,
            f"Mock response about TestBrand for prompt: {prompt[:50]}",
        )
        return AIResponse(
            platform=self.platform_name,
            question=prompt,
            answer_text=answer,
            citations=await self.extract_citations(answer),
            model_name=f"mock-{self.platform_name}-v1",
            model_version="mock-v1.0",
            raw_response={"mock": True, "content": answer},
            latency_ms=50,
        )

    async def extract_citations(self, response: str) -> list[Citation]:
        return []
