# MIDAS backend API handoff

This is the current FastAPI contract for the frontend. It documents only
behavior that exists today. Release, login, and durable Vault storage are
not implemented. Critique · assess and bounded Critique · repair are
available. Local/dev job recovery after process restart is described in
section 12.

Interactive docs: `/docs`  
Machine-readable spec: `/openapi.json`

## 1. Base URL

Local development:

```
http://127.0.0.1:8000
```

Job routes are under `/api/v1`. Health is `GET /health`.

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
must match. The server stores those bytes on the job; they are not returned
on later GET responses.

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
current `stage` / `state`, hold/error when present, and nested Eye / Brain /
Stylist / Engine / Generation results when those stages have completed.

`GET /api/v1/jobs/{job_id}/status` is the short poll object: stage, state,
availability flags, hold, and error. It does not execute stages.

## 5. Stage endpoints

Each stage is an explicit POST. The matching GET returns persisted JSON and
does not re-run the provider.

| Stage | Execute | Read |
| --- | --- | --- |
| Eye | `POST /api/v1/jobs/{job_id}/eye` | `GET /api/v1/jobs/{job_id}/eye` |
| Brain | `POST /api/v1/jobs/{job_id}/brain` | `GET /api/v1/jobs/{job_id}/brain` |
| Stylist | `POST /api/v1/jobs/{job_id}/stylist` | `GET /api/v1/jobs/{job_id}/stylist` |
| Compile | `POST /api/v1/jobs/{job_id}/compile` | `GET /api/v1/jobs/{job_id}/compile` |
| Critique | `POST /api/v1/jobs/{job_id}/critique` | `GET /api/v1/jobs/{job_id}/critique` |
| Repair | `POST /api/v1/jobs/{job_id}/repair` | `GET /api/v1/jobs/{job_id}/repair` |

Execute bodies are empty objects:

```json
{}
```

The caller does not select a model. The backend model policy chooses the
stage model and records the effective `model_id` on the result/artifact.

Planning stages (Eye, Brain, Stylist, Critique) default to
`openai/gpt-4.1`. Compile persists the image model
`google/gemini-3.1-flash-image` onto `EngineCompile`. Generate and Repair
use that compiled image model. Extra `model_id` on a request is rejected
with `422`.

If a prior stage has not run, the API returns `409` with a stage-specific
code (`EYE_NOT_RUN`, `BRAIN_NOT_RUN`, `STYLIST_NOT_RUN`, `ENGINE_NOT_RUN`,
`GENERATION_NOT_RUN`, `CRITIQUE_NOT_RUN`).

If a prior stage is on HOLD, execute returns `409` (`BRAIN_NOT_READY`,
`STYLIST_NOT_READY`, `ENGINE_NOT_READY`, `GENERATION_NOT_READY`).

Provider failures return `502 PROVIDER_FAILURE`.

## 6. Generation endpoint

`POST /api/v1/jobs/{job_id}/generate`

Body is an empty object: `{}`. The image `model_id` is already recorded on
the compile artifact. This call claims and dispatches generation. It does not
repair or release. Critique is a separate POST.

`GET /api/v1/jobs/{job_id}/generate` returns the persisted operation and
receipt. It never dispatches again.

Generation JSON includes:

- `job_id`, `revision`, `stage`, `state`
- `generation.operation` (includes `model_id`, `exact_prompt`, reference ids, timestamps via `claimed_at`)
- `generation.receipt` (status, provider name, receipt id, hold reasons, output identity, timestamps)
- `generation.status`
- `generation.output_available`
- `generation.image_url` — `/api/v1/jobs/{job_id}/generate/image` when bytes exist, otherwise `null`

Repeating POST after a claimed, completed, held, or uncertain receipt does
not dispatch again.

## 7. Generated-image endpoint

`GET /api/v1/jobs/{job_id}/generate/image`

Returns the actual image bytes with `Content-Type` `image/png`, `image/jpeg`,
or `image/webp`.

This does not dispatch generation.

If generation has not run: `409 GENERATION_NOT_RUN`.  
If generation ran but there is no image: `409 GENERATION_IMAGE_UNAVAILABLE`.  
Unknown job: `404 JOB_NOT_FOUND`.  
Wrong owner: `403 JOB_OWNER_MISMATCH`.

## 8. Critique endpoint

`POST /api/v1/jobs/{job_id}/critique`

Body is an empty object: `{}`. The backend selects the Critique model.
Inspects the original reference and generated image. Does not repair.

`GET /api/v1/jobs/{job_id}/critique` returns the persisted assessment. It never
reruns Critique.

If generation is not completed or the image is missing: `409 GENERATION_NOT_READY`.

## 8b. Repair endpoint

`POST /api/v1/jobs/{job_id}/repair`

Body is an empty object: `{}`. The repair planner is deterministic and does
not call an LLM. Image generation uses `EngineCompile.model_id` already
recorded on the job by compile. Do not send `model_id` on this request.

Requires Critique `overall_result=repair_required`. Maximum two image repairs.
Repair #3 is impossible. The original product reference stays attached on
every attempt. A completed repair writes a new generation version and must be
re-reviewed with `POST /critique`. `GET /repair` never dispatches.

If Critique has not run: `409 CRITIQUE_NOT_RUN`.  
If Critique passed: `409 REPAIR_NOT_REQUIRED`.  
If the two-repair budget is exhausted: the job HOLDs and no provider call is
made.

## 9. Status values

Job `stage`: `intake` | `eye` | `brain` | `stylist` | `compile` | `generate` | `critique`

Job `state`: `accepted` | `ready` | `hold` | `failed`

Generation receipt `status`: `claimed` | `completed` | `failed` | `hold` | `uncertain`

`JobStatusView.ready` is Eye readiness (`readiness.status == "ready"`), not a
guarantee that later stages succeeded.

## 10. Error format

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
- `409` wrong revision, missing stage, or HOLD / not ready
- `422` invalid request
- `502` provider failure

## 11. Expected frontend flow

```
Create Job
  ↓
POST /api/v1/jobs
  ↓
GET /api/v1/jobs/{id}/status
  ↓
POST /api/v1/jobs/{id}/eye   then GET .../eye
  ↓
POST /api/v1/jobs/{id}/brain then GET .../brain
  ↓
POST /api/v1/jobs/{id}/stylist then GET .../stylist
  ↓
POST /api/v1/jobs/{id}/compile then GET .../compile
  ↓
POST /api/v1/jobs/{id}/generate
  ↓
GET /api/v1/jobs/{id}/generate   (poll; do not treat GET as execute)
  ↓
GET /api/v1/jobs/{id}/generate/image
  ↓
POST /api/v1/jobs/{id}/critique
  ↓
GET /api/v1/jobs/{id}/critique
```

Do not skip stages. Do not send the contract again after create. Do not
expect Repair or Release routes; they do not exist.

## 12. Local/dev job recovery after process restart

This is **not** durable production persistence and is **not** a database.

On FastAPI startup the process reconstructs in-memory `JobRecord`s from the
configured local artifact directory (`MIDAS_OUTPUTS_DIR`, defaulting to
`outputs/<job_id>/` in the repo). Completed Eye / Brain / Stylist / Compile /
Generate / Critique JSON already on disk is loaded into `JobStore`. Stages
are not rerun and providers are not called.

If a completed `generation.json` is present (`status=completed`, operation
key, provider receipt id, output metadata), `POST /generate` must not
dispatch another paid call. After restart you can `GET` restored stages and
continue with `POST /critique` when generation is already complete.

Jobs already in memory are not overwritten. Malformed artifacts are skipped
with a warning; they do not crash startup. Production Vault/object storage
is a later replacement of this local/dev seam.
