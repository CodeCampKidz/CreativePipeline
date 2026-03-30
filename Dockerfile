# ── Stage 1: Test ──────────────────────────────────────────────────────
FROM python:3.11-slim AS test

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY tests/ tests/
COPY data/ data/
COPY pyproject.toml .

# Run test suite — build fails if any test fails
# Tests re-run automatically when src/, tests/, or data/ change (layer cache invalidation)
RUN python -m pytest tests/ -v --tb=short \
    && echo "ALL_TESTS_PASSED" > /tmp/.tests_passed

# ── Stage 2: Production ───────────────────────────────────────────────
FROM python:3.11-slim AS production

WORKDIR /app

# Force dependency on test stage — build fails if tests failed
COPY --from=test /tmp/.tests_passed /tmp/.tests_passed

# Non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only application code and data (no tests in prod image)
COPY src/ src/
COPY data/ data/
COPY pyproject.toml .

# Create runtime directories owned by appuser
RUN mkdir -p data/output data/uploads && \
    chown -R appuser:appuser /app && \
    rm /tmp/.tests_passed

USER appuser

# Health check for web mode
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()" || exit 1

EXPOSE 8080

ENTRYPOINT ["python", "-m", "src.cli"]
CMD ["web"]
