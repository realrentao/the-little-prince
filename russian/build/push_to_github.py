# -*- coding: utf-8 -*-
# Push the Russian Little Prince reader into the-little-prince repo under /russian/.
# Git Data API strategy (resumable blob cache) — robust to flaky network / large repo.
import json, os, base64, time, traceback, urllib.request, urllib.error, ssl

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # little-prince-ru/
ROOT = os.path.expanduser(r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru")
mcp = os.path.expanduser(r"C:\Users\迪丽希斯\.workbuddy\mcp.json")
TOK = json.load(open(mcp, encoding="utf-8"))["mcpServers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"]
OWNER, REPO, BRANCH = "realrentao", "the-little-prince", "main"
SUB = "russian"                      # 目标子目录
CTX = ssl.create_default_context()

# 要排除的构建中间产物 / 日志
EXCLUDE_PREFIX = ("_",)
EXCLUDE_NAMES = {"parsed.json", "_shot_reader.png"}


def api(method, path, data=None, tries=8):
    url = f"https://api.github.com{path}"
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(url,
                data=json.dumps(data).encode() if data is not None else None,
                method=method,
                headers={"Authorization": f"token {TOK}", "Accept": "application/vnd.github+json",
                          "Content-Type": "application/json", "User-Agent": "workbuddy"})
            with urllib.request.urlopen(req, context=CTX) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            last = (e.code, body[:200])
            if e.code == 409 and "empty" in body:
                return e.code, json.loads(body or "{}")
            print(f"  HTTP {e.code} {path}: {body[:140]}")
        except Exception as e:
            last = (type(e).__name__, str(e)[:140])
            print(f"  net err {path}: {e} (retry {t+1})")
        time.sleep(2 + t)
    raise RuntimeError(f"api failed {path}: {last}")


def collect():
    out = []  # (local_rel, github_path, kind)
    # 顶层运行文件
    for fn in ["index.html", "app.js", "styles.css", "serve.py"]:
        out.append((fn, f"{SUB}/{fn}", "text"))
    # data/
    for fn in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if fn.endswith(".js") or fn.endswith(".json"):
            out.append((f"data/{fn}", f"{SUB}/data/{fn}", "text"))
    # audio/ mp3 + json
    for fn in sorted(os.listdir(os.path.join(ROOT, "audio"))):
        if fn.endswith(".mp3") or fn.endswith(".json"):
            out.append((f"audio/{fn}", f"{SUB}/audio/{fn}", "bin" if fn.endswith(".mp3") else "text"))
    # build/ 纯文本流水线（排除日志/临时）
    bdir = os.path.join(ROOT, "build")
    if os.path.isdir(bdir):
        for fn in sorted(os.listdir(bdir)):
            fp = os.path.join(bdir, fn)
            if not os.path.isfile(fp):
                continue
            if fn.startswith(EXCLUDE_PREFIX) or fn in EXCLUDE_NAMES:
                continue
            if fn.endswith(".py") or fn.endswith(".json") or fn.endswith(".txt"):
                kind = "text"
                out.append((f"build/{fn}", f"{SUB}/build/{fn}", kind))
    return out


def main():
    st, ref = api("GET", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}")
    if st != 200:
        raise RuntimeError(f"cannot get main ref: {ref}")
    parent_sha = ref["object"]["sha"]
    print("parent commit:", parent_sha[:10])

    files = collect()
    print(f"Total files to push: {len(files)}")

    cache_path = os.path.join(ROOT, "pushed_blobs.json")
    blob_cache = {}
    if os.path.exists(cache_path):
        try:
            blob_cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception:
            blob_cache = {}
    tree_items = []
    failed = []
    BLOB_BATCH = 15
    for bi in range(0, len(files), BLOB_BATCH):
        batch = files[bi:bi + BLOB_BATCH]
        for local_rel, gh_path, kind in batch:
            full = os.path.join(ROOT, local_rel)
            with open(full, "rb") as f:
                raw = f.read()
            if gh_path in blob_cache:
                tree_items.append({"path": gh_path, "mode": "100644", "type": "blob", "sha": blob_cache[gh_path]})
                continue
            if kind == "text":
                payload = {"content": raw.decode("utf-8"), "encoding": "utf-8"}
            else:
                payload = {"content": base64.b64encode(raw).decode(), "encoding": "base64"}
            try:
                st, blob = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs", payload)
            except Exception as e:
                print(f"  FAIL {gh_path}: {e}")
                failed.append(gh_path)
                continue
            if st != 201:
                print(f"  FAIL {gh_path}: {blob}")
                failed.append(gh_path)
                continue
            blob_cache[gh_path] = blob["sha"]
            tree_items.append({"path": gh_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        json.dump(blob_cache, open(cache_path, "w", encoding="utf-8"))
        print(f"  blobs {min(bi + BLOB_BATCH, len(files))}/{len(files)}  cached={len(blob_cache)} failed={len(failed)}")
    if failed:
        print(f"STOP: {len(failed)} blobs still failed; rerun to retry. Sample: {failed[:5]}")
        return
    print("all blobs ready")

    st, ptree = api("GET", f"/repos/{OWNER}/{REPO}/git/trees/{parent_sha}")
    base_tree = ptree.get("tree", [])
    existing = {t["path"]: t for t in base_tree}
    for it in tree_items:
        existing[it["path"]] = it
    merged_tree = list(existing.values())
    st, tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees", {"tree": merged_tree})
    if st != 201:
        raise RuntimeError(f"tree failed: {tree}")
    print("tree created:", tree["sha"][:10], "entries:", len(merged_tree))

    st, commit = api("POST", f"/repos/{OWNER}/{REPO}/git/commits",
                     {"message": "Add Russian Little Prince bilingual reader (russian/)",
                      "tree": tree["sha"], "parents": [parent_sha]})
    if st != 201:
        raise RuntimeError(f"commit failed: {commit}")
    print("commit created:", commit["sha"][:10])

    st, _ = api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}", {"sha": commit["sha"]})
    if st not in (200, 202):
        raise RuntimeError(f"ref update failed: {st}")
    print("ref updated ->", commit["sha"][:10])
    print("DONE. Final commit:", commit["sha"])


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
