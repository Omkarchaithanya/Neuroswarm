"""S3 MCP server — REAL implementation (FastMCP + boto3).

Replaces the fake stub that only echoed its own tool description back.
Auth: export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (standard AWS env).
Optional: AWS_REGION (default us-east-1), AWS_SESSION_TOKEN, S3_ENDPOINT_URL
(for MinIO / R2 / other S3-compatible endpoints).

Run: python server.py          (stdio, for local MCP clients)
Test: npx @modelcontextprotocol/inspector python server.py
"""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastmcp import FastMCP

REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL") or None
MAX_BODY_BYTES = 256 * 1024

mcp = FastMCP("s3")


def _client():
    kwargs: dict[str, Any] = {"region_name": REGION}
    if ENDPOINT_URL:
        kwargs["endpoint_url"] = ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def _map_client_error(exc: ClientError, *, bucket: str, key: str | None = None) -> ValueError:
    code = (exc.response.get("Error") or {}).get("Code", "")
    status = (exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
    where = f"{bucket}/{key}" if key else bucket
    if code in ("NoSuchKey", "404", "NotFound") or status == 404:
        return ValueError(f"Not found: s3://{where}. Check bucket/key spelling and that the object exists.")
    if code in ("AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403") or status == 403:
        return ValueError(
            f"Access denied for s3://{where}. Check AWS credentials, bucket policy, and IAM permissions."
        )
    if code in ("SlowDown", "Throttling", "RequestLimitExceeded", "503") or status == 429:
        return ValueError("S3 rate limit / throttling hit. Back off and retry; check account request quotas.")
    if code == "NoSuchBucket":
        return ValueError(f"Bucket not found: {bucket}. Check the name and region/endpoint.")
    return ValueError(f"S3 error ({code or status}): {exc}")


def _run_sync(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except ClientError as exc:
        bucket = kwargs.get("Bucket") or (args[0] if args else "?")
        key = kwargs.get("Key")
        raise _map_client_error(exc, bucket=str(bucket), key=key) from None
    except BotoCoreError as exc:
        raise ValueError(
            f"S3 client error: {exc}. Check network, AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, "
            "and S3_ENDPOINT_URL if using a compatible endpoint."
        ) from None


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_object(bucket: str, key: str) -> dict[str, Any]:
    """Read an object from S3 (or an S3-compatible endpoint).

    Args:
        bucket: S3 bucket name
        key: object key
    """
    if not bucket or not key:
        raise ValueError("bucket and key are required")

    def _get() -> dict[str, Any]:
        resp = _run_sync(_client().get_object, Bucket=bucket, Key=key)
        body = resp["Body"].read(MAX_BODY_BYTES + 1)
        truncated = len(body) > MAX_BODY_BYTES
        if truncated:
            body = body[:MAX_BODY_BYTES]
        content_type = resp.get("ContentType") or "application/octet-stream"
        try:
            text = body.decode("utf-8")
            payload: dict[str, Any] = {"encoding": "utf-8", "body": text}
        except UnicodeDecodeError:
            payload = {
                "encoding": "base64",
                "body": base64.b64encode(body).decode("ascii"),
            }
        return {
            "bucket": bucket,
            "key": key,
            "content_type": content_type,
            "content_length": resp.get("ContentLength"),
            "etag": (resp.get("ETag") or "").strip('"'),
            "last_modified": resp["LastModified"].isoformat() if resp.get("LastModified") else None,
            "truncated": truncated,
            **payload,
        }

    return await asyncio.to_thread(_get)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def put_object(bucket: str, key: str, body: str, content_type: str = "text/plain") -> dict[str, Any]:
    """Upload/overwrite an object (UTF-8 text body).

    Args:
        bucket: S3 bucket name
        key: object key
        body: UTF-8 text to store
        content_type: Content-Type header (default text/plain)
    """
    if not bucket or not key:
        raise ValueError("bucket and key are required")

    def _put() -> dict[str, Any]:
        data = body.encode("utf-8")
        resp = _run_sync(
            _client().put_object,
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return {
            "bucket": bucket,
            "key": key,
            "etag": (resp.get("ETag") or "").strip('"'),
            "bytes": len(data),
            "content_type": content_type,
        }

    return await asyncio.to_thread(_put)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_objects_v2(bucket: str, prefix: str = "", max_keys: int = 100) -> dict[str, Any]:
    """List objects in a bucket (optionally under a prefix).

    Args:
        bucket: S3 bucket name
        prefix: key prefix filter (default: all keys)
        max_keys: max keys to return (1-1000)
    """
    if not bucket:
        raise ValueError("bucket is required")
    max_keys = max(1, min(int(max_keys), 1000))

    def _list() -> dict[str, Any]:
        resp = _run_sync(
            _client().list_objects_v2,
            Bucket=bucket,
            Prefix=prefix or "",
            MaxKeys=max_keys,
        )
        contents = [
            {
                "key": obj["Key"],
                "size": obj.get("Size"),
                "etag": (obj.get("ETag") or "").strip('"'),
                "last_modified": obj["LastModified"].isoformat() if obj.get("LastModified") else None,
            }
            for obj in resp.get("Contents") or []
        ]
        return {
            "bucket": bucket,
            "prefix": prefix or "",
            "key_count": len(contents),
            "is_truncated": bool(resp.get("IsTruncated")),
            "objects": contents,
        }

    return await asyncio.to_thread(_list)


if __name__ == "__main__":
    mcp.run()
