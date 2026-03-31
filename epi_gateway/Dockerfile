# Lightweight Python Image
FROM python:3.10-slim

# Prevent python buffering
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies if needed (e.g. for crypto)
# RUN apt-get update && apt-get install -y gcc

# Install dependencies
# We include the gateway extra so hosted sharing can use S3/R2 when configured.
RUN pip install --no-cache-dir fastapi uvicorn[standard] "epi-recorder[gateway]"

# Copy Gateway Code
COPY . /app/epi_gateway

# Expose Sidecar Port
EXPOSE 8000

# Run the Sidecar
CMD ["uvicorn", "epi_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
