data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "flow_logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogGroups", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.flow_logs.arn}:*"]
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(var.tags, { Name = var.name })
}

resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name}-default-deny" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name}-igw" })
}

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.this.id
  availability_zone       = var.availability_zones[count.index]
  cidr_block              = var.public_subnet_cidrs[count.index]
  map_public_ip_on_launch = false
  tags = merge(var.tags, {
    Name                     = "${var.name}-public-${var.availability_zones[count.index]}"
    "kubernetes.io/role/elb" = "1"
  })
}

resource "aws_subnet" "private" {
  count                   = 3
  vpc_id                  = aws_vpc.this.id
  availability_zone       = var.availability_zones[count.index]
  cidr_block              = var.private_subnet_cidrs[count.index]
  map_public_ip_on_launch = false
  tags = merge(var.tags, {
    Name                              = "${var.name}-private-${var.availability_zones[count.index]}"
    "kubernetes.io/role/internal-elb" = "1"
  })
}

resource "aws_eip" "nat" {
  count      = var.single_nat_gateway ? 1 : 3
  domain     = "vpc"
  tags       = merge(var.tags, { Name = "${var.name}-nat-${count.index + 1}" })
  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count         = var.single_nat_gateway ? 1 : 3
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = merge(var.tags, { Name = "${var.name}-nat-${count.index + 1}" })
  depends_on    = [aws_internet_gateway.this]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(var.tags, { Name = "${var.name}-public" })
}

resource "aws_route_table_association" "public" {
  count          = 3
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  count  = 3
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
  }
  tags = merge(var.tags, { Name = "${var.name}-private-${var.availability_zones[count.index]}" })
}

resource "aws_route_table_association" "private" {
  count          = 3
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

resource "aws_cloudwatch_log_group" "flow_logs" {
  name              = "/aws/vpc/${var.name}/flow-logs"
  retention_in_days = max(365, var.flow_log_retention_days)
  kms_key_id        = aws_kms_key.logs.arn
  tags              = var.tags
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "logs_key" {
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
      values   = ["arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vpc/${var.name}/flow-logs"]
    }
  }
}

resource "aws_kms_key" "logs" {
  description             = "${var.name} VPC flow-log encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  policy                  = data.aws_iam_policy_document.logs_key.json
  tags                    = var.tags
}

resource "aws_iam_role" "flow_logs" {
  name               = "${var.name}-vpc-flow-logs"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "flow_logs" {
  name   = "cloudwatch-logs"
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs.json
}

resource "aws_flow_log" "this" {
  iam_role_arn    = aws_iam_role.flow_logs.arn
  log_destination = aws_cloudwatch_log_group.flow_logs.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.this.id
  tags            = var.tags
}

resource "aws_security_group" "alb" {
  #checkov:skip=CKV2_AWS_5: Attached to the ALB in the edge module.
  name_prefix = "${var.name}-alb-"
  description = "Public ALB entrypoint"
  vpc_id      = aws_vpc.this.id
  ingress {
    description = "ALB listener from the internet"
    protocol    = "tcp"
    from_port   = var.alb_ingress_port
    to_port     = var.alb_ingress_port
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "Forward traffic to private application targets"
    protocol    = "tcp"
    from_port   = 8080
    to_port     = 8080
    cidr_blocks = var.private_subnet_cidrs
  }
  tags = merge(var.tags, { Name = "${var.name}-alb" })
  lifecycle { create_before_destroy = true }
}

resource "aws_security_group" "kubernetes" {
  #checkov:skip=CKV2_AWS_5: Attached to EKS in the Kubernetes module.
  name_prefix = "${var.name}-kubernetes-"
  description = "Private Kubernetes workloads"
  vpc_id      = aws_vpc.this.id
  ingress {
    description     = "Application traffic from the ALB"
    protocol        = "tcp"
    from_port       = 8080
    to_port         = 8080
    security_groups = [aws_security_group.alb.id]
  }
  ingress {
    description = "Node-to-node communication"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    self        = true
  }
  egress {
    description = "Internal VPC communication"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]
  }
  #trivy:ignore:AVD-AWS-0104 Private workloads require outbound HTTPS through NAT for AWS APIs, image pulls, model downloads, and configured integrations.
  egress {
    description = "HTTPS through NAT and AWS APIs"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(var.tags, { Name = "${var.name}-kubernetes" })
  lifecycle { create_before_destroy = true }
}

resource "aws_security_group" "database" {
  #checkov:skip=CKV2_AWS_5: Attached to Aurora in the RDS module.
  name_prefix = "${var.name}-database-"
  description = "PostgreSQL from Kubernetes only"
  vpc_id      = aws_vpc.this.id
  ingress {
    description     = "PostgreSQL from private application workloads"
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [aws_security_group.kubernetes.id]
  }
  egress {
    description = "Return traffic"
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = [var.vpc_cidr]
  }
  tags = merge(var.tags, { Name = "${var.name}-database" })
  lifecycle { create_before_destroy = true }
}
