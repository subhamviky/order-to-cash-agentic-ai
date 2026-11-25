# Identity at ingress (E2A v1.7.4; gcp_cloud_run since E2A v1.11.0, GCP-01): Google Cloud API Gateway verifies the caller's Identity
# Platform token and passes the verified claims to this service (X-Apigateway-Api-Userinfo).
# The service then takes tenant, user and role from those claims only, never from the
# X-Tenant-Id / X-User-* headers. The gateway is deployed from infra/api-gateway/openapi.yaml
# (gcloud api-gateway; the Terraform resources exist only in the google-beta provider).
#
# Trust: the header is trustworthy only if callers cannot bypass the gateway. Keep
# invoker_members (o2c.tf) to the gateway's service account; the scheduler (events.tf) calls
# only /internal/events/publish.

variable "identity_source" {
  type        = string
  description = "Where verified claims come from: gcp_api_gateway, or gcp_cloud_run (the free tier: Cloud Run IAM verifies the caller's Google ID token; no API Gateway); fail-closed either way. Empty: header mode (never in production)."
  default     = "gcp_api_gateway"

  validation {
    condition     = contains(["", "gcp_api_gateway", "gcp_cloud_run"], var.identity_source)
    error_message = "identity_source: gcp_api_gateway, gcp_cloud_run or empty."
  }
}

variable "identity_subject_roles" {
  type        = map(list(string))
  description = "gcp_cloud_run: the roles each caller (service account or user email) is granted, tenants as \"tenant:<id>\", e.g. {\"genai-app@P.iam.gserviceaccount.com\" = [\"tenant:acme\", \"finance\"]}."
  default     = {}
}

variable "identity_trusted_issuers" {
  type        = list(string)
  description = "Token issuers accepted, e.g. https://securetoken.google.com/<project>. Empty: any issuer the gateway verified."
  default     = []
}

locals {
  cloud_run_identity = var.identity_source == "gcp_cloud_run"
  identity_env = var.identity_source == "" ? {} : merge({
    E2A_IDENTITY_SOURCE = var.identity_source
    E2A_IDENTITY_TRUSTED_ISSUERS = jsonencode(local.cloud_run_identity && length(var.identity_trusted_issuers) == 0
    ? ["https://accounts.google.com"] : var.identity_trusted_issuers)
    }, local.cloud_run_identity ? {
    E2A_IDENTITY_TENANTS_FROM_ROLES = "tenant:"
    E2A_IDENTITY_SUBJECT_ROLES      = jsonencode(var.identity_subject_roles)
  } : {})
}
