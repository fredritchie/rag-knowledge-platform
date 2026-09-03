output "vpc_id" { value = aws_vpc.this.id }
output "vpc_cidr" { value = aws_vpc.this.cidr_block }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "alb_security_group_id" { value = aws_security_group.alb.id }
output "kubernetes_security_group_id" { value = aws_security_group.kubernetes.id }
output "database_security_group_id" { value = aws_security_group.database.id }
output "nat_gateway_ids" { value = aws_nat_gateway.this[*].id }
