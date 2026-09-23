# Local secrets (never committed)

API keys for the offline harvest scripts live here as plain files. **Everything in this folder is
git-ignored except this README and `*.example` templates** (see `.gitignore`). Never paste a real key
into a tracked file, a commit, or a chat.

## URDB / NREL Utility Rate API key

Put your key in a file named `urdb_api_key` (no extension) in this folder:

```
secrets/urdb_api_key      ← one line: your key, nothing else
```

`scripts/build_urdb.py` resolves the key in this order:
1. `--api-key <key>` command-line flag
2. `URDB_API_KEY` environment variable
3. `secrets/urdb_api_key` (this file)
4. `DEMO_KEY` (rate-limited public fallback)

So once `secrets/urdb_api_key` exists, just run:

```
.venv/Scripts/python.exe scripts/build_urdb.py --state CA
```

## PVWatts (NLR, formerly NREL) API key

NREL was renamed the **National Laboratory of the Rockies (NLR)**; `developer.nrel.gov` no longer
resolves. Get a key at https://developer.nlr.gov/signup/ and put it in:

```
secrets/nrel_api_key      ← one line: your key, nothing else
```

`scripts/build_pvwatts.py` resolves the key in this order:
1. `--api-key <key>` command-line flag
2. `NREL_API_KEY` environment variable
3. `secrets/nrel_api_key` (this file)
4. `URDB_API_KEY` env / `secrets/urdb_api_key` (fallback: the developer networks share a key namespace)
5. `DEMO_KEY` (rate-limited public fallback)

```
.venv/Scripts/python.exe scripts/build_pvwatts.py --region ca_zone_stations
```
