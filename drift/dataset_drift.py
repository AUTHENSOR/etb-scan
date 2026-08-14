#!/usr/bin/env python3
"""
Dataset drift measurement (ETB-24 empirical arm).

For each eval dataset id: fetch commit history of `main`, take the OLDEST and
NEWEST commits, fetch the file tree at both, and diff LFS OIDs of data files.
Drift = the benchmark's bytes changed while scores kept being quoted against
the dataset name. No data is downloaded — OID comparison only.

  python dataset_drift.py
Output: drift/results.jsonl + printed summary table.
"""
import json
import time
import urllib.request
import urllib.error
from pathlib import Path

OUT = Path(__file__).parent / "results.jsonl"
DATA_EXT = (".parquet", ".jsonl", ".json", ".csv", ".arrow", ".tsv", ".txt", ".zip")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "etb-drift-study"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                return {"__error__": e.code}
            if e.code == 429:
                time.sleep(15)
                continue
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {"__error__": "unreachable"}


def tree(ds, rev):
    t = get(f"https://huggingface.co/api/datasets/{ds}/tree/{rev}?recursive=true")
    if isinstance(t, dict):
        return t
    out = {}
    for f in t:
        if f.get("type") == "file":
            oid = f.get("lfs", {}).get("oid") or f.get("oid")
            out[f["path"]] = oid
    return out


def main(ds_ids):
    for ds in ds_ids:
        rec = {"dataset": ds}
        commits = get(f"https://huggingface.co/api/datasets/{ds}/commits/main?limit=200")
        if isinstance(commits, dict):
            rec["error"] = commits["__error__"]
        elif not commits:
            rec["error"] = "no_commits"
        else:
            rec["n_commits"] = len(commits)
            newest, oldest = commits[0], commits[-1]
            rec["newest_date"] = newest["date"][:10]
            rec["oldest_date"] = oldest["date"][:10]
            rec["newest_title"] = newest.get("title", "")[:80]
            t_new, t_old = tree(ds, newest["id"]), tree(ds, oldest["id"])
            if isinstance(t_new, dict) and "__error__" not in t_new and isinstance(t_old, dict) and "__error__" not in t_old:
                data_new = {p: o for p, o in t_new.items() if p.lower().endswith(DATA_EXT)}
                data_old = {p: o for p, o in t_old.items() if p.lower().endswith(DATA_EXT)}
                changed = sorted(p for p in data_new.keys() & data_old.keys() if data_new[p] != data_old[p])
                added = sorted(data_new.keys() - data_old.keys())
                removed = sorted(data_old.keys() - data_new.keys())
                rec.update({
                    "data_files_now": len(data_new),
                    "changed": changed, "added": added, "removed": removed,
                    "drifted": bool(changed or added or removed),
                })
            else:
                rec["error"] = "tree_fetch_failed"
        with OUT.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        d = rec.get("drifted")
        print(f"{ds:55s} commits={rec.get('n_commits','?'):>4} "
              f"{rec.get('oldest_date','?')} -> {rec.get('newest_date','?')} "
              f"{'DRIFTED' if d else ('ok' if d is False else rec.get('error'))}", flush=True)
        time.sleep(1.0)


if __name__ == "__main__":
    import sys
    ids = [l.strip() for l in open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/hf_d3.txt") if l.strip()]
    done = set()
    if OUT.exists():
        done = {json.loads(l)["dataset"] for l in OUT.read_text().splitlines() if l.strip()}
    main([d for d in ids if d not in done])
