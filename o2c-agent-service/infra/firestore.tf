# State of the service (orders, stock, approvals, request claims) in Firestore, through
# e2a-adapters' Firestore adapters (design note D-03), so Cloud Run can run several instances.
# Added by hand next to the A2C-generated main.tf, which stays untouched apart from the Cloud
# Run environment and scaling.

variable "max_instance_count" {
  type        = number
  description = "Cloud Run instances at most. State is in Firestore, shared by every instance."
  default     = 3
}

variable "firestore_collection" {
  type        = string
  description = "Collection holding the service's state documents."
  default     = "o2c"
}

resource "google_firestore_database" "state" {
  name                              = local.name
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  concurrency_mode                  = "OPTIMISTIC" # the adapters write with update-time preconditions
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  deletion_policy                   = "ABANDON"
}

# Claims carry a "ttl" timestamp: a TTL policy garbage-collects them. Correctness never depends
# on it: the adapters use their own expiry fields.
resource "google_firestore_field" "ttl" {
  database   = google_firestore_database.state.name
  collection = var.firestore_collection
  field      = "ttl"
  ttl_config {}
}

# Least privilege: read and write documents in this database only.
resource "google_project_iam_member" "firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.app.email}"
  condition {
    title      = "o2c-state-database-only"
    expression = "resource.name.startsWith(\"projects/${var.project_id}/databases/${google_firestore_database.state.name}\")"
  }
}

output "firestore_database" {
  value = google_firestore_database.state.name
}
