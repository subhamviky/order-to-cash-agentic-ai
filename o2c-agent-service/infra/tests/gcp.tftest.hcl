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
    condition     = google_firestore_database.state[0].type == "FIRESTORE_NATIVE" && google_firestore_database.state[0].point_in_time_recovery_enablement == "POINT_IN_TIME_RECOVERY_ENABLED"
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
    condition     = google_artifact_registry_repository.images[0].format == "DOCKER"
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
    condition     = google_cloud_scheduler_job.publish_events[0].http_target[0].http_method == "POST" && length(google_cloud_scheduler_job.publish_events[0].http_target[0].oidc_token) == 1
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
    condition     = google_cloud_scheduler_job.recover_orders[0].schedule == "*/5 * * * *" && google_cloud_scheduler_job.recover_orders[0].http_target[0].http_method == "POST"
    error_message = "Cloud Scheduler calls the recovery sweep every five minutes"
  }
  assert {
    condition     = contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value}"], "O2C_RECOVERY_AFTER_SECONDS=600")
    error_message = "orders are recovered only after the request's lease"
  }
}

# GCP-01: the landscape on the free tier. Shared (default) database, the landscape's image
# repository, one scheduler job, Cloud Run IAM identity, Google ID tokens to the other services,
# Gemini's free tier with its key in Secret Manager, one instance.
run "free_tier" {
  command = plan

  variables {
    region                 = "us-central1"
    firestore_database     = "(default)"
    image_repository       = "us-central1-docker.pkg.dev/demo-project/landscape"
    combined_schedule      = "*/2 * * * *"
    max_instance_count     = 1
    identity_source        = "gcp_cloud_run"
    identity_subject_roles = { "genai-app@demo-project.iam.gserviceaccount.com" = ["tenant:acme", "finance"] }
    workload_identity      = "gcp_id_token"
    llm_profile            = "gemini_api"
    gemini_api_key_secret  = "gemini-api-key"
  }

  assert {
    condition     = length(google_firestore_database.state) == 0 && google_firestore_field.ttl.database == "(default)"
    error_message = "No database of its own: the shared (default) database, the free one."
  }

  assert {
    condition     = length(google_artifact_registry_repository.images) == 0
    error_message = "No repository of its own: images are in the landscape's repository."
  }

  assert {
    condition     = length(google_cloud_scheduler_job.publish_events) == 0 && length(google_cloud_scheduler_job.recover_orders) == 0 && google_cloud_scheduler_job.jobs[0].schedule == "*/2 * * * *"
    error_message = "One scheduler job (the landscape has three free), doing both jobs."
  }

  assert {
    condition = alltrue([for want in [
      "E2A_IDENTITY_SOURCE=gcp_cloud_run",
      "E2A_IDENTITY_TENANTS_FROM_ROLES=tenant:",
      "E2A_IDENTITY_TRUSTED_ISSUERS=[\"https://accounts.google.com\"]",
      "E2A_WORKLOAD_IDENTITY=gcp_id_token",
      "E2A_PROVIDER_PROFILE=gemini_api",
      "O2C_FIRESTORE_DATABASE=(default)",
    ] : contains([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : "${e.name}=${e.value != null ? e.value : ""}"], want)])
    error_message = "Cloud Run IAM identity, ID tokens outbound, Gemini's free tier, the shared database."
  }

  assert {
    condition     = length([for e in google_cloud_run_v2_service.app.template[0].containers[0].env : e if e.name == "GEMINI_API_KEY" && e.value == null]) == 1 && length(google_secret_manager_secret_iam_member.gemini_key) == 1
    error_message = "The Gemini key comes from Secret Manager, never a plain value."
  }

  assert {
    condition     = google_cloud_run_v2_service.app.template[0].scaling[0].max_instance_count == 1
    error_message = "One instance on the free tier."
  }
}

run "only_free_models" {
  command = plan

  variables {
    llm_profile = "google_vertex"
  }

  expect_failures = [var.llm_profile]
}
