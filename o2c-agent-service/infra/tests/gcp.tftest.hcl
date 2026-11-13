# Plans the configuration against a mocked google provider: no project and
# no credentials.
mock_provider "google" {}

variables {
  project_id      = "demo-project"
  invoker_members = ["serviceAccount:frontend@demo-project.iam.gserviceaccount.com"]
}

run "plan_with_mocks" {
  command = plan

  assert {
    condition     = google_pubsub_subscription.events.dead_letter_policy[0].max_delivery_attempts == 5
    error_message = "The subscription must dead-letter after 5 delivery attempts."
  }

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].scaling[0].max_instance_count > 1
    error_message = "State is in Firestore (e2a-adapters), so the service runs more than one instance."
  }

  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "O2C_STATE_BACKEND=firestore")
    error_message = "Every instance must keep its state in Firestore, not in memory."
  }

  assert {
    condition     = google_firestore_database.state.type == "FIRESTORE_NATIVE" && google_firestore_database.state.point_in_time_recovery_enablement == "POINT_IN_TIME_RECOVERY_ENABLED"
    error_message = "The state database is Firestore in Native mode, recoverable (PITR)."
  }

  assert {
    condition     = google_firestore_field.ttl.field == "ttl" && google_firestore_field.ttl.collection == "o2c"
    error_message = "A TTL policy on \"ttl\" garbage-collects the adapters' claims."
  }

  assert {
    condition     = google_project_iam_member.firestore.role == "roles/datastore.user"
    error_message = "The service account reads and writes Firestore documents, nothing more."
  }

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].containers[0].ports[0].container_port == 8000
    error_message = "Cloud Run must send traffic to the port the Dockerfile serves on."
  }

  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e.name], "SETTLEMENT_API_URL") && contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e.name], "RECONCILIATION_API_URL")
    error_message = "The service must know both downstream services."
  }

  assert {
    condition     = google_artifact_registry_repository.images.format == "DOCKER"
    error_message = "Images go to a Docker repository in Artifact Registry."
  }

  assert {
    condition     = length(google_cloud_run_v2_service_iam_member.invokers) == 1
    error_message = "Only the listed principals may invoke the service."
  }
}

run "public_access_is_refused" {
  command = plan

  variables {
    invoker_members = ["allUsers"]
  }

  expect_failures = [var.invoker_members]
}
