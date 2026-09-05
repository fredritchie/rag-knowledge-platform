# Phase 16: CI/CD and AI quality gates

Phase 16 makes pull-request verification deployment-free and makes image promotion an explicit,
reviewable operation. Pull requests receive read-only repository permissions and no AWS
credentials. A merge to `main` can publish only after the same software and RAG checks pass.

## Pull-request pipeline

`.github/workflows/pull-request.yml` runs one ordered verification job:

```text
format -> lint -> unit -> integration -> security -> RAG evaluation
       -> Docker build -> image scan -> Terraform validate -> Checkov
       -> Helm lint -> kubeconform
```

The workflow never configures AWS credentials, runs Terraform plan/apply, invokes Helm against a
cluster, pushes an image, or changes a GitOps manifest. Concurrency cancels superseded runs for the
same pull request.

Unit and integration tests are separate pytest marker suites. Security includes Gitleaks, Bandit,
pip-audit, npm audit, Trivy secret/misconfiguration scanning, Checkov, and image scans. Terraform
initializes with `-backend=false`, so validation cannot read or mutate remote state. Helm renders the
application and every pinned platform/observability chart; kubeconform and the exact reviewed
third-party finding sets in `docs/security/` inspect the output.

## RAG quality gate

`evaluation/datasets/ci-golden.jsonl` is a small, version-controlled dataset with three answerable
questions and eight indexed source/distractor documents. The runner uses the real catalog, hybrid
retrieval, prompt builder, generation service, citation construction, and evaluation service. Its
offline embedder and generation adapter are deterministic so a pull request does not depend on a
network model endpoint or fluctuate between runs.

`evaluation/baselines/ci-quality.json` controls the gate:

| Metric | Baseline | Tolerance | Required minimum |
| --- | ---: | ---: | ---: |
| Hit@5 | 1.00 | 0.00 | 1.00 |
| Groundedness | 0.80 | 0.01 | 0.79 |
| Citation correctness | 1.00 | 0.00 | 1.00 |

Any value below `baseline - tolerance`, any non-finite value, or fewer than three cases fails the
job. Retrieval, RAG, and gate reports are retained as workflow artifacts for 30 days. Run the same
gate locally with `make quality-gate`.

This is a stable regression gate for retrieval/generation plumbing and the repository's lexical
groundedness proxy. It does not replace a representative corpus evaluation, human citation audit,
or an environment-specific evaluation of the production embedding and language models.

## Post-merge release and GitOps promotion

`.github/workflows/supply-chain.yml` runs only for pushes to `main`:

```text
tests + RAG gate -> build -> SBOM -> scan -> ECR push -> sign/attest -> GitOps PR
```

Images are pushed by immutable commit SHA and signed by digest with keyless Cosign. The workflow
downloads its own digest artifacts, rejects missing, duplicate, tag-only, or malformed references,
and updates `gitops/environments/dev/images.yaml`. It then opens a pull request; it never deploys the
manifest. Merging that GitOps pull request is the promotion approval.

Repository settings must allow GitHub Actions to create pull requests. `GITOPS_PR_TOKEN` must be a
fine-grained token or GitHub App token with repository contents and pull-request write access; using
a non-`GITHUB_TOKEN` credential ensures the promotion pull request triggers its own verification
workflow. `AWS_ECR_ROLE_ARN` and `AWS_REGION` must identify the Terraform-created OIDC publisher
role and region. If AWS/ECR is intentionally destroyed, release fails before promotion and no
GitOps pull request is created.

## Exit criteria

Phase 16 is complete when all of the following are true:

- A pull request runs every stage in the documented order with no deployment credentials or
  mutation step.
- Format, lint, unit, integration, security, Docker/image, Terraform, Checkov, Helm, and
  kubeconform stages fail closed.
- The committed CI golden dataset contains at least three cases and the gate enforces Hit@5,
  groundedness, and citation correctness against versioned baselines and tolerances.
- A test proves a metric below tolerance fails, and a test proves incomplete or mutable image
  references cannot update the GitOps manifest.
- Evaluation reports are downloadable workflow artifacts.
- Pull-request image builds and scans do not push, sign, deploy, or open promotion pull requests.
- A successful `main` run produces SBOMs, scans all images, pushes immutable ECR references, signs
  digests, attaches SBOM attestations, and opens a digest-only GitOps pull request.
- The GitOps pull request changes only the expected image manifest and requires review; no workflow
  automatically applies Terraform or Helm.
- Branch protection requires the Phase 16 pull-request verification check before merge.

Repository implementation can be validated while AWS is absent. The post-merge ECR/signing/GitOps
criteria require the Phase 13 ECR repositories and publisher role to be recreated.

## Manually approved dev infrastructure deployment

`.github/workflows/terraform-deploy.yml` is manual-only and operates only from `main`. Run it first
with `operation=plan`. The successful run retains a human-readable plan, binary saved plan, source
commit, and checksum for five days. Review `plan.txt`, then start a second run with
`operation=apply` and the successful plan run ID.

The apply run rejects artifacts from another workflow, branch, failed run, or stale `main` commit.
It verifies the source commit and plan checksum before applying the exact binary plan. Both jobs use
the protected `dev` GitHub environment and OIDC role; no static AWS credentials are used. The
environment must define secret `AWS_TERRAFORM_ROLE_ARN` and variables `AWS_REGION`,
`TF_STATE_BUCKET`, and `TF_STATE_KMS_KEY_ARN`. Concurrency permits only one dev Terraform operation
at a time.

For controlled teardown, run `destroy-plan` and review its `plan.txt` artifact. Then run
`destroy-apply` with that successful run ID and the exact confirmation `destroy-dev`. A normal apply
cannot consume a destroy plan, and a destroy apply cannot consume a normal plan. The protected
environment approval still applies. Teardown affects only resources in the dev remote state; the
separately bootstrapped state bucket, state KMS key, GitHub OIDC provider, and deployment role remain
available for future deployments.
