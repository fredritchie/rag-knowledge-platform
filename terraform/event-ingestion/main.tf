module "event_ingestion" {
  source = "../modules/event_ingestion"

  name                       = var.name
  bucket_name                = var.bucket_name
  bucket_arn                 = var.bucket_arn
  enable_bucket_versioning   = false
  object_prefix              = "tenants/"
  visibility_timeout_seconds = 900
  max_receive_count          = 5
  alarm_actions              = var.alarm_actions
  tags                       = var.tags
}

# The Phase 8 document-storage root owns S3 versioning and the EC2 instance
# profile. This stack adds only the Phase 9 consumer permissions to that role.
resource "aws_iam_role_policy_attachment" "event_worker" {
  role       = var.worker_role_name
  policy_arn = module.event_ingestion.worker_policy_arn
}
