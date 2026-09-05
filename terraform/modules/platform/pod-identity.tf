data "aws_iam_policy_document" "pod_identity_assume" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession"]
    principals {
      type        = "Service"
      identifiers = ["pods.eks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "workers" {
  name               = "${local.name}-workers"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "workers" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [module.documents.bucket_arn]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${module.documents.bucket_arn}/*"]
  }
  statement {
    actions = [
      "sqs:ChangeMessageVisibility",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ReceiveMessage",
      "sqs:SendMessage",
    ]
    resources = [module.queues.queue_arn]
  }
  statement {
    actions = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [
      module.documents.kms_key_arn,
      module.queues.kms_key_arn,
    ]
  }
}

resource "aws_iam_role_policy" "workers" {
  name   = "data-plane"
  role   = aws_iam_role.workers.id
  policy = data.aws_iam_policy_document.workers.json
}

resource "aws_eks_pod_identity_association" "workers" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "rag-platform"
  service_account = "rag-platform-workers"
  role_arn        = aws_iam_role.workers.arn
}

resource "aws_iam_role" "external_secrets" {
  name               = "${local.name}-external-secrets"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "external_secrets" {
  statement {
    actions = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
    resources = [
      module.iam.runtime_secret_arn,
      module.database.master_user_secret_arn,
    ]
  }
  statement {
    actions = ["kms:Decrypt"]
    resources = [
      module.iam.runtime_kms_key_arn,
      module.database.kms_key_arn,
    ]
  }
}

resource "aws_iam_role_policy" "external_secrets" {
  name   = "read-platform-secrets"
  role   = aws_iam_role.external_secrets.id
  policy = data.aws_iam_policy_document.external_secrets.json
}

resource "aws_eks_pod_identity_association" "external_secrets" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "external-secrets"
  service_account = "external-secrets"
  role_arn        = aws_iam_role.external_secrets.arn
}

resource "aws_iam_role" "keda" {
  name               = "${local.name}-keda"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "keda" {
  statement {
    actions   = ["sqs:GetQueueAttributes", "sqs:GetQueueUrl"]
    resources = [module.queues.queue_arn]
  }
}

resource "aws_iam_role_policy" "keda" {
  name   = "read-ingestion-queue-depth"
  role   = aws_iam_role.keda.id
  policy = data.aws_iam_policy_document.keda.json
}

resource "aws_eks_pod_identity_association" "keda" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "keda"
  service_account = "keda-operator"
  role_arn        = aws_iam_role.keda.arn
}

resource "aws_iam_role" "telemetry" {
  name               = "${local.name}-telemetry"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "telemetry" {
  statement {
    actions   = ["s3:GetBucketLocation", "s3:ListBucket"]
    resources = [module.telemetry.bucket_arn]
  }
  statement {
    actions = [
      "s3:AbortMultipartUpload",
      "s3:DeleteObject",
      "s3:GetObject",
      "s3:ListMultipartUploadParts",
      "s3:PutObject",
    ]
    resources = ["${module.telemetry.bucket_arn}/*"]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = [module.telemetry.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "telemetry" {
  name   = "telemetry-object-storage"
  role   = aws_iam_role.telemetry.id
  policy = data.aws_iam_policy_document.telemetry.json
}

resource "aws_eks_pod_identity_association" "loki" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "monitoring"
  service_account = "loki"
  role_arn        = aws_iam_role.telemetry.arn
}

resource "aws_eks_pod_identity_association" "tempo" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "monitoring"
  service_account = "tempo"
  role_arn        = aws_iam_role.telemetry.arn
}

resource "aws_iam_role" "grafana" {
  name               = "${local.name}-grafana"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "grafana" {
  #checkov:skip=CKV_AWS_355: CloudWatch ListMetrics/GetMetricData and Resource Groups Tagging API reads do not support resource-level ARNs.
  #checkov:skip=CKV_AWS_356: Read-only CloudWatch discovery APIs require Resource "*" by AWS design.
  statement {
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:ListMetrics",
      "tag:GetResources",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "grafana" {
  name   = "read-cloudwatch-metrics"
  role   = aws_iam_role.grafana.id
  policy = data.aws_iam_policy_document.grafana.json
}

resource "aws_eks_pod_identity_association" "grafana" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "monitoring"
  service_account = "grafana"
  role_arn        = aws_iam_role.grafana.arn
}

resource "aws_iam_role" "alertmanager" {
  name               = "${local.name}-alertmanager"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "alertmanager" {
  statement {
    actions   = ["sns:Publish"]
    resources = [module.monitoring.sns_topic_arn]
  }
  statement {
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [module.monitoring.kms_key_arn]
  }
}

resource "aws_iam_role_policy" "alertmanager" {
  name   = "publish-alerts"
  role   = aws_iam_role.alertmanager.id
  policy = data.aws_iam_policy_document.alertmanager.json
}

resource "aws_eks_pod_identity_association" "alertmanager" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "monitoring"
  service_account = "alertmanager"
  role_arn        = aws_iam_role.alertmanager.arn
}

resource "aws_iam_role" "load_balancer_controller" {
  name               = "${local.name}-load-balancer-controller"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "load_balancer_controller" {
  statement {
    actions = [
      "ec2:DescribeAvailabilityZones",
      "ec2:DescribeInstances",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeVpcs",
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeListeners",
      "elasticloadbalancing:DescribeRules",
      "elasticloadbalancing:DescribeTags",
      "elasticloadbalancing:DescribeTargetGroups",
      "elasticloadbalancing:DescribeTargetHealth",
    ]
    resources = ["*"]
  }
  statement {
    actions = [
      "elasticloadbalancing:DeregisterTargets",
      "elasticloadbalancing:ModifyTargetGroup",
      "elasticloadbalancing:RegisterTargets",
    ]
    resources = [module.edge.target_group_arn]
  }
}

resource "aws_iam_role_policy" "load_balancer_controller" {
  name   = "manage-platform-target-group"
  role   = aws_iam_role.load_balancer_controller.id
  policy = data.aws_iam_policy_document.load_balancer_controller.json
}

resource "aws_eks_pod_identity_association" "load_balancer_controller" {
  cluster_name    = module.kubernetes.cluster_name
  namespace       = "kube-system"
  service_account = "aws-load-balancer-controller"
  role_arn        = aws_iam_role.load_balancer_controller.arn
}

resource "aws_iam_role" "ebs_csi" {
  name               = "${local.name}-ebs-csi"
  assume_role_policy = data.aws_iam_policy_document.pod_identity_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "aws_eks_addon" "ebs_csi" {
  cluster_name                = module.kubernetes.cluster_name
  addon_name                  = "aws-ebs-csi-driver"
  resolve_conflicts_on_update = "PRESERVE"
  pod_identity_association {
    role_arn        = aws_iam_role.ebs_csi.arn
    service_account = "ebs-csi-controller-sa"
  }
  tags       = local.tags
  depends_on = [module.kubernetes]
}
