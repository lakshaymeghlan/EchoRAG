"""Upload the local index to a HuggingFace Dataset repo. Run once, locally.

    hf auth login
    python scripts/push_index.py your-username/echorag-index

Then set ECHORAG_INDEX_REPO to that same value in your Space's settings, and the
container will pull it at every boot (scripts/fetch_index.py).

A Dataset repo rather than the Space itself: Spaces are for code, and 723 MB of
LanceDB files in a Space repo makes every push slow.
"""

import os
import pathlib
import sys

# Same env var fetch_index.py and retrieve.py use, so `ECHORAG_INDEX_DIR=x`
# means one directory everywhere instead of three different defaults.
INDEX_DIR = pathlib.Path(os.environ.get("ECHORAG_INDEX_DIR", "index"))


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    repo_id = sys.argv[1]
    if "/" not in repo_id:
        print("error: repo must look like username/repo-name", file=sys.stderr)
        return 2

    if not (INDEX_DIR / "chunks.lance").is_dir():
        print(
            f"error: no index at {INDEX_DIR}/ — build one first:\n"
            "  python -m echorag.index --lang hin --rows 10000",
            file=sys.stderr,
        )
        return 1

    size_mb = sum(f.stat().st_size for f in INDEX_DIR.rglob("*") if f.is_file()) / 1e6
    print(f"uploading {INDEX_DIR}/ ({size_mb:.0f} MB) -> {repo_id}")

    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
    api.upload_folder(
        folder_path=str(INDEX_DIR),
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="index: 100k passages, hin shard",
    )

    print(f"\ndone. Now set this in your Space -> Settings -> Variables:\n")
    print(f"  ECHORAG_INDEX_REPO = {repo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
