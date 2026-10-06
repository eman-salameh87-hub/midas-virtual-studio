# Sources policy

This repository is the generalized MIDAS Virtual Studio backend. Architecture A is the engineering baseline. Living Room material is evidence of an earlier case, not the product scope.

## What this milestone accepts as evidence

The Phase-0 job fields stored by this backend are the fields already evidenced for that contract:

- `taxonomy_node_id`
- `profile_id`
- `product_role`
- `references` (`id`, `role`, optional `filename`, `sha256`, `media_type`)
- `lighting`
- `wall_paint`
- `floor`
- `mood`
- `plants`
- `human`
- `input_condition`

`EyeObservation` keeps the evidenced structure:

- `source_role`
- `category_candidates` (`name`, `confidence_basis`)
- `visible_features`
- `observed_facts`
- `unknowns`
- `ambiguities`
- `conflicts`
- `parsing_limits`

Unresolved contract fields are rejected. They are not given defaults, enums, or stand-in values.

## What this repository does not import

- Scraped MIDAS website pages or extracted client catalogs
- Historical proof runners and temporary execution runners
- A model-selection engine, model registry, or universal model policy
- Living Room historical prompts, including any prompt treated as a generalized system prompt
- A Brain prompt, Stylist prompt, or other stage prompt
- Magnific, LangGraph, n8n, billing, tokenization, or a frontend

No canonical generalized Eye prompt was available as a source. This repository does not invent one. The Eye request carries the original product image, the supplied `source_role`, and the Eye observation schema.

## Provider boundary

OpenRouter is called only from `app/providers/openrouter.py`. The Eye stage does not select a model. The caller supplies `model_id`. For the first temporary live execution, that explicit id is `openai/gpt-4.1`.

## Scope stop

This milestone ends at job validation, the original product image, Eye, OpenRouter, `EyeObservation`, and job-scoped readiness. Later stages are out of scope.
