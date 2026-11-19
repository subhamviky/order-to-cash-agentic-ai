# aidlc — model access for aidlc-change, through the Google Cloud project

`aidlc-change` (a2c-framework, hub design note AD-01) changes this service's code from a prompt.
Its model is **Gemini on Vertex AI in your own Google Cloud project** (E2A profile `google_vertex`
from e2a-managed-providers). There is no model-provider account and no stored key: the
`aidlc-change` workflow signs in through Workload Identity Federation.

This stack creates only what that needs:

| Resource | Why |
|---|---|
| Vertex AI, IAM Credentials and STS APIs | The model, and federation |
| Service account `aidlc-change` with `roles/aiplatform.user` | It may call the model, nothing else |
| Workload identity pool `github-aidlc` and provider `github-actions` | Accepts GitHub's OIDC tokens only from this repository, and only inside a2c-framework's reusable `aidlc-change.yml` |
| `roles/iam.workloadIdentityUser` for this repository | The workflow impersonates the service account |

It is separate from the service's stack (`..`), so it can be applied before the service is ever
deployed.

## One-time setup

1. Apply, with your own Google Cloud login (`gcloud auth application-default login`):

```bash
cd o2c-agent-service/infra/aidlc && terraform init && terraform apply -var project_id=<your-project-id>
```

2. Store the outputs as the repository's Actions **variables** (not secrets: none of them is a credential):

```bash
cd o2c-agent-service/infra/aidlc && gh variable set AIDLC_GCP_WORKLOAD_IDENTITY_PROVIDER --body "$(terraform output -raw workload_identity_provider)" && gh variable set AIDLC_GCP_SERVICE_ACCOUNT --body "$(terraform output -raw service_account)" && gh variable set AIDLC_GCP_PROJECT --body "$(terraform output -raw project_id)" && gh variable set AIDLC_GCP_LOCATION --body "$(terraform output -raw location)"
```

3. Run the change from the Actions tab (**aidlc-change**, *Run workflow*), or:

```bash
gh workflow run aidlc-change.yml -f prompt="<the change>"
```

The workflow plans, edits, verifies and commits as you, then opens a pull request. Review and merge
it like any other. The model's answers and the run's log stay as an artifact of the run.

## Cost and limits

Each change makes a few model calls (one plan, one to three edit attempts) billed to the project.
The model and location come from the profile (`LLM_MODEL_ID`, default `gemini-3.8-flash`;
`GOOGLE_CLOUD_LOCATION`, default `us-central1`); the model must be available in that location.
