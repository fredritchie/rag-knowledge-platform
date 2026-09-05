# Private application deployment

Creates a no-ingress, VPC-attached CodeBuild project that can reach a private-only EKS API endpoint.
A protected GitHub environment assumes the narrow trigger role and starts a build for an exact main
commit. The build installs checksum-verified Helm and kubectl binaries, then runs the repository's
deployment script. Runtime credentials never enter Terraform state or GitHub Actions.
