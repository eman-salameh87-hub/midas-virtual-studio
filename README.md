# MIDAS Virtual Studio

Production-oriented backend for the MIDAS Virtual Studio workflow.

The backend provides a FastAPI API for processing furniture and product visualization jobs through a contract-driven Architecture A workflow.

## Workflow

```text
Intake
  ↓
Eye
  ↓
Brain
  ↓
Stylist
  ↓
Engine
  ↓
Generate
  ↓
Critique
  ↓
Bounded Repair
  ↓
Critique
  ↓
Release / Hold
```

Each stage produces a typed artifact and is bound to the current job contract.

## Architecture

The implementation follows Architecture A:

- FastAPI intake API
- Immutable job contract
- Runtime job state
- Specialist stages
- OpenRouter provider integration
- Image generation
- Independent critique
- Bounded repair
- Local artifact persistence
- Startup recovery
- Contract and execution tests

The backend is provider-adapter based. Model IDs are supplied through stage/provider boundaries rather than being hard-coded into the workflow.

## API

API prefix:

`/api/v1`

Main endpoints include:

- `POST /jobs`
- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/status`
- `POST /jobs/{job_id}/eye`
- `GET /jobs/{job_id}/eye`
- `POST /jobs/{job_id}/brain`
- `GET /jobs/{job_id}/brain`
- `POST /jobs/{job_id}/stylist`
- `GET /jobs/{job_id}/stylist`
- `POST /jobs/{job_id}/compile`
- `GET /jobs/{job_id}/compile`
- `POST /jobs/{job_id}/generate`
- `GET /jobs/{job_id}/generate`
- `GET /jobs/{job_id}/generate/image`
- `POST /jobs/{job_id}/critique`
- `GET /jobs/{job_id}/critique`
- `POST /jobs/{job_id}/repair`
- `GET /jobs/{job_id}/repair`

Interactive API documentation is available through FastAPI/Swagger when the server is running.

See `docs/frontend-api.md` for the frontend integration contract.

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

Create `.env` from `.env.example` and configure:

```text
OPENROUTER_API_KEY=...
```

## Run

```powershell
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000/docs
```

for the interactive Swagger API documentation.

## Tests

Run the full local test suite:

```powershell
pytest -q
```

Live provider tests are opt-in:

```powershell
$env:MIDAS_RUN_LIVE_PROVIDER_TEST="1"
pytest -q
```

Without the live-provider flag, live provider tests remain skipped.

## Project Structure

```text
app/
  api/          FastAPI routes and schemas
  contracts/    Typed stage contracts
  providers/    Provider adapters and fake providers
  runtime/      Job state, artifacts and recovery
  stages/       Eye, Brain, Stylist, Engine, Critique and Repair

tests/           Contract, execution, API and recovery tests
docs/            API and source documentation
```

## Runtime Flow

A complete job can progress through the following path:

```text
Job Intake
    ↓
Eye Observation
    ↓
Brain Planning
    ↓
Stylist Planning
    ↓
Engine Compilation
    ↓
Image Generation
    ↓
Independent Critique
    ↓
Bounded Repair
    ↓
Independent Re-critique
    ↓
Pass / Hold
```

Generation and repair preserve the job contract and relevant reference bindings across attempts.

Critique operates independently from generation and determines whether the current output passes or requires bounded correction.

Repair is bounded and does not allow an unbounded generation/correction loop.

## Recovery

Runtime artifacts are persisted locally so the application can reconstruct completed job state after restart.

Recovery restores available job artifacts and completed stage results without re-dispatching completed provider operations.

## Provider Integration

The backend uses provider adapters so workflow stages are separated from provider-specific transport details.

OpenRouter is currently used for live model execution.

Fake providers are included for deterministic contract and execution tests without making live provider calls.
