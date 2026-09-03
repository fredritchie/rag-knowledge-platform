output "alb_arn" { value = aws_lb.this.arn }
output "alb_arn_suffix" { value = aws_lb.this.arn_suffix }
output "dns_name" { value = aws_lb.this.dns_name }
output "application_url" { value = "https://${aws_route53_record.application.fqdn}" }
output "target_group_arn" { value = aws_lb_target_group.application.arn }
output "certificate_arn" { value = aws_acm_certificate.this.arn }
output "waf_arn" { value = aws_wafv2_web_acl.this.arn }
output "access_log_bucket" { value = aws_s3_bucket.logs.id }
