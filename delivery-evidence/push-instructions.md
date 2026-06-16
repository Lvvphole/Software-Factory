# Push & PR Instructions (credential fallback)

Credentials for `Lvvphole/Software-Factory` were not available in the build environment, so the port was committed locally and packaged as a patch. Two equivalent paths to land it:

## Option A — Apply the patch to a fresh clone, then push

```bash
git clone https://github.com/Lvvphole/Software-Factory.git
cd Software-Factory
git checkout -b port-v1-software-factory
git am < /path/to/port-v1-software-factory.patch
# verify locally
pip install -e ".[dev]"
bash scripts/test.sh
factory run --signal examples/sample-signal.json
# push
git push -u origin port-v1-software-factory
```

Then open the PR (web UI or gh CLI):

```bash
gh pr create \
  --base main \
  --head port-v1-software-factory \
  --title "Port v1 software factory implementation" \
  --body-file delivery-evidence/PR-body.md
```

## Option B — Push the already-prepared local repo

The local repo at the build environment's `/home/claude/work/Software-Factory` already has the branch and commit. Configure a remote with credentials and push directly:

```bash
cd /path/to/local/Software-Factory
git remote set-url origin https://<USER>:<TOKEN>@github.com/Lvvphole/Software-Factory.git
git push -u origin port-v1-software-factory
gh pr create --base main --head port-v1-software-factory \
  --title "Port v1 software factory implementation" \
  --body-file delivery-evidence/PR-body.md
```

## Facts of record

- **Branch:** `port-v1-software-factory`
- **Base:** `main`
- **Commit hash:** `18e4ba6fbb2aadbfda7ec602f64f55e93df1cd04`
- **Commit message:** `Port v1 software factory implementation`
- **Files changed:** 49 (+1561 / −1)
- **PR title:** `Port v1 software factory implementation`
- **PR body:** see `delivery-evidence/PR-body.md`
- **Patch file:** `port-v1-software-factory.patch` (1981 lines, included in delivery package)
