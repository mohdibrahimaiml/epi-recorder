# Customer-owned storage (M4)

Every sealed `.epi` belongs in **your** S3-compatible bucket (AWS S3,
Cloudflare R2, MinIO, GCS interoperability mode). EPI Cloud never sees these
bytes and never holds your bucket credentials — it only witnesses hashes
(M1), serves selected runs you push (M3), and shows the health heartbeat
below as vendor-reported.

## Vendor setup (5 minutes)

```bash
export EPI_STORAGE_URL=s3://my-bucket/epi-runs
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...      # or ~/.aws/credentials (AWS_PROFILE)
# Optional:
export EPI_STORAGE_ENDPOINT=https://<account>.r2.cloudflarestorage.com  # R2
# export EPI_STORAGE_ENDPOINT=http://127.0.0.1:9000                    # MinIO
export EPI_STORAGE_REGION=eu-west-1   # default us-east-1
```

From then on every `record()` seal uploads the `.epi` outbox-first (offline
queues locally, `epi cloud storage flush` retries). The gateway case export
does the same. Check it with:

```bash
epi cloud storage test     # writes + re-reads one probe object
epi cloud storage show     # server target + local outbox
epi cloud storage set --url s3://my-bucket/epi-runs --object-lock on
```

Register the bucket (no secrets — those stay in your environment):

```bash
epi cloud storage set --url s3://my-bucket/epi-runs --object-lock on
```

## Write-only bucket policy (AWS example)

The recorder only ever PUTs objects. This policy grants exactly that on one
prefix, nothing else (replace `my-bucket` and `epi-runs`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EpiRecorderWriteOnly",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": ["arn:aws:s3:::my-bucket/epi-runs/*"]
    }
  ]
}
```

Attach it to a dedicated IAM user whose access key you put in
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. The trust page reports what
your recorder last told EPI Cloud — it cannot verify your bucket itself.

## Retention: S3 Object Lock (recommended)

For WORM retention, enable **Object Lock in Compliance mode** on the bucket
(at creation — it cannot be added later) and set a default retention rule
matching your policy (e.g. 7 years). Report it honestly:

```bash
epi cloud storage set --url s3://my-bucket/epi-runs --object-lock on
```

`--object-lock` is **self-attested**: the trust page labels it
"vendor-reported". `off` means you run without Object Lock; `unknown`
(the default) means you have not said.

## What the trust page shows

`storage target configured · last check ok <time> · Object Lock: on/off/unknown
(vendor-reported)`. A missing heartbeat means the recorder never reported —
ask the vendor why, the same way you would for a missing witness entry.

## Limits (read these)

- The bucket holds what the vendor's recorder uploaded. EPI Cloud cannot
  prove completeness — only that these bytes were sealed no later than
  the recorded time (see docs/WITNESS.md).
- If the sealed file moves before a queued upload flushes, the flush fails
  loudly instead of uploading a different file (sha256 is re-checked).
