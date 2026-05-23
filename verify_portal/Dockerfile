# EPI Verify Portal — Production Docker Image
# Build: docker build -f verify_portal/Dockerfile -t epi-verify .
# Run:  docker run -p 8000:8000 -e EPI_ATTESTATION_PRIVATE_KEY=<key> epi-verify

FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[gateway]"

# Copy application code
COPY epi_core/ ./epi_core/
COPY epi_cli/ ./epi_cli/
COPY verify_portal/ ./verify_portal/

# Create non-root user for security
RUN useradd -m -u 1000 epi && chown -R epi:epi /app
USER epi

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["python", "-m", "verify_portal.main"]
