# Plans against a mocked google provider: no project and no credentials.
mock_provider "google" {}

variables {
  project_id = "demo-project"
}

run "model_access_for_aidlc_change_only" {
  command = plan

  assert {
    condition     = contains(keys(google_project_service.apis), "aiplatform.googleapis.com")
    error_message = "Vertex AI must be enabled: the model is Gemini on Vertex AI."
  }

  assert {
    condition     = google_project_iam_member.model_user.role == "roles/aiplatform.user"
    error_message = "The service account may call the model, and nothing more."
  }

  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "assertion.repository == 'subhamviky/order-to-cash-agentic-ai'")
    error_message = "Only this repository's tokens are accepted."
  }

  assert {
    condition     = strcontains(google_iam_workload_identity_pool_provider.github.attribute_condition, "assertion.job_workflow_ref.startsWith('subhamviky/a2c-framework/.github/workflows/aidlc-change.yml@')")
    error_message = "Only the reusable aidlc-change workflow may use the credentials."
  }

  assert {
    condition     = google_iam_workload_identity_pool_provider.github.oidc[0].issuer_uri == "https://token.actions.githubusercontent.com"
    error_message = "Tokens come from GitHub Actions, never from a stored key."
  }

  assert {
    condition     = google_service_account_iam_member.github_impersonates.role == "roles/iam.workloadIdentityUser"
    error_message = "The workflow impersonates the service account through federation."
  }
}
