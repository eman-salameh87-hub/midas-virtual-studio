# MIDAS sources

`MIDAS_SOURCES/` is a read-only corpus. The backend does not modify, move, or scrape it, and it does not call a MIDAS website.

The implementation baseline is Architecture A from the canonical specification:

Client → Intake API → immutable job contract → durable state machine → specialist services → provider gateway → independent review → bounded correction → package release.

The 21 MIDAS responsibilities are logical responsibilities. They are not 21 agents, 21 models, or 21 fixed runtime steps.

## canonical

`MIDAS_SOURCES/canonical/` is the primary MIDAS specification. Architecture A, the responsibility crosswalk, and the shared north star live here. When a later milestone defines contracts or stage behavior, this directory is the specification to follow.

## evidence

`MIDAS_SOURCES/evidence/` is historical implementation and run evidence. It records what was tried, reviewed, or retained. It is not a template for a new workflow, a database, or a model registry.

Living Room material in this directory is historical execution evidence only. It must not become a Living-Room-specific workflow. The backend is generalized across furniture and product categories.

Magnific material is historical provider evidence only. It is not the image-generation provider for this backend. Live image generation uses the OpenRouter Image API. The default image model in this implementation is `google/gemini-3.1-flash-image`. Planning stages default to `openai/gpt-4.1`.

Historical provider names and model ids found in evidence are not automatically a production registry. A caller may send an allowed `model_id`. Generate still has to match the model compiled onto the job.

## handoff

`MIDAS_SOURCES/handoff/` is transfer, recovery, and project-status information. It records what was inspected, what was transferred, and what remained unverified. It does not launch or certify a pipeline, and it does not replace the canonical specification.
