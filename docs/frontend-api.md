# MIDAS backend API handoff

This is the current FastAPI contract for the frontend. It documents only
behavior that exists today. There is no login layer and no durable Vault.
Job state in a running process is in memory. Files under `outputs/<job_id>/`
are the local recovery seam.

Interactive docs: `/docs`
Machine-readable spec: `/openapi.json`

Swagger lists every POST operation before every GET operation. The routes
themselves are unchanged.

## 1. Base URL

Local development:

```
http://127.0.0.1:8000
```

Copy `.env.example` to `.env` in the repo root. python-dotenv loads that file
(process environment wins). UIMidas Manual persist uses operator-provided
`MIDAS_DEV_OWNER_ID` and `MIDAS_DEV_CONTRACT_ID` from `.env` when the POST
body omits Architecture A identity. That is not production identity.
`.env.example` is not loaded.

Start the API with `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
and UIMidas with `npm run dev` in `UIMidas/` (`http://127.0.0.1:5173`). Vite
proxies `/api` to this base URL.

Job routes are under `/api/v1`. Health is `GET /health`. Client briefs are
`POST /api/v1/client-briefs` and `GET /api/v1/client-briefs/{brief_id}`.
`POST /api/v1/client-briefs/{brief_id}/jobs` maps a saved Manual one-by-one
brief to Phase-0, creates a job, and schedules Eye → Brain → Stylist → Compile.
It does not generate images. Unmapped Phase-0 fields return
`BRIEF_MAPPING_UNRESOLVED` and leave the brief unchanged.

## 2. Authentication assumptions

There is no login, API key, or session layer on this API.

Optional query parameters on job reads and stage calls:

- `owner_id` — if present, must match the job's `owner_id` or the API returns `403 JOB_OWNER_MISMATCH`
- `revision` — if present, must match the frozen contract revision or the API returns `409 REVISION_MISMATCH`

`owner_id` is copied from the job contract at create time. It is an
application-level check, not authentication.

## 3. Job creation request

`POST /api/v1/jobs`

Body:

```json
{
  "contract": { }
}
```

The contract is the Phase-0 job contract. Image references (`JPG`, `PNG`,
`WebP`) must include `content_base64`. `content_hash` is optional on create:
the server SHA-256 hashes the decoded file bytes (not the base64 string) and
stores that digest on the frozen contract. If you send `content_hash`, it
must match. Do not send `request_identity`, `request_hash`, or
`source_hashes`. The server derives `source_hashes` from those file digests
and `request_hash` from the canonical contract, then stores both on the
frozen contract. The server stores the file bytes on the job; they are not
returned on later GET responses.

Eye is not executed on create.

## 4. Job response

`POST /api/v1/jobs` returns:

- `job_id`
- `owner_id`
- `contract_id`
- `revision`
- `state` / `status` (same job-state value)
- `stage` (`intake` after create)

`GET /api/v1/jobs/{job_id}` returns the public job view: frozen contract,
current `stage` / `state`, hold/error when present, nested stage results when
those stages have completed, `review_status`, `complete`, `releasable`, and
`approved`. `approved` is true only after final owner approval. Pre-generation
approval does not set it.

`GET /api/v1/jobs/{job_id}/status` is the short poll object: stage, state,
availability flags, hold, and error. It does not execute stages.

## 5. POST endpoints

Each execute route is explicit. A GET never re-runs a provider.

| Action | Route |
| --- | --- |
| Create job | `POST /api/v1/jobs` |
| Eye | `POST /api/v1/jobs/{job_id}/eye` |
| Brain | `POST /api/v1/jobs/{job_id}/brain` |
| Stylist | `POST /api/v1/jobs/{job_id}/stylist` |
| Compile | `POST /api/v1/jobs/{job_id}/compile` |
| Pre-generation approval | `POST /api/v1/jobs/{job_id}/generate/approve` |
| Generate | `POST /api/v1/jobs/{job_id}/generate` |
| Critique | `POST /api/v1/jobs/{job_id}/critique` |
| Repair | `POST /api/v1/jobs/{job_id}/repair` |
| Final owner approval | `POST /api/v1/jobs/{job_id}/review/approve` |
| Release | `POST /api/v1/jobs/{job_id}/review/release` |

Stage bodies may be `{}`. `model_id` is optional. Planning stages (Eye, Brain,
Stylist, Critique) default to `openai/gpt-4.1`. Compile, Generate, and Repair
default to `google/gemini-3.1-flash-image`. A model outside the allowed set
returns `422`. Generate and Repair must match the image model already stored
on the compile artifact. A different allowed image model returns `422`.

If a prior stage has not run, the API returns `409` with a stage-specific
code (`EYE_NOT_RUN`, `BRAIN_NOT_RUN`, `STYLIST_NOT_RUN`, `ENGINE_NOT_RUN`,
`GENERATION_NOT_RUN`, `CRITIQUE_NOT_RUN`).

If a prior stage is on HOLD, execute returns `409` (`BRAIN_NOT_READY`,
`STYLIST_NOT_READY`, `ENGINE_NOT_READY`, `GENERATION_NOT_READY`).

Provider failures return `502 PROVIDER_FAILURE`.

## 6. GET endpoints

| Read | Route |
| --- | --- |
| Job | `GET /api/v1/jobs/{job_id}` |
| Eye | `GET /api/v1/jobs/{job_id}/eye` |
| Brain | `GET /api/v1/jobs/{job_id}/brain` |
| Stylist | `GET /api/v1/jobs/{job_id}/stylist` |
| Compile | `GET /api/v1/jobs/{job_id}/compile` |
| Generation | `GET /api/v1/jobs/{job_id}/generate` |
| Critique | `GET /api/v1/jobs/{job_id}/critique` |
| Repair | `GET /api/v1/jobs/{job_id}/repair` |
| Image bytes | `GET /api/v1/jobs/{job_id}/generate/image` |
| Status | `GET /api/v1/jobs/{job_id}/status` |

These reads return persisted JSON, or image bytes for the image route. They
do not dispatch providers.

## 7. Pre-generation approval

`POST /api/v1/jobs/{job_id}/generate/approve`

Authorizes one render. It does not approve the reviewed candidate and does
not release.

The record is bound to:

- `owner_id`
- `contract_id`
- contract revision
- `request_hash`
- `render_count` (`1` for the initial generate call)
- `approved_at`
- `expires_at` when the caller sends one

The job contract has no expiry field. Omit `expires_at`, or send `null`,
when the approval should not expire. Body `{}` is valid.

```json
{ "expires_at": null }
```

Calling approve again for the same owner, revision, request hash, and render
count does not create a second record.

`POST /generate` returns `409 PRE_GENERATION_APPROVAL_REQUIRED` and does not
call OpenRouter when:

- no pre-generation approval exists
- the approval owner does not match the job owner
- the request hash does not match
- the contract revision does not match
- the render count does not match
- `expires_at` is in the past

A changed contract revision invalidates the previous approval. Compile must
already be ready. A held compile returns `409 GENERATION_NOT_READY` and does
not record approval.

## 8. Generation

`POST /api/v1/jobs/{job_id}/generate`

Requires a matching pre-generation approval. The call then claims one
operation and sends it to the OpenRouter Image API (`POST /api/v1/images`).
Compiled resolution and aspect ratio are sent as provider fields. Reference
images are sent as input references when the model advertises them.

The backend then measures the returned image. `format_check` passes only when
the measured long edge is in the requested resolution tier, the aspect ratio
is within tolerance, and the MIME type agrees. The bytes are not resized or
upscaled. A mismatch holds the job and keeps the measured image.

`GET /api/v1/jobs/{job_id}/generate` returns the persisted operation and
receipt. It never dispatches again.

Generation JSON includes:

- `generation.operation` (`model_id`, exact prompt, reference ids, output format, `claimed_at`)
- `generation.receipt` (status, provider name, receipt id, format check, measured pixels, provider request, provider usage, provider cost)
- `generation.status`
- `generation.output_available`
- `generation.image_url` — `/api/v1/jobs/{job_id}/generate/image` when bytes exist, otherwise `null`

`provider_cost` is present on a completed OpenRouter receipt:

- `amount` is the provider-reported number when `usage.cost` was returned
- `currency` is set only when the provider response included a currency; otherwise `null`
- `status` is `known` or `unknown`

Unknown cost uses `amount: null`. It is never stored as `0`. This is receipt
evidence, not a price quote or a billing system. The delivery manifest copies
that object when the current receipt has one. Jobs with no provider cost keep
manifest `cost: null` and `cost_status: "not_recorded"`.

Repeating POST after a claimed, completed, held, or uncertain receipt for the
same operation does not dispatch again. A `failed` receipt with
`retry_if_never_started` can be dispatched again. That classification is used
when OpenRouter returned a finished rejection, such as HTTP 4xx, or a finished
body with no image. A timeout or dropped connection stays `uncertain` /
`reconcile_only` and blocks another paid call.

## 9. Generated-image endpoint

`GET /api/v1/jobs/{job_id}/generate/image`

Returns the actual image bytes with `Content-Type` `image/png`, `image/jpeg`,
or `image/webp`.

This does not dispatch generation.

If generation has not run: `409 GENERATION_NOT_RUN`.
If generation ran but there is no image, or the checksum does not match:
`409 GENERATION_IMAGE_UNAVAILABLE`.
Unknown job: `404 JOB_NOT_FOUND`.
Wrong owner: `403 JOB_OWNER_MISMATCH`.

## 10. Critique

`POST /api/v1/jobs/{job_id}/critique`

Inspects the original reference and the generated image. It does not repair
and it does not approve or release.

The assessment includes:

- product fidelity findings: inventory, identity, geometry, details, appearance, placement, lighting, composition
- styling compliance
- Brain/Stylist plan compliance
- requested view
- scene compliance
- attribute drift
- unknowns, kept separate from findings

A finding `result` of `pass` cannot use severity `critical`. Severity
`critical` is only for `fail` or `uncertain`.

`overall_result` `pass` moves the job to review. It does not set `complete`
or `releasable`. Release still needs final owner approval.

`GET /api/v1/jobs/{job_id}/critique` returns the persisted assessment and
does not rerun Critique.

If generation is not completed or the image is missing:
`409 GENERATION_NOT_READY`.

## 11. Repair

`POST /api/v1/jobs/{job_id}/repair`

Runs only when the latest Critique has `overall_result` `repair_required`.
The planner does not call an LLM. Image generation, when the selected action
is supported, uses the compiled image model.

The limit is two image repairs. A third attempt holds and does not call the
provider. Repair does not rerun Eye, Brain, Stylist, or Compile. The original
product reference stays on the operation. The plan names protected scene
attributes and the product-authority reference.

The current OpenRouter generation adapter does not advertise `local_edit`.
A non-geometry repair selects that targeted edit, then the job holds, and
scene preservation is not claimed. A geometry or identity failure can select
`fresh_render`. That is a new image call. It does not claim the previous
scene was preserved. An unsupported or exhausted repair holds.

A completed repair writes another generation version. It must be critiqued
again before final approval. `GET /repair` never dispatches.

If Critique has not run: `409 CRITIQUE_NOT_RUN`.
If Critique passed: `409 REPAIR_NOT_REQUIRED`.

No live repair-required job is part of the end-to-end proof below.

## 12. Final owner approval and release

These routes are separate from pre-generation approval.

`POST /api/v1/jobs/{job_id}/review/approve`

Records owner approval of the current critiqued candidate. Critique pass
alone cannot do this. The record is bound to the owner, contract revision,
request hash, and generation output id. On success, `complete` and
`releasable` become true and `review_status` is `owner_approved`.

If Critique has not passed, format check has not passed, or the image is
missing: `409 REVIEW_NOT_READY`.

`POST /api/v1/jobs/{job_id}/review/release`

Releases an already approved candidate. It does not create approval.
Pre-generation approval is not enough. On success, `review_status` is
`released`.

If final approval is missing: `409 RELEASE_NOT_READY`.

## 13. Status values

Job `stage`: `intake` | `eye` | `brain` | `stylist` | `compile` | `generate` | `critique` | `repair`

Job `state`: `accepted` | `ready` | `hold` | `failed` | `review_pending` | `approved` | `released`

`review_status`: `generation_completed` | `critique_passed` | `review_pending` | `owner_approved` | `released` | `hold`

Generation receipt `status`: `claimed` | `completed` | `failed` | `hold` | `uncertain`

`JobStatusView.ready` is Eye readiness (`readiness.status == "ready"`), not a
guarantee that later stages succeeded.

## 14. Error format

All errors use:

```json
{
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Job not found",
    "details": {}
  }
}
```

Common HTTP statuses:

- `403` owner mismatch
- `404` job not found
- `409` wrong revision, missing stage, HOLD / not ready, or missing pre-generation approval
- `422` invalid request or disallowed model
- `502` provider failure

## 15. Expected frontend flow

```
POST /api/v1/jobs
  ↓
POST /api/v1/jobs/{id}/eye
POST /api/v1/jobs/{id}/brain
POST /api/v1/jobs/{id}/stylist
POST /api/v1/jobs/{id}/compile
  ↓
POST /api/v1/jobs/{id}/generate/approve
POST /api/v1/jobs/{id}/generate
  ↓
GET  /api/v1/jobs/{id}/generate
GET  /api/v1/jobs/{id}/generate/image
  ↓
POST /api/v1/jobs/{id}/critique
  ↓
POST /api/v1/jobs/{id}/repair    only when Critique is repair_required
POST /api/v1/jobs/{id}/critique  again after a completed repair
  ↓
POST /api/v1/jobs/{id}/review/approve
POST /api/v1/jobs/{id}/review/release
```

GET routes are for polling and display. Do not skip stages. Do not send the
contract again after create. Do not treat pre-generation approval as release.

## 16. Local artifacts

Files are under `outputs/<job_id>/` unless `MIDAS_OUTPUTS_DIR` is set.

- `job.json` — contract, owner, review, pre-generation approval, final approval, release
- `input/` — reference bytes
- `eye.json`, `brain.json`, `stylist.json`, `compile.json`
- `generation.json` and `generations/` — receipt, measured pixels, provider usage and cost when returned
- `output/` — generated image bytes
- `critique.json` and `critiques/`
- `repair.json` and `repairs/` when repair has run
- `manifest.json` — delivery projection, including persisted cost evidence when the receipt has it

Reference metadata and checksums are computed from stored bytes. A checksum
mismatch holds the job. The image GET then returns `409`.

## 17. Recovery

This is not durable production persistence and is not a database.

On FastAPI startup the process reconstructs in-memory jobs from the local
artifact directory. Saved Eye, Brain, Stylist, Compile, Generate, Critique,
and Repair JSON is loaded. Pre-generation approval is loaded with `job.json`.
Stages are not rerun and OpenRouter is not called.

If `generation.json` has a receipt that blocks dispatch, `POST /generate`
does not make another paid call. After restart you can GET restored stages
and continue with the next POST that the recovered state allows.

Jobs already in memory are not overwritten. Malformed artifacts are skipped
with a warning. They do not crash startup.

## 18. One live end-to-end case

Job `dd169c6b-fc47-46e3-bd28-20bc002f348b`.

Eye observed one dining table and six dining chairs. The contract category
is Dining Sets. The path that completed was:

Create → Eye → Brain → Stylist → Compile → pre-generation approval →
OpenRouter generate → pixel validation → Critique pass → final owner
approval → release.

The image is a 2048×2048 PNG. The provider request used `resolution` `2K`
and `aspect_ratio` `1:1` on `google/gemini-3.1-flash-image`. Format check
passed. Provider-reported cost is `0.102204` with status `known`. Currency
was not in the provider payload, so it is null. The job is `released`, with
`complete=true`, `releasable=true`, and final approval present.

The local test suite at the time of this note was `311 passed, 7 skipped`.

This is one live case. It does not prove every product category, a companion
or SKU workflow, or a live repair-required job.
