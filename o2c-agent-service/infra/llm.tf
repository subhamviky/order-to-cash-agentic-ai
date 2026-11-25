# The model (GCP-01): E2A's simulated model, or the Gemini Developer API's free tier through
# e2a-managed-providers' gemini_api profile (build the image with POETRY_EXTRAS=gemini). The key
# is a Secret Manager secret, read at start-up; it is never in Terraform state. No paid AI
# service is bound.

variable "llm_profile" {
  type        = string
  description = "E2A provider profile: simulated (no model access) or gemini_api (free tier)."
  default     = "simulated"

  validation {
    condition     = contains(["simulated", "gemini_api"], var.llm_profile)
    error_message = "Free tier only: simulated or gemini_api."
  }
}

variable "llm_model_id" {
  type        = string
  description = "Gemini model for the gemini_api profile (empty: the profile's default)."
  default     = ""
}

variable "gemini_api_key_secret" {
  type        = string
  description = "Secret Manager secret id holding the Gemini API key (empty with the simulated profile)."
  default     = ""
}

locals {
  llm_env = merge({ E2A_PROVIDER_PROFILE = var.llm_profile },
  var.llm_model_id == "" ? {} : { LLM_MODEL_ID = var.llm_model_id })
}

resource "google_secret_manager_secret_iam_member" "gemini_key" {
  count     = var.gemini_api_key_secret == "" ? 0 : 1
  secret_id = var.gemini_api_key_secret
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.app.email}"
}
