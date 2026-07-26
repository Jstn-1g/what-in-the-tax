# Regional geography fixtures

`ontario-waterloo-test-ring.json` is the offline QA registry for the seven
lower-tier municipalities in the Region of Waterloo and the first ring returned
by Ontario's official municipal-boundary topology.

The adjacent list uses the ArcGIS `esriSpatialRelTouches` relation. It means two
municipal polygons touch; it does **not** imply that they share a taxing
authority, service, or tax rule. A touch may also be point-only. Administrative
relationships are represented separately by `parentSlug`.

The companion `ontario-waterloo-test-ring.sources.lock.json` records the
official Ontario layers, query method, retrieval/effective dates, licence, and
the SHA-256 of the canonicalized registry. It also independently retains the
exact touch results by assessment code, their normalized edge count, and
canonical hashes. Canonicalization makes the lock independent of checkout line
endings and JSON indentation. Normal builds and tests never call those
services:

```powershell
python scripts/validate_regional_registry.py
python -m unittest discover -s tests -p "regional*.py"
```

Refreshing this fixture is a reviewed evidence update. Re-run the documented
queries against the locked official layers, reconcile all identity and topology
changes, update the normalized registry, and then update its hash and retrieval
metadata together. Do not refresh the hash merely to make validation pass.

Every existing lower- or single-tier corpus pack and build input must carry its
official `assessmentCode`. A deliberately unavailable jurisdiction may omit it
only by declaring `identityStatus: unsupported`; that status is accepted solely
for draft or withdrawn packs and blocks sealing or publication.
