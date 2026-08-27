aws_region  = "ap-south-1"
bucket_name = "fred-rag-unique-bucket-12345"

# localhost is valid only while using the SSH-tunnel test flow. Add the HTTPS
# production origin after deploying the frontend behind a domain and TLS.
app_origins = [
  "http://localhost:3000",
]

tags = {
  Environment = "phase8-dev"
  ManagedBy   = "Terraform"
  Project     = "rag-knowledge-platform"
  Phase       = "8"
}
