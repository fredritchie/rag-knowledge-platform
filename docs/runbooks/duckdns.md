# DuckDNS HTTPS configuration

The platform reserves one external hostname per environment:

| Environment | Hostname |
| --- | --- |
| dev | `fred-rag-dev.duckdns.org` |
| staging | `fred-rag-stage.duckdns.org` |
| prod | `fred-rag.duckdns.org` |

DuckDNS is external DNS. Terraform never receives the DuckDNS token or TLS private key. The
certificate workflow issues or renews the certificate and stores its ACM ARN in an environment
specific SSM parameter. The Terraform plan workflow reads that parameter and writes an ephemeral
`zz-pipeline.auto.tfvars.json`; no manual certificate variable edit is required.

## Certificate preparation

1. Store the DuckDNS token as the `DUCKDNS_TOKEN` secret in the target GitHub environment.
2. Set the non-secret `LETSENCRYPT_EMAIL` variable in that environment.
3. Run **DuckDNS Let's Encrypt certificate** for the target environment. It performs the DNS-01
   challenge, imports the certificate into ACM in `ap-south-1`, validates it, and records the ARN at
   `/rag-platform/ENVIRONMENT/letsencrypt/acm_certificate_arn` in SSM Parameter Store.
4. Run the normal Terraform plan and reviewed apply pipeline. The plan injects the domain,
   certificate ARN, and DuckDNS settings automatically. Terraform creates a Global Accelerator in
   front of the ALB, and the apply job publishes its primary static address through DuckDNS.

Imported ACM certificates are not renewed by AWS. The certificate workflow runs monthly for dev
and reimports into the same ACM ARN. Add staging and production to the scheduled matrix only after
those environments and their GitHub secrets are active.

## DNS routing limitation

DuckDNS publishes one IPv4 address and cannot publish the ALB DNS name as a CNAME or Route53-style
alias. Global Accelerator therefore provides stable addresses in front of the three-AZ ALB. The
pipeline publishes its primary address automatically. Global Accelerator supplies two addresses,
but DuckDNS can publish only one; moving to a DNS provider that supports multiple A records or an
alias remains the path to full DNS-level edge redundancy.
