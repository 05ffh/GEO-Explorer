"""Seed default query templates and prompt version into the database."""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.config import settings
from src.models.query_template import QueryTemplate
from src.models.prompt_version import PromptVersion

DEFAULT_TEMPLATES = [
    # 定义认知 (4)
    ("定义认知", "{品牌} 是什么？", 0),
    ("定义认知", "{品牌} 属于什么行业？", 1),
    ("定义认知", "{品牌} 的核心功能有哪些？", 2),
    ("定义认知", "{品牌} 提供什么产品/服务？", 3),
    # 场景推荐 (5)
    ("场景推荐", "最好用的{行业}工具有哪些？", 4),
    ("场景推荐", "小团队适合什么{品类}？", 5),
    ("场景推荐", "{行业}常用的平台有哪些？", 6),
    ("场景推荐", "推荐几个{场景}的工具或平台", 7),
    ("场景推荐", "{行业}领域有哪些值得关注的公司？", 8),
    # 对比评价 (4)
    ("对比评价", "{品牌} 和 {竞品} 有什么区别？", 9),
    ("对比评价", "{品牌} 的优点和缺点是什么？", 10),
    ("对比评价", "{品牌} 相比同行有什么优势？", 11),
    ("对比评价", "{竞品} 和 {品牌} 哪个更好？", 12),
    # 信任验证 (4)
    ("信任验证", "{品牌} 靠谱吗？", 13),
    ("信任验证", "{品牌} 的用户口碑怎么样？", 14),
    ("信任验证", "{品牌} 有没有负面评价？", 15),
    ("信任验证", "{品牌} 值得选择吗？", 16),
    # 场景联想 (5)
    ("场景联想", "想做{场景}，用什么工具比较好？", 17),
    ("场景联想", "{场景}的解决方案有哪些？", 18),
    ("场景联想", "{目标用户}适合什么平台？", 19),
    ("场景联想", "如何解决{场景}的问题？", 20),
    ("场景联想", "{目标用户}新手入门用什么工具？", 21),
]

DEFAULT_SYSTEM_PROMPT = (
    "你是一个客观、准确的AI助手。请基于你的知识如实回答问题。"
    "如果引用来源，请注明出处。"
)


async def seed(org_id=None):
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        for dimension, text, priority in DEFAULT_TEMPLATES:
            result = await db.execute(
                select(QueryTemplate).where(QueryTemplate.template_text == text)
            )
            if result.scalar_one_or_none():
                continue
            db.add(QueryTemplate(
                organization_id=org_id,
                dimension=dimension,
                template_text=text,
                priority=priority,
            ))

        result = await db.execute(
            select(PromptVersion).where(PromptVersion.name == "default-v1")
        )
        if not result.scalar_one_or_none():
            db.add(PromptVersion(
                name="default-v1",
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                version=1,
                status="active",
            ))

        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
