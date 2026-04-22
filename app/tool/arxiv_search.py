import arxiv
import httpx
from app.tool.base import BaseTool, ToolResult

# Semantic Scholar API (free, no key needed)
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper"


async def _get_citation_count(arxiv_id: str) -> int | None:
    """Look up citation count from Semantic Scholar by ArXiv ID."""
    try:
        clean_id = arxiv_id.split("/")[-1].split("v")[0]
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_API}/ArXiv:{clean_id}",
                params={"fields": "citationCount,isOpenAccess"},
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("citationCount")
    except Exception:
        pass
    return None


class ArxivSearch(BaseTool):
    """Search ArXiv for academic papers with citation counts from Semantic Scholar."""

    name: str = "arxiv_search"
    description: str = (
        "Search ArXiv for academic papers. Returns titles, authors, abstracts, PDF links, "
        "and citation counts. Papers with higher citation counts are generally more reliable. "
        "NOTE: ArXiv is a preprint server without peer review. Treat results as references, "
        "not authoritative sources. Prefer papers with 10+ citations or published in conferences/journals."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query. Use keywords related to the modeling topic, e.g. 'linear programming optimization', 'regression analysis'. Field prefixes: ti: (title), abs: (abstract), cat: (category).",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of papers to return (default: 5, max: 15).",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Search ArXiv and return results sorted by citation count."""
        max_results = min(max_results, 15)

        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=arxiv.SortCriterion.Relevance,
            )

            papers = []
            client = arxiv.Client()
            for paper in client.results(search):
                authors = ", ".join(a.name for a in paper.authors[:3])
                if len(paper.authors) > 3:
                    authors += " et al."

                arxiv_id = paper.entry_id.split("/")[-1]
                citation_count = await _get_citation_count(arxiv_id)

                papers.append({
                    "title": paper.title,
                    "authors": authors,
                    "published": paper.published.strftime("%Y-%m-%d"),
                    "arxiv_id": paper.entry_id,
                    "categories": ", ".join(paper.categories),
                    "pdf_url": paper.pdf_url,
                    "abstract": paper.summary[:500] + ("..." if len(paper.summary) > 500 else ""),
                    "citations": citation_count,
                })

            if not papers:
                return ToolResult(output=f"No papers found for query: {query}")

            # Sort by citation count (None treated as 0), descending
            papers.sort(key=lambda p: p["citations"] or 0, reverse=True)

            # Format output
            results = []
            for p in papers:
                cite_str = f"{p['citations']} citations" if p["citations"] is not None else "citations: unknown"
                reliability = ""
                if p["citations"] is not None:
                    if p["citations"] >= 50:
                        reliability = " [HIGH RELIABILITY]"
                    elif p["citations"] >= 10:
                        reliability = " [MODERATE]"
                    else:
                        reliability = " [LOW - verify independently]"

                results.append(
                    f"Title: {p['title']}\n"
                    f"Authors: {p['authors']}\n"
                    f"Published: {p['published']} | {cite_str}{reliability}\n"
                    f"ArXiv ID: {p['arxiv_id']}\n"
                    f"Categories: {p['categories']}\n"
                    f"PDF: {p['pdf_url']}\n"
                    f"Abstract: {p['abstract']}"
                )

            output = f"Found {len(papers)} papers for '{query}' (sorted by citation count):\n\n"
            output += "\n\n---\n\n".join(results)
            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(error=f"ArXiv search failed: {str(e)}")
