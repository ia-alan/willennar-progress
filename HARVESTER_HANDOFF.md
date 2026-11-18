# Handoff: send catalog totals to the Willennar progress dashboard

Paste this whole file into Claude Code on the computer that runs the
Willennar catalog harvester (the tool that copies willennar.catalogaccess.com
records to archive.org as `test-willennar-...` items, with `pp_*` fields and
`pp_mirror_version`).

## What's needed

The dashboard at `https://ia-alan.github.io/willennar-progress/` shows how many
catalog records are on archive.org per catalog collection. It can count the
uploads itself, but it can't read the catalog site (it blocks automated
requests), so it needs the harvester to report how many records each catalog
collection has.

After each harvest, write `willennar_catalog_counts.json` and push it to the
`main` branch of `https://github.com/ia-alan/willennar-progress`. Pushing it
triggers the dashboard to refresh within a few minutes.

## File format

```json
{
  "counted": "2026-11-18",
  "source": "harvester test-0.3",
  "collections": {
    "Transportation in Indiana": {"total": 412, "photos": 400, "library": 12},
    "Extraordinary Hoosiers: Don Lash Collection": {"total": 87, "objects": 80, "photos": 7}
  }
}
```

- `counted`: the date the catalog was read, `YYYY-MM-DD`.
- `collections`: one entry per catalog collection, **every** collection in the
  catalog, including ones not uploaded yet.
  - Key: the collection name **exactly** as the harvester writes it to
    `pp_collection` on archive.org items (same spelling, punctuation and
    case). The dashboard matches on this string.
  - `total` (required, whole number): records in that collection, all types.
  - `photos`, `library`, `objects`, `archives` (optional): the same count
    split by record type, matching the `pp_record_type` values.
- Records with no collection in the catalog: key `"(no catalog collection)"`.
- Count each catalog record once.

## Pushing it

Only this one file should be committed. A minimal approach:

```bash
git clone https://github.com/ia-alan/willennar-progress.git   # once
cd willennar-progress
git pull --ff-only
cp /path/to/new/willennar_catalog_counts.json .
git add willennar_catalog_counts.json
git commit -m "Update catalog totals" && git push
```

This computer needs push access to `ia-alan/willennar-progress` (signed in to
GitHub as an account with write access, or a fine-grained token limited to
that one repo with Contents: read and write). Never commit anything else, and
don't edit `index.html`; the dashboard's own job rewrites it.

## Checking it worked

Within a few minutes of the push, the repo's Actions tab shows an "Update
catalog progress" run. If it fails, its log starts with `REFUSING TO WRITE`
and says what's wrong with the file. Once it succeeds, the dashboard's
"Records in catalog" tile shows the total.
