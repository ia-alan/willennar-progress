# Willennar catalog progress

How much of the Willennar Genealogy Center's PastPerfect catalog
(willennar.catalogaccess.com) is on the Internet Archive, by catalog collection.

Live page: https://ia-alan.github.io/willennar-progress/

- `update_site.py` searches archive.org for the catalog mirror's items and rewrites
  the data line in `index.html`. The GitHub Action runs it weekdays at 11:00 UTC,
  and whenever `willennar_catalog_counts.json` changes.
- `willennar_catalog_counts.json` holds each catalog collection's record count. The
  harvester writes and pushes it; see `HARVESTER_HANDOFF.md`.
- Uploads in `eckhartpubliclibrary` count as done; `test_collection` uploads are
  shown separately (archive.org removes them after about 30 days).
