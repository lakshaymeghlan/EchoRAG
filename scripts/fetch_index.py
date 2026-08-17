"""Download the prebuilt index at boot. Runs before uvicorn (see Dockerfile).

The index is 723 MB and gitignored, and HF Spaces disk is ephemeral — so it has
to arrive from somewhere on every cold start. Downloading a prebuilt copy takes
~1-2 min; rebuilding it would take 17.

    ECHORAG_INDEX_REPO=your-username/echorag-index

Exits 0 when the index is already present or absent-but-optional, so a missing
repo degrades to a clear /health error rather than a container that won't boot.
"""

import os
import pathlib
import shutil
import sys

INDEX_DIR = pathlib.Path(os.environ.get("ECHORAG_INDEX_DIR", "index"))
REPO = os.environ.get("ECHORAG_INDEX_REPO", "").strip()


def already_there() -> bool:
    return (INDEX_DIR / "chunks.lance").is_dir() and (INDEX_DIR / "passages.lance").is_dir()


def main() -> int:
    if already_there():
        print(f"[fetch_index] {INDEX_DIR} already present — skipping download")
        return 0

    if not REPO:
        print(
            "[fetch_index] ECHORAG_INDEX_REPO is not set and no local index exists.\n"
            "              The server will start but /health will report degraded.\n"
            "              Push an index with: python scripts/push_index.py <repo>",
            file=sys.stderr,
        )
        return 0

    from huggingface_hub import snapshot_download

    print(f"[fetch_index] downloading {REPO} -> {INDEX_DIR} …")
    local = snapshot_download(
        repo_id=REPO,
        repo_type="dataset",
        # A Space secret named HF_TOKEN covers private index repos.
        token=os.environ.get("HF_TOKEN") or None,
    )

    src = pathlib.Path(local)
    # Tolerate either layout: files at the repo root, or nested under index/.
    if not (src / "chunks.lance").exists() and (src / "index").is_dir():
        src = src / "index"

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name.startswith("."):
            continue
        dest = INDEX_DIR / item.name
        if dest.exists():
            continue
        # Copy rather than symlink: the HF cache may be on a different mount,
        # and LanceDB memory-maps these files.
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    print(f"[fetch_index] ready: {sorted(p.name for p in INDEX_DIR.iterdir())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
