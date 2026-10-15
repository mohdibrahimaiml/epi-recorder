"""M4 interop: my SigV4 sink against real S3-speaking servers.

Two modes, same file:
- Local/default: spins up moto_server (needs `pip install "moto[server]"`,
  else the file skips). Moto verifies every SigV4 signature independently.
- CI MinIO: set EPI_TEST_S3_ENDPOINT (+ACCESS/+SECRET/+BUCKET); the MinIO
  service job runs this file, including the 100-seal acceptance.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

moto_server = shutil.which("moto_server")
boto3 = pytest.importorskip("boto3", reason="pip install boto3 for interop tests")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def s3():
    """(endpoint, access, secret, bucket, region) for this run."""
    endpoint = os.getenv("EPI_TEST_S3_ENDPOINT")
    if endpoint:
        yield {
            "endpoint": endpoint.rstrip("/"),
            "access": os.environ["EPI_TEST_S3_ACCESS"],
            "secret": os.environ["EPI_TEST_S3_SECRET"],
            "bucket": os.environ.get("EPI_TEST_S3_BUCKET", "epi-interop"),
            "region": os.environ.get("EPI_TEST_S3_REGION", "us-east-1"),
        }
        return
    if not moto_server:
        pytest.skip("moto_server not installed")
    port = _free_port()
    proc = subprocess.Popen(
        [moto_server, "-H", "127.0.0.1", "-p", str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        endpoint = f"http://127.0.0.1:{port}"
        deadline = time.time() + 60
        import urllib.request

        while True:
            try:
                urllib.request.urlopen(f"{endpoint}/moto-api/", timeout=2)
                break
            except Exception:
                if time.time() > deadline or proc.poll() is not None:
                    pytest.skip("moto_server did not start")
                time.sleep(0.5)
        yield {"endpoint": endpoint, "access": "testing", "secret": "testing",
               "bucket": "epi-interop", "region": "us-east-1"}
    finally:
        proc.terminate()


@pytest.fixture()
def configured(s3, monkeypatch, tmp_path: Path):
    import boto3 as _boto3

    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", s3["access"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", s3["secret"])
    monkeypatch.setenv("EPI_STORAGE_URL", f"s3://{s3['bucket']}/runs")
    monkeypatch.setenv("EPI_STORAGE_ENDPOINT", s3["endpoint"])
    monkeypatch.setenv("EPI_STORAGE_REGION", s3["region"])
    client = _boto3.client(
        "s3", endpoint_url=s3["endpoint"], region_name=s3["region"],
        aws_access_key_id=s3["access"], aws_secret_access_key=s3["secret"],
    )
    try:
        client.create_bucket(Bucket=s3["bucket"])
    except Exception as exc:
        if "BucketAlreadyOwnedByYou" not in str(exc):
            raise
    return s3, client


def test_put_get_roundtrip(configured):
    import boto3 as _boto3  # noqa: F401  (importorskip above guarantees presence)

    s3, client = configured
    from epi_core.storage_sink import parse_storage_url, put_object, load_credentials

    target = parse_storage_url(f"s3://{s3['bucket']}/runs", endpoint=s3["endpoint"], region=s3["region"])
    body = b"interop-bytes-" + bytes(range(256))
    put_object(body, "runs/probe.bin", target, load_credentials())
    back = client.get_object(Bucket=s3["bucket"], Key="runs/probe.bin")["Body"].read()
    assert back == body


@pytest.mark.slow
def test_100_seals_land_with_matching_sha256(configured, tmp_path: Path):
    from epi_recorder import record

    s3, client = configured
    for i in range(100):
        out = tmp_path / f"run-{i:03d}.epi"
        with record(str(out), storage_url=f"s3://{s3['bucket']}/runs") as epi:
            epi.log_step("llm.request", {"content": f"hello {i}"})
        key = f"runs/{hashlib.sha256(out.read_bytes()).hexdigest()}.epi"
        back = client.get_object(Bucket=s3["bucket"], Key=key)["Body"].read()
        assert back == out.read_bytes(), f"object {i} bytes differ"
