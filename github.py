import re
import httpx

INCLUDE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".txt", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".yaml", ".yml", ".toml", ".json", ".html", ".css"}
EXCLUDE_DIRS = {"node_modules", "vendor", "dist", "build", ".git", "__pycache__", ".venv", "venv", ".next", "target"}
MAX_TOTAL_CHARS = 100_000
MAX_FILE_SIZE = 50_000


def parse_repo(url: str) -> tuple[str, str]:
    match = re.search(r"github\.com/([^/]+)/([^/\s?#]+)", url)
    if not match:
        raise ValueError(f"Could not parse GitHub repo from URL: {url}")
    return match.group(1), match.group(2).removesuffix(".git")


def get_repo_content(url: str) -> tuple[str, str]:
    owner, repo = parse_repo(url)
    tree = _fetch_tree(owner, repo)
    files = _filter_files(tree)

    chunks = []
    total = 0
    with httpx.Client(timeout=30) as client:
        for path in files:
            if total >= MAX_TOTAL_CHARS:
                break
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{path}"
            resp = client.get(raw_url)
            if resp.status_code != 200:
                continue
            content = resp.text
            if len(content) > MAX_FILE_SIZE:
                content = content[:MAX_FILE_SIZE] + "\n... (truncated)"
            chunks.append(f"=== {path} ===\n{content}")
            total += len(content)

    if not chunks:
        raise ValueError("No readable files found in repository")

    return "\n\n".join(chunks), f"{owner}/{repo}"


def _fetch_tree(owner: str, repo: str) -> list[dict]:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    resp = httpx.get(api_url, timeout=15)
    if resp.status_code == 404:
        raise ValueError(f"Repository not found: {owner}/{repo}")
    resp.raise_for_status()
    return resp.json().get("tree", [])


def _filter_files(tree: list[dict]) -> list[str]:
    paths = []
    for item in tree:
        if item.get("type") != "blob":
            continue
        path = item["path"]
        parts = path.split("/")
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext not in INCLUDE_EXTENSIONS:
            continue
        size = item.get("size", 0)
        if size > MAX_FILE_SIZE:
            continue
        paths.append(path)
    return paths
