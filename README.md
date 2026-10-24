# mcp-claude-agent

Private remote MCP server that gives Claude read/write access to GitHub.

## Env vars
- `GITHUB_TOKEN`: fine-grained PAT (Contents + Issues read/write, limited to chosen repos)
- `URL_SECRET`: long random string; the MCP endpoint is `/<URL_SECRET>/mcp`

Generate a secret: `python -c "import secrets;print(secrets.token_urlsafe(32))"`

## Run locally
```
pip install -r requirements.txt
python server.py
```

## Deploy (Render)
- Build: `pip install -r requirements.txt`
- Start: `python server.py`
- Set the two env vars

## Connect to Claude
Settings -> Connectors -> Add custom connector -> `https://<host>/<URL_SECRET>/mcp`

Treat the URL as a password. Never commit tokens or the secret.