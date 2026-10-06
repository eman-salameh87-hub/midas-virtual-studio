# midas-backend

Generalized MIDAS Virtual Studio backend. Architecture A is the engineering baseline. FastAPI is the API shell. OpenRouter is the provider boundary.

This milestone runs one path:

`Phase-0 job → validation → original product image → Eye → OpenRouter → EyeObservation → job readiness`

Living Room is not the product scope. The Eye stage does not select a model. The caller supplies `model_id`. No canonical Eye prompt is bundled.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health check: `http://127.0.0.1:8000/health`

Copy `.env.example` to `.env` before a live provider call. `OPENROUTER_API_KEY` is required only when a job actually calls OpenRouter.

## Temporary live execution

Pass `model_id` on the job. The first temporary live id is `openai/gpt-4.1`. The runtime does not substitute another model.

```json
{
  "model_id": "openai/gpt-4.1",
  "original_product_image": {
    "media_type": "image/png",
    "data_base64": "<base64 bytes>",
    "source_role": "<caller-supplied role>"
  },
  "job": {
    "taxonomy_node_id": "node-1",
    "profile_id": "profile-1",
    "product_role": "hero",
    "references": [],
    "lighting": null,
    "wall_paint": null,
    "floor": null,
    "mood": null,
    "plants": false,
    "human": false,
    "input_condition": null
  }
}
```

`POST /jobs` validates that body and returns job status. `GET /jobs/{job_id}` returns the same job-scoped readiness, including the Eye observation.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The test suite injects a fake provider. It does not call OpenRouter.

## Not in this milestone

Brain, Stylist, compiler, generation, critic, repair, package, catalogue retrieval, model selection, Magnific, LangGraph, n8n, billing, and frontend.
