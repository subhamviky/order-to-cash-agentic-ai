# State of the service (orders, stock, approvals, request claims) in Firestore, through
# e2a-adapters' Firestore adapters (design note D-03), so Cloud Run can run several instances.
# Added by hand next to the A2C-generated main.tf, which stays untouched apart from the Cloud
# Run environment and scaling.

variable "max_instance_count" {
  type        = number
  description = "Cloud Run instances at most. State is in Firestore, shared by every instance."
  default     = 3
}

variable "firestore_database" {
  type        = string
  description = "Empty: the service gets its own database (PITR, delete protection). A name, e.g. \"(default)\": use that existing database instead (GCP-01: the free tier has one Firestore database per project, shared by the landscape; collections keep the services apart)."
  default     = ""
}

variable "firestore_collection" {
  type        = string
  description = "Collection holding the service's state documents."
  default     = "o2c"
}

resource "google_firestore_database" "state" {
  count                             = var.firestore_database == "" ? 1 : 0
  name                              = local.name
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  concurrency_mode                  = "OPTIMISTIC" # the adapters write with update-time preconditions
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  deletion_policy                   = "ABANDON"
}

locals {
  firestore_database = var.firestore_database == "" ? google_firestore_database.state[0].name : var.firestore_database
}

# Claims carry a "ttl" timestamp: a TTL policy garbage-collects them. Correctness never depends
# on it: the adapters use their own expiry fields.
resource "google_firestore_field" "ttl" {
  database   = local.firestore_database
  collection = var.firestore_collection
  field      = "ttl"
  ttl_config {}
}

# Least privilege: read and write documents. With the service's own database the grant is limited to it by a
# condition; on a shared existing database (GCP-01, "(default)") it is the plain project role, as in the other
# services, because a condition on the shared database's name delayed or denied access in the first live apply.
resource "google_project_iam_member" "firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
  dynamic "condition" {
    for_each = var.firestore_database == "" ? [1] : []
    content {
      title      = "o2c-state-database-only"
      expression = "resource.name.startsWith(\"projects/${var.project_id}/databases/${local.firestore_database}\")"
    }
  }
}

output "firestore_database" {
  value = local.firestore_database
}
