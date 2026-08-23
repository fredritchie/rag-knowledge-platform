# Event ingestion Terraform module

This module enables S3-to-EventBridge delivery, filters canonical object events into an encrypted
SQS queue, configures an encrypted DLQ and redrive policy, creates a DLQ CloudWatch alarm, and
publishes a least-scope worker IAM policy. Pass the existing bucket name and ARN; attach the
`worker_policy_arn` output to the API/worker runtime role. Configure `alarm_actions` with an SNS
topic or another CloudWatch alarm action.

Only one `aws_s3_bucket_notification` resource should manage a bucket. If another stack already
owns that resource, move the `eventbridge = true` setting there and disable/remove the resource
from this module before applying it.
