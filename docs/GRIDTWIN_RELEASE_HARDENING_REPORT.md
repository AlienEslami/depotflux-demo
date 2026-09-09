# GridTwin local release-hardening report

Review date: 2026-09-09 UTC. Candidate branch: `codex/gridtwin-ops`.
Candidate base before this review: `460a32013dfca7f4f321bc98657da1fca584b909`.

This is a bounded, local engineering review. It does not authorize a push,
publication, visibility change, cloud deployment, licence grant or claim of
security, safety, field readiness, certification or standards compliance.

## Verdict

The local code, dependency and evidence gates described below pass, with one
material scan limitation: Docker Scout generated SBOMs for the rebuilt images
but would not perform CVE lookups without a Docker ID login. Public release
therefore remains **hold** pending the image/OS CVE scan, an owner-selected
repository licence, independent review, and CI on the exact publication
candidate.

## Dependency finding and bounded remediation

The initial npm advisory scan reported four high-severity dependency paths:
direct `@cloudflare/vite-plugin` and `wrangler`, plus transitive `miniflare` and
`sharp`. Both current Cloudflare packages resolved through a Miniflare alpha
that pinned `sharp` 0.35.2, affected by the libheif advisory identified by npm.
At review time, the latest Cloudflare package metadata still resolved that
version. npm's proposed automatic fixes were disruptive downgrades.

The only package change is an npm `overrides` entry pinning transitive `sharp`
to patched version 0.35.4. No `--force`, major-version change or Cloudflare
downgrade was used. A clean `npm ci`, dependency-tree check, lint, TypeScript
check and production build passed. `npm audit` then reported zero known
advisories in its 697-package accounting (495 production, 83 development, 156
optional and 35 peer entries; categories overlap by npm's model). This is a
time- and database-bounded result, not a claim that the software is
vulnerability-free.

## Verification results

- Python: 97 tests passed in 188.69 seconds. The committed coverage artifacts
  report 73.681% combined line/branch coverage, 77.863% statement coverage and
  57.156% branch coverage.
- Gateway denial: the TCP-backed integration test exercised actual gateway
  authentication/range policy. Unauthorized and unsafe requests produced no
  Modbus request at the counting PLC and left its registers unchanged.
- Contract/UI: OpenAPI drift, dashboard lint, TypeScript no-emit and production
  build passed. The existing large-chunk advisory and Vinext dynamic-route note
  remain non-blocking build warnings.
- Compose: all seven rebuilt services reached their expected running states;
  the five services with health checks were healthy. Because ports 3000, 8000
  and 9100 were already owned by a separate running DepotFlux lab, the rerun
  used an ignored local Compose override on 13000, 18080 and 19100. No unrelated
  container was stopped. The live API readiness request on port 18080 returned
  HTTP 200.
- Canonical Docker/HiGHS evidence: all three scenarios and the minimum gate
  passed in 82.879 seconds. The constrained result was 126.907 CAD cost,
  55.962 CAD export revenue, 1,371.545 kW peak, 2,107.347 kWh feeder losses,
  zero voltage/thermal violation intervals and 882.117 kWh BESS throughput.
  Against cost-only operation it reduced peak by 228.455 kW (14.28%), removed
  two voltage-violation intervals, reduced modeled losses by 5.292 kWh and
  added 0.606 CAD modeled cost.
- Optional local Gurobi 13.0.2 cross-check: the evidence gate passed in 33.470
  seconds and reproduced 126.907 CAD constrained cost, 1,371.545 kW peak, zero
  violations and 882.117 kWh throughput. Its reported constrained combined
  solve time was 2.442 seconds. This is not a controlled solver benchmark.

The authoritative measured artifacts are `evidence/gridtwin/results.json` and
`evidence/gridtwin/results.md`; the optional cross-check is under
`evidence/gridtwin-gurobi/`.

## Security, SBOM and licence review

- A high-signal scan of the current tracked tree and every commit reachable
  from local refs found no private-key blocks or token forms for AWS, GitHub,
  OpenAI, Slack or Google. Only rule names, paths and abbreviated commit IDs
  were eligible for output; credential values were never printed. This manual
  regex review is not a substitute for an independently configured secret
  scanner before publication.
- The publication-claim search returned only explicit limitations or warnings;
  manual review confirmed that none of the high-risk phrase contexts asserts
  NIST/IEC/ISO compliance, certification, production readiness, field
  validation, functional safety, utility employment or physical control.
- `pip-audit` reported zero known vulnerabilities across 50 resolved Python
  dependencies. The checked-in npm and Python CycloneDX files contain 545 and
  50 components respectively.
- Docker Scout produced CycloneDX inventories for the exact rebuilt API (216
  components), dashboard (669) and database (67) images. The API image is
  representative of the shared Python build used by API, worker, gateway, PLC
  simulator and monitor services. CVE lookup did not run because Docker Scout
  required an account login; no empty or misleading CVE report is committed.
- The direct Python dependency review found MIT, BSD-3-Clause and composite
  NumPy terms, plus LGPL-3.0-only for Psycopg. The npm lock contains permissive,
  Apache, MPL, LGPL, CC and Python-2.0 metadata with no package missing its
  licence field. These inventories require a final notice/redistribution and
  legal review; they do not select or grant a project licence.

Machine-readable evidence is under `evidence/release/`. The licence counts and
review limits are captured in `dependency-license-summary.json`; project
licence choices are described separately in `docs/GRIDTWIN_LICENSE_OPTIONS.md`.

## Reproduction commands

```powershell
./scripts/verify_gridtwin.ps1
./scripts/depotflux.ps1 gridtwin
python -m pip_audit -r requirements-demo-lock.txt --progress-spinner off
Set-Location dashboard
npm ci
npm audit
npm sbom --sbom-format cyclonedx
```

If the default host ports are occupied, use a local Compose override; do not
interrupt unrelated services. Gurobi is optional and only reproducible on a
host with a suitable local licence. Docker/CI evidence remains HiGHS-based and
credential-free.

## Remaining release blockers

1. Complete and assess a CVE scan of the exact image/OS packages without adding
   credentials to the repository.
2. Have the owner choose a repository and documentation licence after reviewing
   the options and third-party obligations.
3. Run CI and an independent secret/provenance/usability/security review on the
   exact publication candidate and record the decision.
