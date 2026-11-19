# aidlc — model access for aidlc-change through the Google Cloud project (hub design note AD-01,
# plan step 4). No model-provider account: aidlc-change binds E2A's `google_vertex` profile
# (e2a-managed-providers), which calls Gemini on Vertex AI with Google credentials. This stack
# gives exactly one caller those credentials: the reusable a2c-framework workflow
# `aidlc-change.yml`, run from this repository, through Workload Identity Federation (no key).
#
# It is separate from the service's stack (../): apply it on its own, before the service is
# ever deployed. Outputs go into the repository's Actions variables (see README.md).

terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.location
}

variable "project_id" {
  type        = string
  description = "Google Cloud project that pays for and audits the model calls."
}

variable "location" {
  type        = string
  description = "Vertex AI location of the model (the profile's GOOGLE_CLOUD_LOCATION)."
  default     = "us-central1"
}

variable "github_repository" {
  type        = string
  description = "owner/name of the repository whose aidlc-change runs may call the model."
  default     = "subhamviky/order-to-cash-agentic-ai"
}

variable "aidlc_workflow" {
  type        = string
  description = "The reusable workflow that may impersonate the service account (any ref)."
  default     = "subhamviky/a2c-framework/.github/workflows/aidlc-change.yml"
}

locals {
  labels = { project = "o2c-agent-service", purpose = "aidlc-change", managed_by = "terraform" }
}

resource "google_project_service" "apis" {
  for_each           = toset(["aiplatform.googleapis.com", "iamcredentials.googleapis.com", "sts.googleapis.com"])
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "aidlc_change" {
  account_id   = "aidlc-change"
  display_name = "aidlc-change (AI-DLC code changes, model calls only)"
  description  = "Used only by the aidlc-change workflow to call Gemini on Vertex AI. No other access."
}

# The model, nothing else: no storage, no deployment, no secrets
resource "google_project_iam_member" "model_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.aidlc_change.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-aidlc"
  display_name              = "GitHub (aidlc-change)"
  description               = "GitHub Actions OIDC tokens of the aidlc-change workflow"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions"
  display_name                       = "GitHub Actions"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.actor"      = "assertion.actor"
    "attribute.workflow"   = "assertion.job_workflow_ref"
  }
  # only this repository, and only inside the reusable aidlc-change workflow (any tag or branch of it)
  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.job_workflow_ref.startsWith('${var.aidlc_workflow}@')"
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonates" {
  service_account_id = google_service_account.aidlc_change.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

output "workload_identity_provider" {
  description = "Actions variable AIDLC_GCP_WORKLOAD_IDENTITY_PROVIDER"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "service_account" {
  description = "Actions variable AIDLC_GCP_SERVICE_ACCOUNT"
  value       = google_service_account.aidlc_change.email
}

output "project_id" {
  description = "Actions variable AIDLC_GCP_PROJECT"
  value       = var.project_id
}

output "location" {
  description = "Actions variable AIDLC_GCP_LOCATION"
  value       = var.location
}
