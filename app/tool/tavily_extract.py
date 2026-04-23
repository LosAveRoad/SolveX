import httpx
from app.tool.base import BaseTool, ToolResult

TAVILY_API_KEY = "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"
TAVILY_EXTRACT_URL = "https://api.tavily.com/extract"


class TavilyExtract(BaseTool):
    """Extract and read content from URLs using Tavily API."""

    name: str = "webReader"
    description: str = (
        "Read and extract content from any URL. Returns the page content as text. "
        "Use this to read full articles, papers, or documentation pages."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to read and extract content from.",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    TAVILY_EXTRACT_URL,
                    headers={
                        "Authorization": f"Bearer {TAVILY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "urls": [url],
                        "extract_depth": "basic",
                    },
                )
                if resp.status_code != 200:
                    return self.fail_response(f"Tavily Extract error: {resp.status_code} {resp.text[:200]}")

                data = resp.json()
                results = data.get("results", [])
                failed = data.get("failed_results", [])

                if not results and failed:
                    return self.fail_response(f"Failed to extract: {failed[0]}")
                if not results:
                    return self.fail_response(f"No content extracted from: {url}")

                content = results[0].get("raw_content", "") or results[0].get("text", "")
                if not content:
                    return self.fail_response(f"Empty content from: {url}")

                return self.success_response(content[:8000])

        except httpx.TimeoutException:
            return self.fail_response(f"Extract timed out for: {url}")
        except Exception as e:
            return self.fail_response(f"Extract failed: {str(e)}")
