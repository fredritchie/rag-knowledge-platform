# Security Foundation

Phase 0/1 security controls focus on safe local ingestion boundaries:

- Do not execute content extracted from PDFs.
- Treat document text as untrusted data.
- Reject encrypted PDFs until an explicit secure password workflow exists.
- Preserve checksums and processing metadata for traceability.
- Do not commit runtime data or source PDFs to Git.
- Avoid logging raw sensitive document content.

Future phases will add tenant isolation, Cognito, document ACLs, prompt-injection controls, KMS, Secrets Manager, NetworkPolicy, signed images, and policy-as-code.
