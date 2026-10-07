# MIDAS Virtual Studio

Clean MIDAS backend for furniture and product categories.

The implementation baseline is Architecture A: the application owns intake, the immutable job contract, the durable state machine, specialist services, the provider gateway, independent review, bounded correction, and package release.

`GET /health` returns `{"status": "ok"}`. The public jobs API is under `/api/v1`. `POST /api/v1/jobs` freezes a Phase-0 contract. Image references must include `content_base64`; bytes are stored on the in-memory job, not on the frozen identity contract. `POST /api/v1/jobs/{job_id}/eye` reconstructs EyeInput from that job and runs Eye with a caller-supplied `model_id`. Normal tests use a fake provider. A live OpenRouter path exists in `tests/test_live_eye_provider.py` and `tests/test_live_api_eye.py` and runs only when `MIDAS_RUN_LIVE_PROVIDER_TEST=1`. Later stages are not implemented.

`MIDAS_SOURCES/` is the specification and evidence corpus. See [docs/SOURCES.md](docs/SOURCES.md). Do not treat Living Room history or historical provider ids as the production workflow.
