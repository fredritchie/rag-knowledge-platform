# Drive sync IAM module

Creates the least-scope IAM policy for `rag-sync-worker`: read the explicitly listed Google OAuth
secrets, write only below the canonical Drive S3 prefix, and send Drive deletion events to the
shared ingestion queue. Attach `policy_arn` to the sync worker runtime role.
