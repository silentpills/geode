# Dependency triage: 2026-11-02

Reviewed `dev` at `4d4ce3f`. This is an inventory and remediation plan, not a
record of applied upgrades. Deployment exposure below describes the committed
Dockerfiles and application paths; no running installation was inspected.

## Inventory and coverage

| Source | Result | Interpretation |
| --- | --- | --- |
| Live GitHub Dependabot API | 109 open alerts: 1 critical, 60 high, 45 moderate, 3 low | 107 reference the frontend lockfile; two reference the Trivy action. The earlier push banner reported 110. |
| Fresh npm audit of the committed lock | 32 affected-package entries: 21 high, 10 moderate, 1 low | Includes dependency chains, so these counts are not interchangeable with GitHub advisory counts. |
| Runtime PyPI audit | 29 advisory records across five of 92 audited packages | No Python Dependabot alerts were present, but the runtime audit finds matches. |
| Supplemental conda Python-distribution audit | Matches in 14 of 76 distributions | Match installed distribution metadata to the runtime lock; verify conda build patches before treating upstream-version matches as confirmed vulnerabilities. |

All 107 frontend GitHub alerts still match versions in the committed
lockfile. Several concern Node-only or development features, rather than the
browser application. The production frontend serves a static bundle through
Nginx, while the backend installs Pixi's `runtime` environment.

The runtime contains 93 PyPI entries including the editable application and 247
conda packages. The existing Python security job audits only the 92 external
PyPI entries. It misses conda-distributed Python libraries as well as native
libraries. Supplemental results contain duplicate records and aliases; they
must not be summed as independent vulnerabilities. Base images, apt packages,
native libraries and a running deployment were not scanned in this triage.

## 1. Restore the container scanner

Both scans in `.github/workflows/docker.yml` reference
`aquasecurity/trivy-action@0.33.1`. The latest inspected
[Docker run](https://github.com/silentpills/geode/actions/runs/41525124280) is green,
but its [scan job](https://github.com/silentpills/geode/actions/runs/41525124280/job/125552954028)
fails during setup because that action version no longer resolves. Job-wide
`continue-on-error: true` hides the failure; neither image was scanned.

The critical alert concerns the
[March 2026 Trivy supply-chain compromise](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23).
The old tag was in the affected range. None of the 67 retained Docker runs or
their inspected reruns executed in the affected March 19–20 action window. No
evidence of malicious execution was found; deleted history cannot be excluded.
The separate [action-input injection advisory](https://github.com/aquasecurity/trivy-action/security/advisories/GHSA-9p44-j4g5-cfx5)
has no identified untrusted-input path in this workflow's literal scan settings.

Prepare this focused workflow change:

```yaml
uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
with:
  version: v0.76.1
  exit-code: '0'
```

The SHA was verified against the signed, immutable
[action release](https://github.com/aquasecurity/trivy-action/releases/tag/v0.36.0).
The [binary release](https://github.com/aquasecurity/trivy/releases/tag/v0.76.1)
is also immutable. Apply to both scans and remove job-wide
`continue-on-error`. This keeps vulnerability findings informational while
surfacing setup/tool failures. Verify that both actual scans complete before
claiming image coverage.

## 2. Patch deployed Python dependencies

The following targets come from the live audit, not an indiscriminate upgrade
of the scientific stack. Re-resolve the shared Pixi environment and inspect
changes on both supported platforms.

| Locked package | Initial upgrade target | Important qualification |
| --- | --- | --- |
| aiohttp 3.14.3 | 3.14.4 or later patched release | Network-client dependency; validate the call paths used by downloads. |
| anyio 4.12.1 | 4.14.2 or later patched release | Validate HTTP/client integration and cancellation behavior. |
| Django REST Framework 3.17.2 | 3.18.2 or later patched release | Requires changing the `~=3.17.2` constraint and API compatibility tests. Preserve Django 5.2 LTS. |
| multidict 6.7.1 | 6.9.1 or later patched release | Resolve alongside aiohttp. |
| PyJWT 2.13.0 | 2.15.0 or later patched release | One audit advisory, `PYSEC-2026-4146`, lists no fix; investigate its prerequisites separately. A version bump alone is not a clean bill of health. |

DRF's [content-negotiation](https://github.com/advisories/GHSA-33wh-fxxf-88vv)
and [JSON-parser](https://github.com/advisories/GHSA-3547-9m27-7rxg) findings are
high severity and concern the API's request-handling layer. The third DRF
finding concerns TokenProxy revocation; this application configures SimpleJWT
rather than TokenProxy authentication. PyJWT is consequently important to test,
although the [unfixed options-dictionary advisory](https://github.com/advisories/GHSA-gvp8-978c-rx2q)
has no identified direct application call satisfying its prerequisites.

The aiohttp/multidict path is Earthscope SDK through aioboto3/aiobotocore; anyio
is reached through httpx. These are outbound processing clients. An aiohttp
server advisory does not automatically apply to the Django/Gunicorn server.

Supplemental conda-distribution matches need package-build verification before
choosing final targets:

| Package | Locked version | Audit patch candidates / disposition |
| --- | --- | --- |
| brotli | 1.2.0 | 1.2.1 |
| certifi | 2026.1.4 | 2026.10.18 |
| cryptography | 46.0.3 | Multiple fixes extend through 50.0.0; review compatibility and conda availability. |
| geopy | 2.4.1 | 2.5.0 |
| h2 / hpack | 4.3.0 / 4.1.0 | 4.4.1 / 4.2.0 |
| idna | 3.11 | 3.15 |
| lxml | 6.0.2 | 6.1.0 |
| paramiko | 4.0.0 | `PYSEC-2026-2858` lists no fix; assess the affected SSH behavior. |
| Pillow | 12.1.0 | Multiple fixes extend through 13.0.0; prioritize upload/image paths and verify compatibility. |
| Pygments | 2.19.2 | 2.20.0 |
| requests / urllib3 | 2.32.5 / 2.6.3 | 2.33.0 / 2.8.0 |
| tornado | 6.5.3 | Multiple fixes extend through 6.6; determine which server/client features are used. |

Do not upgrade NumPy, SciPy or the processing model merely to refresh unrelated
dependencies. After targeted changes, run the runtime audits, processing check,
web API tests, and fresh deployment smoke test. Add authentication regressions
for the applicable JWT advisory conditions.

## 3. Refresh frontend dependencies selectively

| Package | Current version | Target for the listed alerts | Exposure / action |
| --- | --- | --- | --- |
| ExifReader | 4.29.0 | At least 4.41.1 | Both photo/file upload dialogs call `ExifReader.load(file, {async: true})`. Prioritize malformed/compressed metadata and HEIC/AVIF coverage. |
| Axios | 1.12.0 | At least 1.20.0 | Browser API client carries bearer tokens. Patch; distinguish browser behavior from Node HTTP/proxy-only advisories. |
| @xmldom/xmldom | 0.9.8 | At least 0.9.12 | Optional ExifReader dependency. Browser paths normally use native DOMParser; update the lock with ExifReader. |
| react-router-dom / react-router | 6.30.3 | 6.30.6 fixes some alerts; at least 7.18.0 for remaining router alerts | Stage a separate v7 migration. Current app is client-only, so SSR hydration exposure was not identified. Review dynamically constructed navigation paths. |
| @remix-run/router | 1.23.2 | At least 1.23.3 | Refresh with the v6 router patch as an interim step. |
| Draft.js / @types/draft-js / Immutable | 0.11.7 / 0.11.18 / 3.7.6 | Prefer removing the unused Draft dependencies | No application imports found. Both parents constrain Immutable to `~3.7.4`; a normal refresh cannot reach patched 3.8.4. |
| Moment | 2.30.1 | Remove if unused; otherwise at least 2.31.0 | No source/config use found. |
| lodash / lodash-es | 4.17.23 | At least 4.18.0 | Active transitive dependencies; no direct application calls to the flagged APIs were found. |

The [ExifReader metadata advisory](https://github.com/mattiasw/ExifReader/security/advisories/GHSA-rr89-w3h9-m66j)
describes a call mode used by this application. Exceptions are caught in the
dialogs, but that does not reliably contain memory exhaustion. Test malformed
uploads and preserve orientation/GPS extraction behavior.

The [router backslash-navigation advisory](https://github.com/remix-run/react-router/security/advisories/GHSA-wrjc-x8rr-h8h6)
includes all 6.x versions. Do not describe a 6.30.6 update as resolving every
router alert. Check navigation from station/network identifiers and breadcrumbs.

### Stored HTML needs an application fix

`react-quill@2.0.0` brings in `quill@1.3.7`; the
[Quill advisory](https://github.com/advisories/GHSA-4943-9vgg-gr5r) lists no patched
release in that line. Its interpretation is disputed upstream, but an independent
application concern remains: `classHtml()` adds classes without sanitizing,
visit comments pass through the API, and saved comments are rendered through
`dangerouslySetInnerHTML`. No explicit HTML sanitizer was found at those
boundaries.

Prepare an allowlisted rich-text sanitization change, covering newly submitted
and previously stored HTML, with API and rendering regressions. Choose a
maintained editor integration separately. Do not accept npm's suggested ancient
downgrades of ReactQuill or Draft.js as a remediation.

### Build and development dependencies

Refresh compatible patch lines for Vite, PostCSS, Rollup, Browserslist,
source-map-js, nanoid, js-yaml, brace-expansion, picomatch, Babel, flatted,
postcss-selector-parser, Ajv and yaml. Their presence in a production dependency
list does not mean they execute in Nginx, but they still execute in builds or
development. Audit Node-only Axios dependencies such as form-data and
follow-redirects alongside Axios.

A non-forced, lock-only `npm audit fix` trial on temporary manifest copies
changed 94 package paths. It reduced high-severity affected-package entries
from 21 to three, but left 23 affected-package entries overall. The remaining
high entries are the Draft/Immutable chain; Quill, router and build-tool
limitations remain. The trial also surfaced newer minimatch/glob advisories.
This was a resolution experiment, not an installed or build-tested candidate.
Use its resolution evidence to prepare smaller reviewed changes rather than
copying the whole trial lock or forcing major updates.

After each frontend batch: clean `npm ci`, frontend build, fresh audit, and
focused upload/authentication/rich-text/navigation checks. Persist unresolved
advisories with their actual exposure conditions rather than suppressing the
entire audit.

## Verification and completion criteria

The triage queried the live GitHub alert inventory, inspected current source and
retained CI history, ran npm and Python audits, and exercised a temporary npm
resolution. It did not upgrade dependencies, execute application payloads,
deploy changes or rotate credentials.

Remediation is complete only when the scanner actually runs, applicable locked
dependencies are patched or have explicit evidence-based dispositions, relevant
tests pass, and rebuilt deployment images have been audited. Add conda Python
coverage to the Python audit without relabeling native conda packages as PyPI
projects. Keep this plan current as each batch is implemented.
