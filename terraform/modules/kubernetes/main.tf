data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "secrets_key" {
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
      values   = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/${var.name}/cluster"]
    }
  }
}

resource "aws_kms_key" "secrets" {
  description             = "${var.name} Kubernetes secret encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.secrets_key.json
  tags                    = var.tags
}

resource "aws_cloudwatch_log_group" "cluster" {
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = max(365, var.log_retention_days)
  kms_key_id        = aws_kms_key.secrets.arn
  tags              = var.tags
}

resource "aws_eks_cluster" "this" {
  name     = var.name
  role_arn = var.cluster_role_arn
  version  = var.kubernetes_version
  vpc_config {
    subnet_ids              = var.private_subnet_ids
    security_group_ids      = [var.security_group_id]
    endpoint_private_access = true
    endpoint_public_access  = false
  }
  encryption_config {
    provider { key_arn = aws_kms_key.secrets.arn }
    resources = ["secrets"]
  }
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]
  access_config { authentication_mode = "API_AND_CONFIG_MAP" }
  tags       = var.tags
  depends_on = [aws_cloudwatch_log_group.cluster]
}

resource "aws_eks_addon" "pod_identity_agent" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "eks-pod-identity-agent"
  resolve_conflicts_on_update = "PRESERVE"
  tags                        = var.tags
}

resource "aws_eks_addon" "vpc_cni" {
  cluster_name                = aws_eks_cluster.this.name
  addon_name                  = "vpc-cni"
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "PRESERVE"
  tags                        = var.tags
}

resource "aws_eks_node_group" "general" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "general"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.general_instance_types
  capacity_type   = "ON_DEMAND"
  scaling_config {
    desired_size = var.general_desired_size
    min_size     = 1
    max_size     = max(3, var.general_desired_size * 2)
  }
  update_config { max_unavailable_percentage = 33 }
  labels = { workload = "general" }
  taint {
    key    = "node.cilium.io/agent-not-ready"
    value  = "true"
    effect = "NO_EXECUTE"
  }
  tags       = var.tags
  depends_on = [aws_eks_addon.vpc_cni]
}

resource "aws_eks_node_group" "qdrant" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "qdrant"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.qdrant_instance_types
  capacity_type   = "ON_DEMAND"
  scaling_config {
    desired_size = var.qdrant_desired_size
    min_size     = 1
    max_size     = max(3, var.qdrant_desired_size + 2)
  }
  update_config { max_unavailable = 1 }
  labels = { workload = "qdrant" }
  taint {
    key    = "dedicated"
    value  = "qdrant"
    effect = "NO_SCHEDULE"
  }
  taint {
    key    = "node.cilium.io/agent-not-ready"
    value  = "true"
    effect = "NO_EXECUTE"
  }
  tags       = var.tags
  depends_on = [aws_eks_addon.vpc_cni]
}

resource "aws_eks_node_group" "ingestion" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "ingestion"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.ingestion_instance_types
  capacity_type   = "ON_DEMAND"
  scaling_config {
    desired_size = var.ingestion_desired_size
    min_size     = 1
    max_size     = max(3, var.ingestion_desired_size * 2)
  }
  update_config { max_unavailable_percentage = 33 }
  labels = { workload = "ingestion" }
  taint {
    key    = "dedicated"
    value  = "ingestion"
    effect = "NO_SCHEDULE"
  }
  taint {
    key    = "node.cilium.io/agent-not-ready"
    value  = "true"
    effect = "NO_EXECUTE"
  }
  tags       = var.tags
  depends_on = [aws_eks_addon.vpc_cni]
}

resource "aws_eks_node_group" "gpu" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "gpu"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = var.gpu_instance_types
  capacity_type   = "ON_DEMAND"
  ami_type        = "AL2023_x86_64_NVIDIA"
  scaling_config {
    desired_size = var.gpu_desired_size
    min_size     = 0
    max_size     = max(2, var.gpu_desired_size + 1)
  }
  update_config { max_unavailable = 1 }
  labels = { workload = "gpu", accelerator = "nvidia" }
  taint {
    key    = "nvidia.com/gpu"
    value  = "true"
    effect = "NO_SCHEDULE"
  }
  taint {
    key    = "node.cilium.io/agent-not-ready"
    value  = "true"
    effect = "NO_EXECUTE"
  }
  tags       = var.tags
  depends_on = [aws_eks_addon.vpc_cni]
}
