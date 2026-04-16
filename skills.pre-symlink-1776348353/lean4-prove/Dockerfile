# Lean4 Compilation Service — Docker image
# Provides a persistent 20-worker LeanServerPool via HTTP API.
#
# Build:
#   docker build -t lean4-prove-service .
#
# Run:
#   docker run -p 8604:8604 lean4-prove-service
#
# First startup downloads Lean REPL binary + builds Mathlib (~5-10 min).
# Subsequent starts use the lake cache (near-instant).

FROM python:3.13-slim

# System deps for lean-interact (git, curl for elan/lake)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install elan (Lean version manager) — needed by lean-interact
# Pin to v4.28.0: Mathlib not yet released for v4.29.0 (as of 2026-03-29)
RUN curl -sSf https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | bash -s -- -y --default-toolchain leanprover/lean4:v4.28.0
ENV PATH="/root/.elan/bin:${PATH}"

WORKDIR /app

# Copy dependency spec and install Python deps
COPY pyproject.toml /app/
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] httpx pydantic loguru \
    lean-interact>=0.11.1 \
    python-arango>=7.0.0 \
    typer>=0.9.0 \
    python-dotenv>=1.2.1

# Copy service code
COPY compiler.py /app/
COPY service.py /app/

# Pre-build Mathlib at image build time so startup is fast.
# This creates the lake cache that lean-interact reuses.
RUN python -c "\
from compiler import ParallelCompiler; \
c = ParallelCompiler(n_workers=1, timeout=300); \
r = c.compile_one('theorem t : 1+1=2 := by omega'); \
print(f'Warmup: success={r.success}'); \
c.close()" || echo "Warmup failed (will retry at runtime)"

ENV LEAN4_SERVICE_PORT=8604 \
    LEAN4_WORKERS=20 \
    LEAN4_TIMEOUT=60 \
    LEAN4_REQUIRE=mathlib

EXPOSE 8604

HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD python -c "import httpx; r=httpx.get('http://127.0.0.1:8604/health',timeout=5); assert r.status_code==200"

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8604"]
