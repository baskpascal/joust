[doc("Run unit, integration, and end-to-end tests.")]
test:
    uv run --python 3.13 --with pytest==8.4.2 pytest -q tests/

[doc("Run the developer health checks.")]
doctor:
    uv run --python 3.13 python -m hackathon_competitor.cli doctor

[doc("Run lint checks.")]
lint:
    uvx ruff@0.13.1 check hackathon_competitor tests
