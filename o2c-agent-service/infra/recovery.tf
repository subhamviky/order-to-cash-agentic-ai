# Scheduled recovery of unfinished orders (design document G-2). Every order left RESERVING,
# PENDING_PAYMENT or PAYMENT_UNKNOWN for longer than recovery_after_seconds (past the request's
# idempotency lease) is finished with the same keys: reserved once, released once, charged once.
# The scheduler's service account (events.tf) is the caller; the route is not on API Gateway.

variable "recovery_schedule" {
  type        = string
  description = "How often unfinished orders are recovered (cron, UTC)."
  default     = "*/5 * * * *"
}

variable "recovery_after_seconds" {
  type        = number
  description = "An order is recovered once it has been unfinished this long (O2C_RECOVERY_AFTER_SECONDS)."
  default     = 600
}

resource "google_cloud_scheduler_job" "recover_orders" {
  count            = var.combined_schedule == "" ? 1 : 0
  name             = "${local.name}-recover-orders"
  region           = var.region
  schedule         = var.recovery_schedule
  time_zone        = "Etc/UTC"
  attempt_deadline = "300s"

  retry_config {
    retry_count = 0 # the next run tries again
  }

  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.app.uri}/internal/orders/recover"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = google_cloud_run_v2_service.app.uri
    }
  }
}

variable "daily_restock" {
  type        = bool
  description = "Top each SKU up to its catalog level once a day (O2C_DAILY_RESTOCK). For the demonstration landscape, whose scenario buys goods on every run and would otherwise empty the stock; leave false where stock is real."
  default     = false
}

locals {
  recovery_env = merge(
    { O2C_RECOVERY_AFTER_SECONDS = tostring(var.recovery_after_seconds) },
    var.daily_restock ? { O2C_DAILY_RESTOCK = "true" } : {},
  )
}
