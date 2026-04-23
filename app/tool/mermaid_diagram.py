import os
from pathlib import Path

from app.tool.base import BaseTool, ToolResult


class MermaidDiagram(BaseTool):
    """Generate diagrams (mind maps, flowcharts, etc.) using Mermaid syntax and render to PNG."""

    name: str = "mermaid_diagram"
    description: str = (
        "Create diagrams using Mermaid syntax. Supports mind maps, flowcharts, sequence diagrams, "
        "state diagrams, and more. Saves the diagram as PNG and the Mermaid source as .mmd file. "
        "Use this for: mind maps, architecture diagrams, workflow charts, model comparison diagrams."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Mermaid diagram code. Examples:\n"
                "Mind map: mindmap\\n  root((Topic))\\n    Subtopic 1\\n      Detail 1\\n    Subtopic 2\n"
                "Flowchart: flowchart TD\\n  A[Start] --> B{Decision}\\n  B -->|Yes| C[Action]\n",
            },
            "output_path": {
                "type": "string",
                "description": "Full path to save the diagram (without extension). "
                "E.g. /path/to/output/my_diagram",
            },
            "title": {
                "type": "string",
                "description": "Optional title/caption for the diagram.",
                "default": "",
            },
        },
        "required": ["code", "output_path"],
    }

    async def execute(self, code: str, output_path: str, title: str = "") -> ToolResult:
        try:
            base = Path(output_path)
            base.parent.mkdir(parents=True, exist_ok=True)

            # Save .mmd source
            mmd_path = base.with_suffix(".mmd")
            mmd_path.write_text(code)

            # Try to render PNG using mermaid-cli via npx
            png_path = base.with_suffix(".png")
            rendered = await self._render_with_npx(code, png_path)

            if not rendered:
                # Fallback: try rendering with a self-contained HTML + playwright
                rendered = await self._render_with_playwright(code, png_path, title)

            if rendered:
                return self.success_response(
                    f"Diagram saved:\n"
                    f"  PNG: {png_path}\n"
                    f"  Source: {mmd_path}\n"
                    f"  Size: {os.path.getsize(png_path)} bytes"
                )
            else:
                return self.success_response(
                    f"Mermaid source saved (rendering unavailable):\n"
                    f"  Source: {mmd_path}\n"
                    f"Install mermaid-cli (`npm install -g @mermaid-js/mermaid-cli`) for PNG rendering."
                )

        except Exception as e:
            return self.fail_response(f"Failed to create diagram: {str(e)}")

    async def _render_with_npx(self, code: str, png_path: Path) -> bool:
        """Try rendering with npx mermaid-cli."""
        import asyncio
        mmd_temp = png_path.with_suffix(".mmd")
        mmd_temp.write_text(code)
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "-y", "@mermaid-js/mermaid-cli",
                "-i", str(mmd_temp), "-o", str(png_path),
                "-w", "1600", "-b", "white",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0 and png_path.exists():
                return True
        except Exception:
            pass
        return False

    async def _render_with_playwright(self, code: str, png_path: Path, title: str) -> bool:
        """Fallback: render using headless browser + mermaid CDN."""
        try:
            from playwright.async_api import async_playwright

            title_html = f"<h3 style='font-family:sans-serif;text-align:center'>{title}</h3>" if title else ""
            html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>body {{ margin: 20px; background: white; }}</style>
</head><body>
{title_html}
<pre class="mermaid">{code}</pre>
<script>mermaid.initialize({{ startOnLoad: true, theme: 'default' }});</script>
</body></html>"""

            html_path = png_path.with_suffix(".html")
            html_path.write_text(html)

            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page(viewport={"width": 1600, "height": 1200})
                await page.goto(f"file://{html_path}")
                await page.wait_for_load_state("networkidle")
                # Wait for mermaid to render
                await page.wait_for_timeout(3000)
                # Find the mermaid SVG and screenshot it
                svg_el = await page.query_selector(".mermaid svg")
                if svg_el:
                    await svg_el.screenshot(path=str(png_path))
                else:
                    await page.screenshot(path=str(png_path), full_page=True)
                await browser.close()

            # Cleanup temp HTML
            html_path.unlink(missing_ok=True)
            return png_path.exists()

        except Exception:
            return False
