# -*- coding: utf-8 -*-
# Push the root navigation index.html into the-little-prince repo (root, not under russian/).
# Resumable Git Data API. parent = current main HEAD (after russian/ push).
import json, os, base64, time, traceback, urllib.request, urllib.error, ssl

ROOT = os.path.expanduser(r"D:\workbuddy工作区\2026-08-23-21-28-02\little-prince-ru")
NAV_LOCAL = os.path.join(ROOT, "_nav_index.html")
mcp = os.path.expanduser(r"C:\Users\迪丽希斯\.workbuddy\mcp.json")
TOK = json.load(open(mcp, encoding="utf-8"))["mcpServers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"]
OWNER, REPO, BRANCH = "realrentao", "the-little-prince", "main"
CTX = ssl.create_default_context()


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
            print(f"  HTTP {e.code} {path}: {body[:140]}")
        except Exception as e:
            last = (type(e).__name__, str(e)[:140])
            print(f"  net err {path}: {e} (retry {t+1})")
        time.sleep(2 + t)
    raise RuntimeError(f"api failed {path}: {last}")


def main():
    st, ref = api("GET", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}")
    parent_sha = ref["object"]["sha"]
    print("parent commit:", parent_sha[:10])

    with open(NAV_LOCAL, "rb") as f:
        raw = f.read()
    st, blob = api("POST", f"/repos/{OWNER}/{REPO}/git/blobs",
                   {"content": raw.decode("utf-8"), "encoding": "utf-8"})
    if st != 201:
        raise RuntimeError(f"blob failed: {blob}")
    print("nav blob:", blob["sha"][:10])

    st, ptree = api("GET", f"/repos/{OWNER}/{REPO}/git/trees/{parent_sha}")
    base_tree = ptree.get("tree", [])
    existing = {t["path"]: t for t in base_tree}
    existing["index.html"] = {"path": "index.html", "mode": "100644", "type": "blob", "sha": blob["sha"]}
    merged = list(existing.values())
    st, tree = api("POST", f"/repos/{OWNER}/{REPO}/git/trees", {"tree": merged})
    if st != 201:
        raise RuntimeError(f"tree failed: {tree}")
    print("tree:", tree["sha"][:10], "entries:", len(merged))

    st, commit = api("POST", f"/repos/{OWNER}/{REPO}/git/commits",
                     {"message": "Add multilingual navigation index.html", "tree": tree["sha"], "parents": [parent_sha]})
    if st != 201:
        raise RuntimeError(f"commit failed: {commit}")
    print("commit:", commit["sha"][:10])

    st, _ = api("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}", {"sha": commit["sha"]})
    if st not in (200, 202):
        raise RuntimeError(f"ref update failed: {st}")
    print("DONE. Final commit:", commit["sha"])


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
