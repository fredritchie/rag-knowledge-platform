resource "aws_ecr_repository" "this" {
  for_each             = var.repositories
  name                 = "${var.name_prefix}/${each.value}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.force_delete
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = var.kms_key_arn
  }
  image_scanning_configuration { scan_on_push = true }
  tags = var.tags
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name
  policy = jsonencode({ rules = [{
    rulePriority = 1
    description  = "Retain the newest 50 images"
    selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 50 }
    action       = { type = "expire" }
  }] })
}
