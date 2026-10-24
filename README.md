# mcp-claude-agent

Remote MCP server that gives Claude read/write access to GitHub using a server-side GitHub token and a secret URL path.

The five tools are `list_repos`, `read_path`, `write_file`, `list_issues`, and `create_issue`.

## Configuration

Requires Python 3.10 or newer. The MCP SDK dependency is constrained to compatible 1.x releases that support the FastMCP HTTP settings used in `server.py`.

- `GITHUB_TOKEN`: a fine-grained GitHub personal access token limited to your chosen repositories. Grant Contents and Issues read/write permissions; Metadata read access is included automatically. Complete organization approval or SSO authorization if required.
- `URL_SECRET`: a long random URL-safe string. Generate one locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Use the generated value as a single path segment, without slashes.
- `PORT`: optional locally (default 8000); Render supplies it automatically.

Enter real values only in your shell or Render's dashboard. Never commit them. The complete connector URL grants access to the token's capabilities: treat it as a password.

## Run locally

On macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
GITHUB_TOKEN=dummy URL_SECRET=testsecret .venv/bin/python server.py
```

The server binds to `0.0.0.0:8000` and exposes `http://localhost:8000/testsecret/mcp`. Dummy credentials allow startup and MCP tool discovery; GitHub tool calls need a valid token.

While it is running, use a second terminal in the repository to initialize an MCP client and verify the endpoint and all five tool names:

```sh
.venv/bin/python - <<'PY'
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def check():
    async with streamablehttp_client("http://localhost:8000/testsecret/mcp") as (reader, writer, _):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            result = await session.list_tools()
            names = {tool.name for tool in result.tools}
            assert names == {"list_repos", "read_path", "write_file", "list_issues", "create_issue"}, names
            print("MCP endpoint ready:", ", ".join(sorted(names)))

asyncio.run(check())
PY
```

Stop the server with Ctrl-C. For actual GitHub use, export your real environment values in your shell before running `.venv/bin/python server.py`. The server reads process environment variables; creating a `.env` file alone does not configure it.

## Deploy to Render

1. Sign in at https://dashboard.render.com and connect your GitHub account. Give Render access to this repository.
2. Choose **New + -> Blueprint** and select this repository with branch **main**. Render reads `render.yaml` from the repository root.
3. Review the service: Python runtime, Free plan, build command `pip install -r requirements.txt`, start command `python server.py`.
4. Enter your real `GITHUB_TOKEN` and generated `URL_SECRET` in Render's environment-variable prompts/dashboard. Both are declared `sync: false`, so their values are not stored in the Blueprint file.
5. Apply/create the Blueprint and wait for the web service to become **Live**. Check its logs for successful Uvicorn startup. If you edit environment variables afterward, save and redeploy.
6. Copy the service's public hostname from Render, such as `your-service.onrender.com`. Your connector URL is exactly:

   `https://<host>/<URL_SECRET>/mcp`

   Replace both placeholders; do not include angle brackets. Use the same secret you entered in Render and no trailing slash.

If creating a web service manually instead, choose **New + -> Web Service**, connect the repository, select **main**, choose **Python 3** and **Free**, use the same build/start commands, and add both environment variables before deploying. Leave the root directory at the repository root.

Render supplies `PORT`; the server already listens on `0.0.0.0` and uses that port. No Python version override is required for Render's current Python runtime. Free services spin down when idle, so the first connector request can take longer; open the service in Render and retry after it wakes if needed. A browser GET to the MCP URL can show a protocol error because it is an MCP endpoint, not a web page.

## Add the connector in Claude

1. Open Claude on the web and go to **Settings -> Connectors**.
2. Choose **Add custom connector** (sometimes under **Add**), enter a name such as **GitHub private**, and paste `https://<host>/<URL_SECRET>/mcp` as the remote MCP server URL.
3. Leave OAuth/client credentials blank if advanced options are shown. This server uses the secret URL path; the GitHub token stays in Render.
4. Add the connector and connect/enable it. For an organization-managed Claude account, an owner/admin may need to add or allow the custom connector first.
5. Enable the connector in a conversation's tools/connectors menu. Ask Claude to list the available GitHub repositories to verify a real GitHub request. The connector should expose all five tools listed above.

Do not paste the GitHub token into Claude or share the connector URL. If you rotate `URL_SECRET` in Render, redeploy and update the URL in Claude.
