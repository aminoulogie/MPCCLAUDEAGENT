import base64
import os

import httpx
from mcp.server.fastmcp import FastMCP

TOKEN = os.environ["GITHUB_TOKEN"]
SECRET = os.environ["URL_SECRET"]

mcp = FastMCP(
    "github-private",
    host="0.0.0.0",
    port=int(os.environ.get("PORT", 8000)),
    streamable_http_path=f"/{SECRET}/mcp",
    stateless_http=True,
)

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def gh(method, path, **kw):
    r = httpx.request(method, f"https://api.github.com{path}", headers=H, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


@mcp.tool()
def list_repos() -> list[str]:
    """List repos the token can access."""
    return [r["full_name"] for r in gh("GET", "/user/repos", params={"per_page": 100})]


@mcp.tool()
def read_path(repo: str, path: str = "", ref: str = "") -> str:
    """Read a file, or list a directory. repo is 'owner/name'."""
    data = gh("GET", f"/repos/{repo}/contents/{path}", params={"ref": ref} if ref else None)
    if isinstance(data, list):
        return "\n".join(f'{i["type"]}\t{i["path"]}' for i in data)
    return base64.b64decode(data["content"]).decode()


@mcp.tool()
def write_file(repo: str, path: str, content: str, message: str, branch: str = "") -> str:
    """Create or update a file with a commit. Returns the commit URL."""
    params = {"ref": branch} if branch else None
    body = {"message": message, "content": base64.b64encode(content.encode()).decode()}
    if branch:
        body["branch"] = branch
    try:
        body["sha"] = gh("GET", f"/repos/{repo}/contents/{path}", params=params)["sha"]
    except httpx.HTTPStatusError as e:
        if e.response.status_code != 404:
            raise
    return gh("PUT", f"/repos/{repo}/contents/{path}", json=body)["commit"]["html_url"]


@mcp.tool()
def list_issues(repo: str, state: str = "open") -> list[str]:
    """List issues in a repo."""
    return [
        f'#{i["number"]} {i["title"]}'
        for i in gh("GET", f"/repos/{repo}/issues", params={"state": state})
    ]


@mcp.tool()
def create_issue(repo: str, title: str, body: str = "") -> str:
    """Open a new issue. Returns its URL."""
    return gh("POST", f"/repos/{repo}/issues", json={"title": title, "body": body})["html_url"]


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
