# MIDAS Virtual Studio

Backend for the MIDAS Virtual Studio workflow.

The backend provides a FastAPI API for furniture and product visualization jobs through a contract-driven Architecture A workflow. Job state for a running process is in memory. Completed stages are also written as local files under `outputs/<job_id>/` and can be reconstructed after restart. This is not a cloud deployment and not durable Vault storage.

## Workflow

```text
Create Job
  ↓
Eye
  ↓
Brain
  ↓
Stylist
  ↓
Compile
  ↓
Pre-generation approval
  ↓
OpenRouter image generation
  ↓
Pixel validation
  ↓
Critique
  ↓
Bounded Repair, when Critique requires it
  ↓
Critique again, after a completed repair
  ↓
Final owner approval
  ↓
Release
```

Each stage produces a typed artifact bound to the current job contract.

Two human approvals stay separate:

- Pre-generation approval authorizes one render. It does not authorize release.
- Final owner approval happens after Critique and is required before release.

## Architecture

The implementation follows Architecture A:

- FastAPI intake API
- Immutable job contract and server-derived request identity
- In-process job state
- Specialist stages
- OpenRouter for live planning and image generation
- Measured pixel validation after generation
- Independent critique
- Bounded repair
- Local artifact files and a delivery manifest
- Startup recovery from those files
- Contract and execution tests

Magnific is not a generation dependency. There is no billing, quote, or pricing subsystem. When OpenRouter returns a usage cost, that number is stored as evidence. A missing cost stays null and `unknown`. It is never stored as zero.

The image-model default is `google/gemini-3.1-flash-image`. Planning stages default to `openai/gpt-4.1`. Callers may send an allowed `model_id`. Generate and Repair must use the image model already compiled onto the job.

## API

API prefix:

`/api/v1`

POST endpoints:

- `POST /jobs`
- `POST /jobs/{job_id}/eye`
- `POST /jobs/{job_id}/brain`
- `POST /jobs/{job_id}/stylist`
- `POST /jobs/{job_id}/compile`
- `POST /jobs/{job_id}/generate/approve`
- `POST /jobs/{job_id}/generate`
- `POST /jobs/{job_id}/critique`
- `POST /jobs/{job_id}/repair`
- `POST /jobs/{job_id}/review/approve`
- `POST /jobs/{job_id}/review/release`

GET endpoints:

- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/eye`
- `GET /jobs/{job_id}/brain`
- `GET /jobs/{job_id}/stylist`
- `GET /jobs/{job_id}/compile`
- `GET /jobs/{job_id}/generate`
- `GET /jobs/{job_id}/critique`
- `GET /jobs/{job_id}/repair`
- `GET /jobs/{job_id}/generate/image`
- `GET /jobs/{job_id}/status`

`GET /health` reports process status. Interactive docs: `/docs`. Swagger lists POST operations before GET operations.

See `docs/frontend-api.md` for request and error details.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create `.env` from `.env.example` in the repo root:

```powershell
copy .env.example .env
```

Set `OPENROUTER_API_KEY` if you will call live providers. For UIMidas Manual persist (no jobs, no generation), set the operator-provided local labels in that `.env`:

```text
MIDAS_DEV_OWNER_ID=...
MIDAS_DEV_CONTRACT_ID=...
```

Those labels are not production identity. The backend loads `.env` with python-dotenv and does not require PowerShell `$env:` assignments. `.env.example` is not loaded.

## Run

Backend (from the repo root, with the venv active):

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

UIMidas (separate terminal):

```powershell
cd UIMidas
npm install
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
http://127.0.0.1:8000/docs
```

Vite proxies `/api` to the backend. Manual Review persists a brief only. Set `VITE_USE_MOCK_SUBMIT=true` in `UIMidas/.env.local` to keep the in-browser mock instead.

## Tests

Run the full local test suite:

```powershell
pytest -q
```

The last documented local run was `311 passed, 7 skipped`. The skipped tests are live provider calls. They stay skipped unless:

```powershell
$env:MIDAS_RUN_LIVE_PROVIDER_TEST="1"
pytest -q
```

## Project Structure

```text
app/
  api/          FastAPI routes and schemas
  contracts/    Typed stage contracts
  providers/    OpenRouter adapters and fake providers
  runtime/      Job state, artifacts, checksums, and recovery
  stages/       Eye, Brain, Stylist, Engine, Operator, Critique, Repair, package

tests/          Contract, execution, API, and recovery tests
docs/           API and source documentation
outputs/        Local job artifacts for this process
```

## Runtime Flow

Create stores the contract, hashes reference bytes, and derives `request_hash`. Eye, Brain, and Stylist then run as separate calls. Compile freezes the exact prompt, references, view, proportions, and resolution.

`POST /generate/approve` records pre-generation approval for the current owner, contract revision, request hash, and render count (`1`). `expires_at` is optional. The job contract has no expiry of its own. `POST /generate` returns `409 PRE_GENERATION_APPROVAL_REQUIRED` and does not call OpenRouter when that approval is missing, belongs to another owner, does not match the request hash or revision, names another render count, or is expired. A later contract revision clears the previous approval.

Generation uses the OpenRouter Image API (`POST /api/v1/images`). Resolution and aspect ratio are request fields, not prompt-only text. After the bytes return, the backend measures width, height, and MIME type. A tier or ratio mismatch is a hold. The image is not resized or upscaled to force a pass.

Critique compares the original reference and the generated image. It records product fidelity, styling, Brain/Stylist plan compliance, requested view, scene compliance, attribute drift, and unknowns. A Critique pass does not release the job. `POST /review/approve` records final owner approval. `POST /review/release` releases that approved candidate.

Repair runs only when Critique says `repair_required`. The limit is two image repairs. Repair is not a restart of Eye, Brain, Stylist, or Compile. The planner keeps the original product reference and names protected scene attributes. The current OpenRouter generation adapter does not advertise `local_edit`. A targeted local edit therefore holds, and scene preservation is not claimed. A geometry or identity failure can select `fresh_render`, which is a new image call and does not claim the previous scene was preserved. An exhausted repair limit holds with no further provider call. A completed repair must be critiqued again before final approval.

## Evidence

A job directory can contain:

- `job.json` — owner, contract, review, both approval records, release
- `eye.json`, `brain.json`, `stylist.json`, `compile.json`
- `generation.json` and `generations/` — operation, receipt, measured pixels, provider usage and cost when returned
- `output/` — current generated image bytes
- `input/` — stored reference bytes
- `critique.json` and `critiques/`
- `repair.json` and `repairs/` when a repair exists
- `manifest.json` — delivery projection, including persisted cost evidence when a receipt has it

Reference metadata and checksums are recorded from the stored bytes. A checksum mismatch holds the job.

## Recovery

On startup the process rebuilds in-memory jobs from `outputs/<job_id>/` (`MIDAS_OUTPUTS_DIR` overrides the directory). It loads the saved receipts. It does not call OpenRouter. A completed, held, or uncertain generation receipt blocks another paid dispatch for that operation.
