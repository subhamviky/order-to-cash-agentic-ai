# Order events (E2A v1.7.3): each order change is committed in Firestore together with its event
# (an outbox record in the same write); a sweeper publishes pending events to the events topic
# (main.tf). Cloud Scheduler runs the sweeper by calling the service. Added by hand next to the
# A2C-generated main.tf.

variable "events_publish_schedule" {
  type        = string
  description = "How often pending order events are published (cron, UTC)."
  default     = "* * * * *"
}

# The service publishes to the events topic, and to nothing else.
resource "google_pubsub_topic_iam_member" "events_publisher" {
  topic  = google_pubsub_topic.events.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.app.email}"
}

# The scheduler calls the service with its own identity, which may invoke the service only.
resource "google_service_account" "scheduler" {
  account_id   = replace(substr("${local.name}-sched", 0, 28), "/-+$/", "")
  display_name = "${local.name} event publisher schedule"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler" {
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "publish_events" {
  name             = "${local.name}-publish-events"
  region           = var.region
  schedule         = var.events_publish_schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = "120s"

  retry_config {
    retry_count = 0 # the next run picks up whatever is still pending
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.app.uri}/internal/events/publish"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.app.uri
    }
  }
}
