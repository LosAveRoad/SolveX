import httpx
from app.tool.base import BaseTool, ToolResult

TAVILY_API_KEY = "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"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class TavilySearch(BaseTool):
    """Web search using Tavily API."""

    name: str = "web_search_prime"
    description: str = (
        "Search the web for information. Returns titles, URLs, and content snippets. "
        "Use this to find tutorials, blog posts, practical solutions, and recent information."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "search_query": {
                "type": "string",
                "description": "The search query. Use specific keywords for better results.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 5, max: 10).",
                "default": 5,
            },
        },
        "required": ["search_query"],
    }

    async def execute(self, search_query: str, max_results: int = 5) -> ToolResult:
        max_results = min(max_results, 10)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    TAVILY_SEARCH_URL,
                    headers={
                        "Authorization": f"Bearer {TAVILY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": search_query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": False,
                    },
                )
                if resp.status_code != 200:
                    return self.fail_response(f"Tavily API error: {resp.status_code} {resp.text[:200]}")

                data = resp.json()
                results = data.get("results", [])
                if not results:
                    return self.fail_response(f"No results found for: {search_query}")

                lines = [f"Found {len(results)} results for '{search_query}':\n"]
                for i, r in enumerate(results, 1):
                    title = r.get("title", "No title")
                    url = r.get("url", "")
                    content = r.get("content", "")[:500]
                    score = r.get("score", 0)
                    lines.append(f"{i}. [{title}]({url}) (relevance: {score:.2f})")
                    lines.append(f"   {content}\n")

                return self.success_response("\n".join(lines))

        except httpx.TimeoutException:
            return self.fail_response(f"Search timed out for: {search_query}")
        except Exception as e:
            return self.fail_response(f"Search failed: {str(e)}")
