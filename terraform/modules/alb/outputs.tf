output "alb_arn" { value = aws_lb.this.arn }
output "alb_arn_suffix" { value = aws_lb.this.arn_suffix }
output "dns_name" { value = aws_lb.this.dns_name }
output "application_url" { value = var.enable_https ? "https://${var.domain_name}" : "https://${aws_cloudfront_distribution.domainless_tls[0].domain_name}" }
output "target_group_arn" { value = aws_lb_target_group.application.arn }
output "certificate_arn" {
  value = var.enable_https ? coalesce(
    var.certificate_arn,
    try(aws_acm_certificate.this[0].arn, null),
  ) : null
}
output "waf_arn" { value = aws_wafv2_web_acl.this.arn }
output "access_log_bucket" { value = aws_s3_bucket.logs.id }
output "duckdns_ipv4" {
  value       = var.enable_duckdns ? aws_globalaccelerator_accelerator.duckdns[0].ip_sets[0].ip_addresses[0] : null
  description = "Primary stable Global Accelerator IPv4 address to publish through DuckDNS."
}
output "global_accelerator_ipv4_addresses" {
  value       = var.enable_duckdns ? aws_globalaccelerator_accelerator.duckdns[0].ip_sets[0].ip_addresses : []
  description = "All Global Accelerator addresses; DuckDNS can publish only one IPv4 address."
}
