# syntax=docker/dockerfile:1
#
# EPI evidence MCP server — stdio transport.
#
#   docker build -t epi-recorder-mcp .
#   docker run -i --rm epi-recorder-mcp      # MCP over stdin/stdout
#
# The container starts with no credentials and no network access: `initialize`,
# `tools/list` and `prompts/list` all answer offline. The only thing that wants
# a key is `epi_seal_record`, and the server generates its Ed25519 key under
# EPI_MCP_KEYS_DIR on first use (see docs/MCP-DOCKER.md).

FROM python:3.12-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Isolated install: only the venv is copied into the runtime image, so the
# source tree and the build toolchain never reach the final layer.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /src
COPY . .

# ".[mcp]" is the server's own runtime extra (the mcp SDK). Dev and test
# extras are deliberately not installed.
RUN pip install ".[mcp]"


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}" \
    HOME=/home/app \
    EPI_MCP_KEYS_DIR=/home/app/.epi/keys

COPY --from=build /opt/venv /opt/venv

# Non-root, with a writable home so the signing key and temporary seal
# directories have somewhere to live. No apt packages are added: the wheel
# needs no compiler, and the base image already has useradd.
RUN useradd --create-home --uid 10001 --shell /bin/false app \
 && mkdir -p "$EPI_MCP_KEYS_DIR" \
 && chown -R app:app /home/app

USER app
WORKDIR /home/app

ENTRYPOINT ["epi-mcp"]
