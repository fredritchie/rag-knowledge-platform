from __future__ import annotations

from typing import Any

import boto3

from rag_platform.config import StorageSettings


class S3Storage:
    def __init__(self, config: StorageSettings):
        self.config = config
        self._client = None

    @property
    def client(self):
        # Credential discovery is intentionally deferred so S3 outages do not prevent liveness.
        if self._client is None:
            self._client = boto3.client(
                "s3", region_name=self.config.region, endpoint_url=self.config.endpoint_url
            )
        return self._client

    def create_upload(self, storage_key: str, content_type: str) -> dict[str, Any]:
        fields: dict[str, str] = {
            "Content-Type": content_type,
            "x-amz-server-side-encryption": self.config.server_side_encryption,
        }
        conditions: list[Any] = [
            {"Content-Type": content_type},
            {"x-amz-server-side-encryption": self.config.server_side_encryption},
        ]
        if self.config.server_side_encryption == "aws:kms" and self.config.kms_key_id:
            fields["x-amz-server-side-encryption-aws-kms-key-id"] = self.config.kms_key_id
            conditions.append(
                {"x-amz-server-side-encryption-aws-kms-key-id": self.config.kms_key_id}
            )
        return self.client.generate_presigned_post(
            Bucket=self.config.bucket,
            Key=storage_key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=self.config.upload_expiry_seconds,
        )
