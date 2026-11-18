#!/usr/bin/env python3
"""
Refresh index.html with how much of the Willennar Genealogy Center's
PastPerfect catalog (willennar.catalogaccess.com) is on archive.org.

    python3 update_site.py            # normal run (what the GitHub Action runs)
    python3 update_site.py --force    # publish a result the safety check refused (read why first)

Where the numbers come from
---------------------------
- Uploaded: archive.org search for items that carry the catalog mirror's own
  fields (pp_mirror_version) and contributor "Willennar Genealogy Center".
  No uploader email is used, so none ends up in this public repo.
  An item in LIVE_COLLECTION counts as "on archive.org"; one in
  TEST_COLLECTION counts as a test upload. archive.org deletes test_collection
  items after about 30 days, so test numbers are expected to fall on their own.
- Catalog totals: COUNTS_PATH, written and pushed by the harvester after each
  harvest (see HARVESTER_HANDOFF.md). This script only reads it. Until it
  exists, totals show as unknown and the page still shows uploads.

Records are counted once each, keyed by record type + PastPerfect id, so a
record uploaded twice (or to both collections) is not double-counted.

Everything in index.html outside the single-line `const DATA = {...};` and
`const SNAPSHOT_DATE = "...";` statements is left untouched.
"""

import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

# ============================== CONFIG ======================================
SITE_PATH = "index.html"
COUNTS_PATH = "willennar_catalog_counts.json"
QUERY = 'pp_mirror_version:* AND contributor:"Willennar Genealogy Center"'
LIVE_COLLECTION = "eckhartpubliclibrary"
TEST_COLLECTION = "test_collection"
RECORD_TYPES = ("photos", "library", "objects", "archives")
NO_COLLECTION = "(no catalog collection)"
WEEKS_SHOWN = 12
RECENT_SHOWN = 10
COUNTS_STALE_DAYS = 45            # flag catalog totals older than this
MAX_LIVE_SHRINK_PCT = 40          # refuse to publish if live records drop more than this
USER_AGENT = "willennar-site-update/1.0"
SCRAPE_URL = "https://archive.org/services/search/v1/scrape"
FIELDS = "identifier,title,collection,pp_collection,pp_record_type,pp_id,addeddate"
# =============================================================================


def http_get_json(url, retries=5):
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == retries - 1:
                raise
            wait = e.headers.get("Retry-After")
            time.sleep(float(wait) if wait and wait.isdigit() else delay + random.random())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(delay + random.random())
        delay *= 2


def fetch_items():
    items, cursor = [], None
    while True:
        params = {"q": QUERY, "fields": FIELDS, "count": "10000"}
        if cursor:
            params["cursor"] = cursor
        data = http_get_json(SCRAPE_URL + "?" + urllib.parse.urlencode(params))
        page = data.get("items", [])
        items.extend(page)
        cursor = data.get("cursor")
        if not cursor or not page:
            return items


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def first(v):
    v = as_list(v)
    return v[0] if v else None


def load_counts():
    """{"counted": "YYYY-MM-DD", "collections": {name: {"total": N, "photos": n, ...}}}"""
    try:
        with open(COUNTS_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"REFUSING TO WRITE -- {COUNTS_PATH} is not valid JSON ({e}). Nothing was changed.")
        sys.exit(1)
    cols = raw.get("collections")
    if not isinstance(cols, dict):
        print(f"REFUSING TO WRITE -- {COUNTS_PATH} has no 'collections' object. Nothing was changed.")
        sys.exit(1)
    for name, c in cols.items():
        if not isinstance(c, dict) or not isinstance(c.get("total"), int) or c["total"] < 0:
            print(f"REFUSING TO WRITE -- {COUNTS_PATH}: '{name}' needs a whole-number 'total'. Nothing was changed.")
            sys.exit(1)
    return raw


def build_data(items, counts):
    now = datetime.now(timezone.utc)
    cols = defaultdict(lambda: {"live": set(), "test": set(), "live_by_type": defaultdict(set),
                                "last_upload": None})
    live_all, test_all = set(), set()
    recent = []
    week_start = (now - timedelta(days=now.weekday())).date()
    weeks = [week_start - timedelta(weeks=i) for i in range(WEEKS_SHOWN - 1, -1, -1)]
    weekly = {w.isoformat(): {"live": 0, "test": 0} for w in weeks}

    for it in items:
        name = first(it.get("pp_collection")) or NO_COLLECTION
        rtype = (first(it.get("pp_record_type")) or "").lower()
        pid = first(it.get("pp_id"))
        key = f"{rtype}/{pid}" if pid else it["identifier"]
        in_live = LIVE_COLLECTION in as_list(it.get("collection"))
        in_test = TEST_COLLECTION in as_list(it.get("collection"))
        if not (in_live or in_test):
            continue
        c = cols[name]
        added = it.get("addeddate") or ""
        if in_live:
            c["live"].add(key)
            c["live_by_type"][rtype or "other"].add(key)
            live_all.add(key)
        if in_test:
            c["test"].add(key)
            test_all.add(key)
        if added and (c["last_upload"] is None or added > c["last_upload"]):
            c["last_upload"] = added
        if added:
            d = datetime.strptime(added[:10], "%Y-%m-%d").date()
            wk = (d - timedelta(days=d.weekday())).isoformat()
            if wk in weekly:
                weekly[wk]["live" if in_live else "test"] += 1
        recent.append({
            "identifier": it["identifier"],
            "title": first(it.get("title")) or it["identifier"],
            "collection": name,
            "where": "live" if in_live else "test",
            "added": added[:10],
        })

    catalog = (counts or {}).get("collections", {})
    names = set(cols) | set(catalog)
    rows = []
    for name in names:
        c = cols.get(name)
        cat = catalog.get(name)
        total = cat["total"] if cat else None
        live = len(c["live"]) if c else 0
        rows.append({
            "name": name,
            "total": total,
            "total_by_type": {t: cat[t] for t in RECORD_TYPES if cat and isinstance(cat.get(t), int)},
            "live": live,
            "live_by_type": {t: len(v) for t, v in c["live_by_type"].items()} if c else {},
            "test": len(c["test"]) if c else 0,
            "last_upload": (c["last_upload"] or "")[:10] if c else None,
        })

    def state(r):
        if r["total"] is not None and r["total"] > 0 and r["live"] >= r["total"]:
            return "complete"
        if r["live"] or r["test"]:
            return "in_progress"
        return "not_started"

    for r in rows:
        r["state"] = state(r)

    in_progress = sorted([r for r in rows if r["state"] == "in_progress"],
                         key=lambda r: r["last_upload"] or "", reverse=True)
    complete = sorted([r for r in rows if r["state"] == "complete"], key=lambda r: r["name"].lower())
    not_started = sorted([r for r in rows if r["state"] == "not_started"], key=lambda r: r["name"].lower())

    recent.sort(key=lambda r: r["added"], reverse=True)
    counted = (counts or {}).get("counted")
    stale = False
    if counted:
        try:
            stale = (date.today() - date.fromisoformat(counted)).days > COUNTS_STALE_DAYS
        except ValueError:
            stale = True

    catalog_total = sum(c["total"] for c in catalog.values()) if catalog else None
    return {
        "catalog_total": catalog_total,
        "catalog_counted": counted,
        "catalog_stale": stale,
        "collection_count": len(catalog) if catalog else len([n for n in cols if n != NO_COLLECTION]),
        "live_records": len(live_all),
        "test_records": len(test_all),
        "in_progress": in_progress,
        "complete": complete,
        "not_started": not_started,
        "weekly": [{"week": k, **v} for k, v in weekly.items()],
        "recent": recent[:RECENT_SHOWN],
        "live_collection": LIVE_COLLECTION,
        "test_collection": TEST_COLLECTION,
    }


def previous_data(html):
    m = re.search(r"^const DATA = (\{.*\});$", html, re.M)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def sanity_check(prev, data, force):
    problems = []
    if prev and prev.get("live_records"):
        drop = 100.0 * (prev["live_records"] - data["live_records"]) / prev["live_records"]
        if drop > MAX_LIVE_SHRINK_PCT:
            problems.append(f"records on archive.org fell {drop:.0f}% "
                            f"({prev['live_records']:,} -> {data['live_records']:,}), "
                            f"more than the {MAX_LIVE_SHRINK_PCT}% limit -- archive.org search may be having trouble")
    if not problems:
        return True
    print("\nREFUSING TO WRITE -- the new data does not look plausible:")
    for p in problems:
        print(f"  - {p}")
    if force:
        print("  (--force given: writing it anyway)")
        return True
    print("Nothing was changed. If this is real (e.g. items were deliberately removed), re-run with --force.")
    return False


def inject(html, data, snapshot):
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    new, n1 = re.subn(r"^const DATA = .*;$", lambda _: f"const DATA = {payload};", html, count=1, flags=re.M)
    new, n2 = re.subn(r'^const SNAPSHOT_DATE = ".*";$', lambda _: f'const SNAPSHOT_DATE = "{snapshot}";',
                      new, count=1, flags=re.M)
    if n1 != 1 or n2 != 1:
        print(f"REFUSING TO WRITE -- could not find the DATA / SNAPSHOT_DATE lines in {SITE_PATH}.")
        sys.exit(1)
    return new


def main():
    with open(SITE_PATH, encoding="utf-8") as f:
        html = f.read()
    counts = load_counts()
    print(f"Searching archive.org: {QUERY}")
    items = fetch_items()
    print(f"  {len(items):,} item(s) found")
    data = build_data(items, counts)
    if not sanity_check(previous_data(html), data, "--force" in sys.argv):
        sys.exit(1)
    snapshot = date.today().strftime("%B %-d, %Y")
    with open(SITE_PATH, "w", encoding="utf-8") as f:
        f.write(inject(html, data, snapshot))

    print("\nDone. Page updated:")
    total = data["catalog_total"]
    print(f"  Records on archive.org ({LIVE_COLLECTION}): {data['live_records']:,}"
          + (f" of {total:,} in the catalog" if total is not None else " (catalog totals not provided yet)"))
    print(f"  Test uploads ({TEST_COLLECTION}): {data['test_records']:,}")
    print(f"  Collections: {len(data['in_progress'])} in progress, {len(data['complete'])} complete, "
          f"{len(data['not_started'])} not started")
    for r in data["in_progress"]:
        tot = f"{r['total']:,}" if r["total"] is not None else "?"
        print(f"    {r['name'][:50]:50s} live {r['live']:4d} / {tot:>5s}   test {r['test']:3d}")
    if not counts:
        print(f"\n  No {COUNTS_PATH} yet -- totals show as unknown until the harvester provides it.")
    elif data["catalog_stale"]:
        print(f"\n  NOTE: catalog totals are from {data['catalog_counted']}, more than {COUNTS_STALE_DAYS} days old.")


if __name__ == "__main__":
    main()
