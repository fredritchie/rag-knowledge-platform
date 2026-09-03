data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "key" {
  #checkov:skip=CKV_AWS_109: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_111: Account-root administration is required in a KMS key policy.
  #checkov:skip=CKV_AWS_356: Resource star means this KMS key in KMS key-policy syntax.
  statement {
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  statement {
    actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${data.aws_region.current.region}.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values   = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/rds/cluster/${var.name}/postgresql"]
    }
  }
}

resource "aws_kms_key" "this" {
  description             = "${var.name} Aurora and credential encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.key.json
  tags                    = var.tags
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.private_subnet_ids
  tags       = merge(var.tags, { Name = var.name })
}

resource "aws_rds_cluster_parameter_group" "this" {
  name   = var.name
  family = "aurora-postgresql16"
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
  parameter {
    name  = "log_statement"
    value = "ddl"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
  tags = var.tags
}

resource "aws_rds_cluster" "this" {
  cluster_identifier                  = var.name
  engine                              = "aurora-postgresql"
  engine_version                      = var.engine_version
  database_name                       = "ragplatform"
  master_username                     = "ragadmin"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = aws_kms_key.this.arn
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [var.security_group_id]
  db_cluster_parameter_group_name     = aws_rds_cluster_parameter_group.this.name
  storage_encrypted                   = true
  kms_key_id                          = aws_kms_key.this.arn
  backup_retention_period             = var.backup_retention_days
  preferred_backup_window             = "02:00-03:00"
  preferred_maintenance_window        = "sun:03:00-sun:04:00"
  enabled_cloudwatch_logs_exports     = ["postgresql"]
  iam_database_authentication_enabled = true
  deletion_protection                 = var.deletion_protection
  skip_final_snapshot                 = var.skip_final_snapshot
  final_snapshot_identifier           = var.skip_final_snapshot ? null : "${var.name}-final"
  copy_tags_to_snapshot               = true
  tags                                = var.tags
  depends_on                          = [aws_cloudwatch_log_group.postgresql]
}

resource "aws_rds_cluster_instance" "this" {
  count                           = var.instance_count
  identifier                      = "${var.name}-${count.index + 1}"
  cluster_identifier              = aws_rds_cluster.this.id
  instance_class                  = var.instance_class
  engine                          = aws_rds_cluster.this.engine
  engine_version                  = aws_rds_cluster.this.engine_version
  publicly_accessible             = false
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.this.arn
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.monitoring.arn
  auto_minor_version_upgrade      = true
  tags                            = var.tags
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "${var.name}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_cloudwatch_log_group" "postgresql" {
  name              = "/aws/rds/cluster/${var.name}/postgresql"
  retention_in_days = max(365, var.log_retention_days)
  kms_key_id        = aws_kms_key.this.arn
  tags              = var.tags
}

data "aws_iam_policy_document" "backup_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["backup.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name               = "${var.name}-backup"
  assume_role_policy = data.aws_iam_policy_document.backup_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_backup_vault" "this" {
  name          = var.name
  kms_key_arn   = aws_kms_key.this.arn
  force_destroy = var.skip_final_snapshot
  tags          = var.tags
}

resource "aws_backup_plan" "this" {
  name = var.name
  rule {
    rule_name         = "daily"
    target_vault_name = aws_backup_vault.this.name
    schedule          = "cron(0 5 * * ? *)"
    lifecycle { delete_after = 35 }
  }
  tags = var.tags
}

resource "aws_backup_selection" "this" {
  name         = var.name
  iam_role_arn = aws_iam_role.backup.arn
  plan_id      = aws_backup_plan.this.id
  resources    = [aws_rds_cluster.this.arn]
}
