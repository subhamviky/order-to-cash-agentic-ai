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

run "order_events_are_published" {
  command = plan

  assert {
    condition     = google_pubsub_topic_iam_member.events_publisher.role == "roles/pubsub.publisher"
    error_message = "The service publishes order events to the events topic."
  }

  assert {
    condition     = google_cloud_scheduler_job.publish_events.http_target[0].http_method == "POST" && length(google_cloud_scheduler_job.publish_events.http_target[0].oidc_token) == 1
    error_message = "The scheduler calls the publish endpoint with an OIDC identity."
  }

  assert {
    condition     = google_cloud_run_v2_service_iam_member.scheduler.role == "roles/run.invoker"
    error_message = "The scheduler's identity may invoke the service, nothing more."
  }
}

run "identity_at_ingress" {
  command = plan

  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "E2A_IDENTITY_SOURCE=gcp_api_gateway")
    error_message = "In Google Cloud the caller comes from the claims API Gateway verified, never from headers."
  }
}

run "public_access_is_refused" {
  command = plan

  variables {
    invoker_members = ["allUsers"]
  }

  expect_failures = [var.invoker_members]
}

run "calls_carry_this_services_identity" {
  command = plan
  variables {
    settlement_api_url     = "https://settlement.example"
    reconciliation_api_url = "https://reconciliation.example"
    entra_directory_id     = "dir"
    entra_client_id        = "o2c-app"
    settlement_scope       = "api://landscape-test-settlement/.default"
    reconciliation_scope   = "api://landscape-test-reconciliation/.default"
  }
  assert {
    condition = alltrue([for kv in ["E2A_WORKLOAD_IDENTITY=gcp", "E2A_WORKLOAD_ENTRA_CLIENT_ID=o2c-app",
      "E2A_WORKLOAD_TOKEN_SCOPES={\"https://reconciliation.example\":\"api://landscape-test-reconciliation/.default\",\"https://settlement.example\":\"api://landscape-test-settlement/.default\"}"] :
    contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], kv)])
    error_message = "o2c exchanges its Google ID token for an Entra token per target"
  }
}

run "no_token_until_configured" {
  command = plan
  assert {
    condition     = !contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e.name], "E2A_WORKLOAD_IDENTITY")
    error_message = "without the Entra settings, calls carry no token"
  }
}

run "unfinished_orders_are_recovered_on_a_schedule" {
  command = plan
  assert {
    condition     = google_cloud_scheduler_job.recover_orders.schedule == "*/5 * * * *" && google_cloud_scheduler_job.recover_orders.http_target[0].http_method == "POST"
    error_message = "Cloud Scheduler calls the recovery sweep every five minutes"
  }
  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "O2C_RECOVERY_AFTER_SECONDS=600")
    error_message = "orders are recovered only after the request's lease"
  }
}
