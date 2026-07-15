from __future__ import annotations


def tool_payload(name: str, description: str, params: dict[str, str]) -> dict:
    return {"id": name, "name": name, "description": description, "params": params}


def get_object(bucket: str, key: str) -> dict:
    return tool_payload("s3.get_object", f"Read {bucket}/{key}", {"bucket": bucket, "key": key})
