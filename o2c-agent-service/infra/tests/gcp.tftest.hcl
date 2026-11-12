# Plans the configuration against a mocked google provider: no project and
# no credentials.
mock_provider "google" {}

variables {
  project_id = "demo-project"
}

run "plan_with_mocks" {
  command = plan

  assert {
    condition     = google_pubsub_subscription.events.dead_letter_policy[0].max_delivery_attempts == 5
    error_message = "The subscription must dead-letter after 5 delivery attempts."
  }
}
