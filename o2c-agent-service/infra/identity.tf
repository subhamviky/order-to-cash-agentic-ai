# Identity at ingress (E2A v1.7.4): Google Cloud API Gateway verifies the caller's Identity
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
  description = "Where verified claims come from: gcp_api_gateway (fail-closed), or empty for header mode (never in production)."
  default     = "gcp_api_gateway"
}

variable "identity_trusted_issuers" {
  type        = list(string)
  description = "Token issuers accepted, e.g. https://securetoken.google.com/<project>. Empty: any issuer the gateway verified."
  default     = []
}

locals {
  identity_env = var.identity_source == "" ? {} : {
    E2A_IDENTITY_SOURCE          = var.identity_source
    E2A_IDENTITY_TRUSTED_ISSUERS = jsonencode(var.identity_trusted_issuers)
  }
}
