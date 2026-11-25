# Added by hand next to the A2C-generated main.tf: where the image lives, who may call
# the service, and the two services of the landscape it calls.

variable "settlement_api_url" {
  type        = string
  description = "Base URL of settlement-service (financial-settlement-platform)."
  default     = "https://settlement.internal.example"
}

variable "reconciliation_api_url" {
  type        = string
  description = "Base URL of reconciliation-service (payment-reconciliation-engine)."
  default     = "https://reconciliation.internal.example"
}

variable "invoker_members" {
  type        = list(string)
  description = "Principals allowed to call the service, e.g. serviceAccount:frontend@PROJECT.iam.gserviceaccount.com."
  default     = []

  validation {
    condition     = !contains(var.invoker_members, "allUsers") && !contains(var.invoker_members, "allAuthenticatedUsers")
    error_message = "The O2C assistant moves money: it is never public."
  }
}

variable "image_repository" {
  type        = string
  description = "Empty: the service gets its own Artifact Registry repository. Otherwise the repository its images are in (GCP-01: the landscape's one repository, within the 0.5 GB free storage)."
  default     = ""
}

# Container images built by CI are pushed here (the image job builds; pushing needs OIDC trust).
resource "google_artifact_registry_repository" "images" {
  count         = var.image_repository == "" ? 1 : 0
  repository_id = "${local.name}-images"
  location      = var.region
  format        = "DOCKER"
  labels        = local.labels
}

# Authentication in front of the API: only the listed principals may invoke it.
resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = each.value
}

output "image_repository" {
  value = var.image_repository != "" ? var.image_repository : "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images[0].repository_id}"
}
