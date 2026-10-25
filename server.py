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

MAX_LINES = 400
MAX_MATCHES = 60


def gh(method, path, **kw):
    r = httpx.request(method, f"https://api.github.com{path}", headers=H, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def gh_text(path, params=None):
    """Fetch raw file text (works for files over 1 MB too)."""
    headers = {**H, "Accept": "application/vnd.github.raw+json"}
    r = httpx.get(f"https://api.github.com{path}", headers=headers, params=params, timeout=60)
    r.raise_for_status()
    return r.text


@mcp.tool()
def list_repos() -> list[str]:
    """List repos the token can access."""
    return [r["full_name"] for r in gh("GET", "/user/repos", params={"per_page": 100})]


@mcp.tool()
def read_path(repo: str, path: str = "", ref: str = "") -> str:
    """Read a file, or list a directory. repo is 'owner/name'. For big files use read_lines."""
    data = gh("GET", f"/repos/{repo}/contents/{path}", params={"ref": ref} if ref else None)
    if isinstance(data, list):
        return "\n".join(f'{i["type"]}\t{i["path"]}' for i in data)
    return base64.b64decode(data["content"]).decode()


@mcp.tool()
def read_lines(repo: str, path: str, start: int = 1, end: int = 200, ref: str = "") -> str:
    """Read a line range of a file (max 400 lines per call), with line numbers."""
    text = gh_text(f"/repos/{repo}/contents/{path}", {"ref": ref} if ref else None)
    lines = text.splitlines()
    total = len(lines)
    start = max(1, start)
    end = min(total, end, start + MAX_LINES - 1)
    if start > total:
        return f"{path} has only {total} lines."
    body = "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, end + 1))
    return f"[{path} lines {start}-{end} of {total}]\n{body}"


@mcp.tool()
def search_in_file(repo: str, path: str, query: str, ref: str = "") -> str:
    """Find lines containing text (case-insensitive) in one file. Returns line numbers."""
    text = gh_text(f"/repos/{repo}/contents/{path}", {"ref": ref} if ref else None)
    q = query.lower()
    hits = [f"{n}: {line.strip()[:200]}" for n, line in enumerate(text.splitlines(), 1) if q in line.lower()]
    if not hits:
        return "No matches."
    extra = f"\n...and {len(hits) - MAX_MATCHES} more" if len(hits) > MAX_MATCHES else ""
    return "\n".join(hits[:MAX_MATCHES]) + extra


@mcp.tool()
def create_branch(repo: str, branch: str, from_branch: str = "main") -> str:
    """Create a new branch from an existing one."""
    sha = gh("GET", f"/repos/{repo}/git/ref/heads/{from_branch}")["object"]["sha"]
    gh("POST", f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
    return f"Created {branch} from {from_branch} at {sha[:7]}"


@mcp.tool()
def write_file(repo: str, path: str, content: str, message: str, branch: str = "") -> str:
    """Create or update a whole file with a commit. Returns the commit URL."""
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
def replace_in_file(repo: str, path: str, old: str, new: str, message: str, branch: str = "") -> str:
    """Safe small edit: replace exact text that appears exactly once. Returns the commit URL."""
    params = {"ref": branch} if branch else None
    text = gh_text(f"/repos/{repo}/contents/{path}", params)
    count = text.count(old)
    if count != 1:
        return f"Aborted: old text found {count} times (need exactly 1). Nothing changed."
    sha = gh("GET", f"/repos/{repo}/contents/{path}", params=params)["sha"]
    body = {
        "message": message,
        "content": base64.b64encode(text.replace(old, new, 1).encode()).decode(),
        "sha": sha,
    }
    if branch:
        body["branch"] = branch
    return gh("PUT", f"/repos/{repo}/contents/{path}", json=body)["commit"]["html_url"]


@mcp.tool()
def create_pull_request(repo: str, head: str, base: str, title: str, body: str = "") -> str:
    """Open a pull request from head into base. Returns its URL."""
    return gh("POST", f"/repos/{repo}/pulls", json={"title": title, "head": head, "base": base, "body": body})["html_url"]


@mcp.tool()
def run_workflow(repo: str, workflow: str, ref: str) -> str:
    """Start a workflow_dispatch run. workflow is the file name (e.g. ios.yml), ref is the branch."""
    r = httpx.post(
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches",
        headers=H,
        json={"ref": ref},
        timeout=30,
    )
    r.raise_for_status()
    return f"Started {workflow} on {ref}"


@mcp.tool()
def list_workflow_runs(repo: str, branch: str = "") -> list[str]:
    """Latest workflow runs: id, name, status/conclusion and link."""
    params = {"per_page": 5}
    if branch:
        params["branch"] = branch
    runs = gh("GET", f"/repos/{repo}/actions/runs", params=params)["workflow_runs"]
    return [
        f'{r["id"]} {r["name"]} v1.0.{r["run_number"]} {r["status"]}/{r["conclusion"]} branch={r["head_branch"]} sha={r["head_sha"][:7]} {r["html_url"]}'
        for r in runs
    ]


@mcp.tool()
def get_run_failure(repo: str, run_id: int, tail: int = 80) -> str:
    """For a workflow run: branch, commit, which job and step failed, and the last log lines of each failed job."""
    run = gh("GET", f"/repos/{repo}/actions/runs/{run_id}")
    jobs = gh("GET", f"/repos/{repo}/actions/runs/{run_id}/jobs", params={"per_page": 50})["jobs"]
    commit = ((run.get("head_commit") or {}).get("message") or "").splitlines()[:1]
    out = [f'Run {run_id}: branch {run["head_branch"]}, commit {run["head_sha"][:7]} {commit[0][:100] if commit else ""}']
    failed = [j for j in jobs if j["conclusion"] == "failure"]
    if not failed:
        out.append("No failed jobs. " + ", ".join(f'{j["name"]}={j["conclusion"]}' for j in jobs))
        for j in jobs:
            out.append(f'{j["name"]} steps: ' + "; ".join(f'{s["name"]}={s["conclusion"]}' for s in j["steps"]))
        out.append(f'run_number={run["run_number"]} event={run["event"]} tag=v1.0.{run["run_number"]}')
    for j in failed:
        steps = [s["name"] for s in j["steps"] if s["conclusion"] == "failure"]
        out.append(f'\nJob "{j["name"]}" failed at step: {", ".join(steps) or "unknown"}')
        r = httpx.get(
            f'https://api.github.com/repos/{repo}/actions/jobs/{j["id"]}/logs',
            headers=H,
            timeout=60,
            follow_redirects=True,
        )
        if r.status_code != 200:
            out.append(f"(could not fetch log: HTTP {r.status_code})")
            out.append(f'job status={j["status"]} runner={j.get("runner_name")} started={j.get("started_at")} completed={j.get("completed_at")}')
            out.append("steps: " + (", ".join(f'{s["name"]}={s["conclusion"]}' for s in j["steps"]) or "none ran"))
            try:
                notes = gh("GET", f'/repos/{repo}/check-runs/{j["id"]}/annotations')
                for n in notes[:10]:
                    out.append(f'annotation [{n.get("annotation_level")}]: {(n.get("message") or "")[:500]}')
            except httpx.HTTPStatusError as e:
                resp = e.response
                needed = resp.headers.get("x-accepted-github-permissions", "")
                out.append(f"(could not read annotations: HTTP {resp.status_code} {resp.text[:300]})")
                if resp.status_code in (401, 403):
                    out.append(
                        "The GITHUB_TOKEN on Render needs 'Checks: Read' (fine-grained token) or the 'repo' scope (classic token)"
                        + (f"; GitHub says it accepts: {needed}" if needed else "")
                        + "."
                    )
            except Exception as e:
                out.append(f"(could not read annotations: {e})")
            if not j.get("runner_name") and not j.get("steps"):
                out.append("This job never got a runner, so there are no logs. Check Actions billing/spending limit and runner availability for the repo.")
            continue
        lines = [l.split(" ", 1)[-1][:300] if l[:2] == "20" else l[:300] for l in r.text.splitlines()]
        out.append("\n".join(lines[-max(10, min(tail, 300)):]))
    return "\n".join(out)


@mcp.tool()
def merge_branch(repo: str, base: str, head: str, message: str = "") -> str:
    """Merge branch head into branch base with a merge commit (no pull request). Reports conflicts instead of failing."""
    body = {"base": base, "head": head}
    if message:
        body["commit_message"] = message
    r = httpx.post(f"https://api.github.com/repos/{repo}/merges", headers=H, json=body, timeout=60)
    if r.status_code == 201:
        return f"Merged {head} into {base}: {r.json()['html_url']}"
    if r.status_code == 204:
        return f"Nothing to merge: {base} already contains {head}."
    if r.status_code == 409:
        return f"Merge conflict between {head} and {base}. Nothing changed."
    return f"Merge failed ({r.status_code}): {r.text[:300]}"


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
