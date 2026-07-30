"""S3 MCP server — FastMCP + boto3.

Auth: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY; optional AWS_REGION, S3_ENDPOINT_URL.
Tool names match templates/mcp-servers/s3/tools/*.tool.yaml IDs.
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
    """Read an object from S3 (or an S3-compatible endpoint)."""
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
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def put_object(
    bucket: str,
    key: str,
    body: str,
    content_type: str = "text/plain",
    overwrite: bool = False,
    if_match_etag: str | None = None,
) -> dict[str, Any]:
    """Upload an object. Refuses overwrite unless overwrite=true (destructive)."""
    if not bucket or not key:
        raise ValueError("bucket and key are required")

    def _put() -> dict[str, Any]:
        client = _client()
        exists = False
        try:
            client.head_object(Bucket=bucket, Key=key)
            exists = True
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            status = (exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            if code in ("404", "NoSuchKey", "NotFound") or status == 404:
                exists = False
            else:
                raise _map_client_error(exc, bucket=bucket, key=key) from None

        if exists and not overwrite:
            raise ValueError(
                f"Object s3://{bucket}/{key} already exists. Pass overwrite=true to replace (destructive)."
            )

        data = body.encode("utf-8")
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if not exists:
            kwargs["IfNoneMatch"] = "*"
        elif overwrite and if_match_etag:
            kwargs["IfMatch"] = if_match_etag.strip('"')
        try:
            resp = client.put_object(**kwargs)
        except TypeError:
            kwargs.pop("IfNoneMatch", None)
            kwargs.pop("IfMatch", None)
            resp = client.put_object(**kwargs)
        except ClientError as exc:
            raise _map_client_error(exc, bucket=bucket, key=key) from None
        return {
            "bucket": bucket,
            "key": key,
            "etag": (resp.get("ETag") or "").strip('"'),
            "version_id": resp.get("VersionId"),
            "bytes": len(data),
            "content_type": content_type,
            "overwrite": bool(exists and overwrite),
            "if_match_etag": if_match_etag,
            "audit": {"action": "put_object", "bucket": bucket, "key": key},
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
async def list_objects(bucket: str, prefix: str = "", max_keys: int = 100) -> dict[str, Any]:
    """List objects in a bucket (ListObjectsV2 API)."""
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


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def list_objects_v2(bucket: str, prefix: str = "", max_keys: int = 100) -> dict[str, Any]:
    """Legacy alias for list_objects."""
    return await list_objects(bucket=bucket, prefix=prefix, max_keys=max_keys)


@mcp.tool(
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def head_object(bucket: str, key: str) -> dict[str, Any]:
    """Fetch object metadata without downloading the body."""
    if not bucket or not key:
        raise ValueError("bucket and key are required")

    def _head() -> dict[str, Any]:
        resp = _run_sync(_client().head_object, Bucket=bucket, Key=key)
        return {
            "bucket": bucket,
            "key": key,
            "content_type": resp.get("ContentType"),
            "content_length": resp.get("ContentLength"),
            "etag": (resp.get("ETag") or "").strip('"'),
            "last_modified": resp["LastModified"].isoformat() if resp.get("LastModified") else None,
        }

    return await asyncio.to_thread(_head)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def delete_object(bucket: str, key: str) -> dict[str, Any]:
    """Delete an object."""
    if not bucket or not key:
        raise ValueError("bucket and key are required")

    def _del() -> dict[str, Any]:
        _run_sync(_client().delete_object, Bucket=bucket, Key=key)
        return {"bucket": bucket, "key": key, "deleted": True}

    return await asyncio.to_thread(_del)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def copy_object(
    source_bucket: str,
    source_key: str,
    dest_bucket: str,
    dest_key: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copy an object within S3. Refuses dest overwrite unless overwrite=true."""
    if not all([source_bucket, source_key, dest_bucket, dest_key]):
        raise ValueError("source_bucket, source_key, dest_bucket, dest_key are required")

    def _copy() -> dict[str, Any]:
        client = _client()
        exists = False
        try:
            client.head_object(Bucket=dest_bucket, Key=dest_key)
            exists = True
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code", "")
            status = (exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            if code in ("404", "NoSuchKey", "NotFound") or status == 404:
                exists = False
            else:
                raise _map_client_error(exc, bucket=dest_bucket, key=dest_key) from None
        if exists and not overwrite:
            raise ValueError(
                f"Destination s3://{dest_bucket}/{dest_key} exists. Pass overwrite=true (destructive)."
            )
        kwargs: dict[str, Any] = {
            "Bucket": dest_bucket,
            "Key": dest_key,
            "CopySource": {"Bucket": source_bucket, "Key": source_key},
        }
        if not exists:
            # Race-safe create: fail if dest appears between head and copy
            kwargs["CopySourceIfNoneMatch"] = "*"  # may be ignored by some backends
        try:
            resp = client.copy_object(**kwargs)
        except TypeError:
            kwargs.pop("CopySourceIfNoneMatch", None)
            # boto3 uses MetadataDirective etc.; try IfNoneMatch via extra args where supported
            try:
                resp = client.copy_object(
                    Bucket=dest_bucket,
                    Key=dest_key,
                    CopySource={"Bucket": source_bucket, "Key": source_key},
                    **({"IfNoneMatch": "*"} if not exists else {}),
                )
            except TypeError:
                resp = client.copy_object(
                    Bucket=dest_bucket,
                    Key=dest_key,
                    CopySource={"Bucket": source_bucket, "Key": source_key},
                )
        except ClientError as exc:
            raise _map_client_error(exc, bucket=dest_bucket, key=dest_key) from None
        copy_result = resp.get("CopyObjectResult") or {}
        return {
            "source": f"s3://{source_bucket}/{source_key}",
            "dest": f"s3://{dest_bucket}/{dest_key}",
            "copied": True,
            "overwrite": bool(exists and overwrite),
            "etag": (copy_result.get("ETag") or resp.get("ETag") or "").strip('"') or None,
            "version_id": resp.get("VersionId"),
            "audit": {
                "action": "copy_object",
                "dest_bucket": dest_bucket,
                "dest_key": dest_key,
                "source_bucket": source_bucket,
                "source_key": source_key,
            },
        }

    return await asyncio.to_thread(_copy)


@mcp.tool(
    annotations={
        # put_object presigns write; keep readOnlyHint false so callers do not trust RO.
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def presign_url(
    bucket: str,
    key: str,
    expires_in: int = 3600,
    method: str = "get_object",
) -> dict[str, Any]:
    """Generate a presigned URL. put_object presigns are destructive (approval-gated)."""
    if not bucket or not key:
        raise ValueError("bucket and key are required")
    expires_in = max(1, min(int(expires_in), 7 * 24 * 3600))
    client_method = method if method in {"get_object", "put_object"} else "get_object"

    def _presign() -> dict[str, Any]:
        url = _client().generate_presigned_url(
            ClientMethod=client_method,
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return {
            "bucket": bucket,
            "key": key,
            "method": client_method,
            "expires_in": expires_in,
            "url": url,
            "destructive": client_method == "put_object",
            "read_only": client_method == "get_object",
        }

    return await asyncio.to_thread(_presign)


if __name__ == "__main__":
    mcp.run()
