"""Generate ≥40 per-tool MCP schemas under templates/mcp-servers."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "templates" / "mcp-servers"

TOOLS = [
    ("github", "github.list_issues", "GitHub List Issues", "List issues for a GitHub repository by owner/name, state, and limit.", {"repo": "owner/name", "state": "open|closed|all", "limit": "max issues"}, ["list github issues", "open issues in repo"]),
    ("github", "github.search_code", "GitHub Search Code", "Search code across GitHub or scoped to one repository.", {"query": "search terms", "repo": "optional owner/name", "limit": "max results"}, ["search github code", "find code on github"]),
    ("github", "github.get_repo", "GitHub Get Repo", "Fetch repository metadata including stars, license, and default branch.", {"repo": "owner/name"}, ["get github repo info", "repo stars"]),
    ("github", "github.list_pull_requests", "GitHub List Pull Requests", "List pull requests for a repository filtered by state.", {"repo": "owner/name", "state": "open|closed|all", "limit": "max PRs"}, ["list pull requests", "open PRs"]),
    ("github", "github.create_issue", "GitHub Create Issue", "Create a new GitHub issue with title and body.", {"repo": "owner/name", "title": "issue title", "body": "issue body"}, ["create github issue", "file a bug"]),
    ("github", "github.get_file", "GitHub Get File Contents", "Read file contents from a repository path at a ref.", {"repo": "owner/name", "path": "file path", "ref": "branch or sha"}, ["read github file", "get repo file contents"]),
    ("github", "github.list_commits", "GitHub List Commits", "List recent commits on a branch.", {"repo": "owner/name", "sha": "branch", "limit": "max commits"}, ["list commits", "git history"]),
    ("github", "github.search_issues", "GitHub Search Issues", "Search issues and PRs with GitHub search syntax.", {"query": "search query", "limit": "max results"}, ["search github issues", "find bugs"]),
    ("slack", "slack.post_message", "Slack Post Message", "Post a message to a Slack channel.", {"channel": "channel id or name", "text": "message body"}, ["send slack message", "post to channel"]),
    ("slack", "slack.list_channels", "Slack List Channels", "List Slack channels the bot can access.", {"limit": "max channels"}, ["list slack channels"]),
    ("slack", "slack.get_user", "Slack Get User", "Look up a Slack user by id or email.", {"user": "user id or email"}, ["find slack user"]),
    ("slack", "slack.add_reaction", "Slack Add Reaction", "Add an emoji reaction to a Slack message.", {"channel": "channel", "timestamp": "message ts", "emoji": "emoji name"}, ["react on slack"]),
    ("slack", "slack.upload_file", "Slack Upload File", "Upload a file to a Slack channel.", {"channel": "channel", "path": "local path", "title": "file title"}, ["upload file to slack"]),
    ("slack", "slack.search_messages", "Slack Search Messages", "Search message history across Slack.", {"query": "search text", "limit": "max results"}, ["search slack messages"]),
    ("slack", "slack.set_topic", "Slack Set Channel Topic", "Update the topic string for a Slack channel.", {"channel": "channel", "topic": "new topic"}, ["set slack topic"]),
    ("postgres", "postgres.query", "Postgres Query", "Run a read-only SQL SELECT against Postgres.", {"sql": "SELECT statement", "limit": "row limit"}, ["query postgres", "run sql select"]),
    ("postgres", "postgres.execute", "Postgres Execute", "Execute a mutating SQL statement (INSERT/UPDATE/DELETE).", {"sql": "SQL statement"}, ["execute sql", "update postgres"]),
    ("postgres", "postgres.list_tables", "Postgres List Tables", "List tables in a schema.", {"schema": "schema name"}, ["list postgres tables"]),
    ("postgres", "postgres.describe_table", "Postgres Describe Table", "Describe columns and types for a table.", {"table": "table name", "schema": "schema"}, ["describe table schema"]),
    ("postgres", "postgres.insert_row", "Postgres Insert Row", "Insert a row into a table from a JSON object.", {"table": "table", "row": "json object"}, ["insert into postgres"]),
    ("postgres", "postgres.create_index", "Postgres Create Index", "Create an index on table columns.", {"table": "table", "columns": "comma-separated", "unique": "bool"}, ["create postgres index"]),
    ("postgres", "postgres.explain", "Postgres Explain Plan", "Return EXPLAIN plan for a SQL query.", {"sql": "SQL"}, ["explain sql plan"]),
    ("s3", "s3.put_object", "S3 Put Object", "Upload an object to an S3 bucket key.", {"bucket": "bucket", "key": "object key", "path": "local file"}, ["upload to s3", "put object storage"]),
    ("s3", "s3.get_object", "S3 Get Object", "Download an object from S3 to a local path.", {"bucket": "bucket", "key": "object key", "path": "local dest"}, ["download from s3"]),
    ("s3", "s3.list_objects", "S3 List Objects", "List objects under a prefix in a bucket.", {"bucket": "bucket", "prefix": "key prefix", "limit": "max keys"}, ["list s3 objects"]),
    ("s3", "s3.delete_object", "S3 Delete Object", "Delete an object from a bucket.", {"bucket": "bucket", "key": "object key"}, ["delete s3 object"]),
    ("s3", "s3.presign_url", "S3 Presign URL", "Create a time-limited presigned URL for an object.", {"bucket": "bucket", "key": "key", "expires_s": "seconds"}, ["presigned s3 url"]),
    ("s3", "s3.copy_object", "S3 Copy Object", "Copy an object between buckets or keys.", {"src_bucket": "src", "src_key": "src key", "dst_bucket": "dst", "dst_key": "dst key"}, ["copy s3 object"]),
    ("s3", "s3.head_object", "S3 Head Object", "Fetch object metadata without downloading body.", {"bucket": "bucket", "key": "key"}, ["s3 object metadata"]),
    ("browser", "browser.navigate", "Browser Navigate", "Open a URL in a headless browser and wait for load.", {"url": "https url"}, ["open webpage", "navigate browser"]),
    ("browser", "browser.snapshot", "Browser Snapshot", "Capture accessibility/text snapshot of the current page.", {}, ["page snapshot", "browser text"]),
    ("browser", "browser.click", "Browser Click", "Click an element by CSS selector or role.", {"selector": "css or role"}, ["click button in browser"]),
    ("browser", "browser.type_text", "Browser Type Text", "Type text into an input field.", {"selector": "input selector", "text": "value"}, ["type into form"]),
    ("browser", "browser.screenshot", "Browser Screenshot", "Take a PNG screenshot of the page or element.", {"selector": "optional", "path": "output path"}, ["screenshot webpage"]),
    ("browser", "browser.extract_links", "Browser Extract Links", "Extract hyperlinks from the current page.", {"limit": "max links"}, ["extract page links"]),
    ("web-search", "web.search", "Web Search", "Search the public web and return ranked results.", {"query": "search query", "limit": "max results"}, ["search the web", "google-like search"]),
    ("web-search", "web.news", "Web News Search", "Search recent news articles for a topic.", {"query": "topic", "limit": "max articles"}, ["search news"]),
    ("web-search", "web.fetch_url", "Web Fetch URL", "Fetch and extract main text content from a URL.", {"url": "https url"}, ["fetch webpage content"]),
    ("web-search", "web.images", "Web Image Search", "Search for images matching a query.", {"query": "image query", "limit": "max images"}, ["search images"]),
    ("web-search", "web.scholar", "Web Scholar Search", "Search scholarly papers and citations.", {"query": "paper topic", "limit": "max papers"}, ["search academic papers"]),
]


def main() -> None:
    assert len(TOOLS) >= 40, len(TOOLS)
    for meta in ROOT.rglob("okf-metadata.yaml"):
        dest = meta.with_name("okf-server-info.yaml")
        if not dest.exists():
            meta.rename(dest)
            print(f"renamed {meta} -> {dest}")

    for server, tid, name, desc, params, examples in TOOLS:
        d = ROOT / server / "tools"
        d.mkdir(parents=True, exist_ok=True)
        data = {
            "id": tid,
            "name": name,
            "description": desc,
            "namespace": server,
            "category": server,
            "tags": [server, "mcp"],
            "params": params,
            "example_prompts": examples,
            "capabilities": [server, "mcp"],
            "endpoint": f"mcp://{server}/{tid.split('.', 1)[-1]}",
            "input_schema": {
                "type": "object",
                "properties": {k: {"type": "string", "description": v} for k, v in params.items()},
            },
            "output_schema": {"type": "object"},
        }
        path = d / f"{tid.split('.', 1)[-1]}.tool.yaml"
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    from neuroswarm_arm.runtime.router.registry_loader import RegistryLoader

    loaded = RegistryLoader().load_path(ROOT)
    print("generated", len(TOOLS), "files; loaded", len(loaded))


if __name__ == "__main__":
    main()
