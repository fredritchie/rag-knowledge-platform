# DuckDNS HTTPS configuration

The platform reserves one external hostname per environment:

| Environment | Hostname |
| --- | --- |
| dev | `fred-rag-dev.duckdns.org` |
| staging | `fred-rag-stage.duckdns.org` |
| prod | `fred-rag.duckdns.org` |

DuckDNS is external DNS. Terraform does not receive the DuckDNS token or TLS private key. Each
environment instead receives an ACM certificate ARN through its protected `TERRAFORM_TFVARS`
GitHub environment secret.

## Certificate preparation

1. Issue a public certificate for the environment hostname with an ACME client using the DuckDNS
   DNS-01 challenge and the account's DuckDNS token.
2. Import the certificate, unencrypted private key, and CA chain into ACM in `ap-south-1`.
3. Set these values in the environment's `TERRAFORM_TFVARS` secret:

   ```hcl
   enable_https    = true
   domain_name     = "fred-rag-dev.duckdns.org"
   hosted_zone_id  = null
   certificate_arn = "arn:aws:acm:ap-south-1:ACCOUNT_ID:certificate/CERTIFICATE_ID"
   ```

   Replace the hostname for staging or production using the table above.
4. Run the normal Terraform plan and reviewed apply pipeline. Terraform configures the ALB HTTPS
   listener and uses the HTTPS hostname for Cognito callback and logout URLs.

Imported ACM certificates are not renewed by AWS. Renew with the ACME client and reimport the new
certificate into the same ACM ARN before expiry so the ALB association remains unchanged.

## DNS routing limitation

DuckDNS publishes one IPv4 address; it cannot publish the ALB DNS name as a CNAME or Route53-style
alias. An ALB has service-managed addresses that can change and normally exposes one address per
enabled Availability Zone. The IP currently shown in the DuckDNS UI must not be treated as the ALB
endpoint.

For a temporary development endpoint, update the DuckDNS record from a monitored resolver using a
currently resolved ALB address and refresh it whenever the ALB answer changes. This is not a
production-ready availability design.

Before staging or production traffic is enabled, choose one of these durable ingress arrangements:

- place a static-IP AWS ingress layer in front of the ALB and publish its address in DuckDNS; or
- move DNS hosting to a provider that supports a CNAME/alias to the ALB DNS name.

The second option retains all three ALB Availability Zones and is the recommended production path.
