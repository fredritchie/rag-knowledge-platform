# VPC module

Creates a three-AZ VPC with public ALB/NAT subnets and private workload subnets. Private routes use one NAT per AZ by default; `single_nat_gateway` is a non-production cost-saving option. VPC flow logs are KMS-encrypted in CloudWatch.
