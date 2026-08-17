"""Download the prebuilt index at boot. Runs before uvicorn (see Dockerfile).

The index is gitignored and container disks are ephemeral, so it has to arrive
from somewhere on every cold start. Downloading a prebuilt copy takes seconds;
rebuilding it would take minutes.

    ECHORAG_INDEX_REPO=your-username/echorag-index-small

The actual work lives in retrieve.ensure_index(), because serverless hosts have
no startup command and the app has to be able to fetch its own index there.
This stays as the container entry point.

Always exits 0: a missing index degrades to a clear /health error rather than a
container that won't boot.
"""

from echorag import retrieve


def main() -> int:
    if retrieve.index_present():
        print(f"[fetch_index] {retrieve.INDEX_DIR} already present — skipping download")
        return 0

    print(f"[fetch_index] fetching into {retrieve.INDEX_DIR} …")
    if retrieve.ensure_index():
        print("[fetch_index] ready")
    else:
        print(
            "[fetch_index] no index and nothing to fetch — the server will start "
            "but /health will report degraded.\n"
            "              Push one with: python scripts/push_index.py <repo>"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
