# GitOps promotion

`environments/dev/images.yaml` is a digest-only Helm values overlay. After a successful merge to
`main`, the release workflow builds, scans, pushes, signs, and attests every project image before
opening a pull request that updates this file. Merging the GitOps pull request is the explicit
promotion approval; this repository does not deploy from a pull-request workflow.

Deploy with this overlay plus the ignored environment values file:

```bash
helm upgrade --install rag-platform helm/rag-platform \
  --namespace rag-platform --create-namespace \
  --values helm/rag-platform/values-dev.yaml \
  --values gitops/environments/dev/images.yaml
```

The environment values file owns the externally pinned Qdrant digest and all environment-specific
ARNs, endpoints, and CIDRs. No secret value belongs in this directory.
