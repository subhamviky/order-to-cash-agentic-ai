# Calls to settlement-service and to reconciliation-service's service route carry this service's
# own identity (hub design note SI-01): the Cloud Run service account's Google ID token, from the
# metadata server, exchanged for an Entra access token for each target (e2a_adapters.workload).
# No secret: the caller app's federated credential trusts the service account's unique id.
# financial-settlement-platform/landscape-identity/ holds the apps, roles and grants; give it
# this stack's output runtime_service_account_unique_id.

variable "entra_directory_id" {
  type        = string
  description = "The Entra directory that issues the landscape's workload tokens. Empty: calls carry no token."
  default     = ""
}

variable "entra_client_id" {
  type        = string
  description = "This service's caller app (landscape-identity's output o2c_client_id)."
  default     = ""
}

variable "settlement_scope" {
  type        = string
  description = "landscape-identity's output settlement_scope."
  default     = ""
}

variable "reconciliation_scope" {
  type        = string
  description = "landscape-identity's output reconciliation_scope."
  default     = ""
}

locals {
  workload_on = var.entra_directory_id != "" && var.entra_client_id != "" && var.settlement_scope != "" && var.reconciliation_scope != ""
  workload_env = local.workload_on ? {
    E2A_WORKLOAD_IDENTITY        = "gcp"
    E2A_WORKLOAD_ENTRA_TENANT    = var.entra_directory_id
    E2A_WORKLOAD_ENTRA_CLIENT_ID = var.entra_client_id
    E2A_WORKLOAD_TOKEN_SCOPES = jsonencode({
      (var.settlement_api_url)     = var.settlement_scope
      (var.reconciliation_api_url) = var.reconciliation_scope
    })
  } : {}
}

output "runtime_service_account_unique_id" {
  description = "landscape-identity's o2c_google_service_account_id: the subject of this service's Google ID token."
  value       = google_service_account.app.unique_id
}
