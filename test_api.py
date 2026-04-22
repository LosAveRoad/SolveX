import asyncio
from openai import AsyncOpenAI


async def test_api():
    client = AsyncOpenAI(
        api_key="bb42554938b54241a4f9e86022cb31db.DShTGwiYP0WVvLPa",
        base_url="https://open.bigmodel.cn/api/coding/paas/v4",
    )
    response = await client.chat.completions.create(
        model="glm-4.7",
        messages=[{"role": "user", "content": "请用一句话回答：1+1等于几？"}],
        max_tokens=1024,
        temperature=0.0,
    )
    print("API 连接成功！")
    print(f"回复: {response.choices[0].message.content}")
    print(f"Token 用量: prompt={response.usage.prompt_tokens}, completion={response.usage.completion_tokens}")
    print(f"完整响应: {response}")


if __name__ == "__main__":
    asyncio.run(test_api())
