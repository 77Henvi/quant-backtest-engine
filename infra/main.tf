terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# --- Enable the GCP APIs this stack needs. Fresh projects have these
# --- off by default; Terraform will turn them on and wait until ready.
resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "sqladmin" {
  service            = "sqladmin.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifactregistry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

# --- Artifact Registry: where `docker push` sends your built image ---
resource "google_artifact_registry_repository" "quant_repo" {
  repository_id = "quant-repo"
  location      = var.region
  format        = "DOCKER"
  depends_on    = [google_project_service.artifactregistry]
}

# --- Cloud SQL: managed Postgres ---
# db-f1-micro is the smallest/cheapest tier - fine for a portfolio
# project's traffic level. Upgrade the tier if you outgrow it.
resource "google_sql_database_instance" "quant_db_instance" {
  name             = "quant-db-instance"
  database_version = "POSTGRES_16"
  region           = var.region
  depends_on       = [google_project_service.sqladmin]

  settings {
    tier              = "db-f1-micro"
    availability_type = "ZONAL" # single-zone; cheaper than regional HA
    disk_size         = 10
    disk_autoresize   = true
  }

  # Portfolio project safety net: without this, `terraform destroy`
  # deletes the database (and all backtest history) with no confirmation.
  deletion_protection = false
}

resource "google_sql_database" "quant_db" {
  name     = "quant"
  instance = google_sql_database_instance.quant_db_instance.name
}

resource "google_sql_user" "quant_app_user" {
  name     = "quant_app"
  instance = google_sql_database_instance.quant_db_instance.name
  password = var.db_password
}

# --- Service account the Cloud Run service runs as ---
resource "google_service_account" "quant_api_sa" {
  account_id   = "quant-api-runner"
  display_name = "Project Quant API runtime service account"
}

# Lets Cloud Run connect to Cloud SQL via the built-in Cloud SQL proxy,
# without opening the database to the public internet.
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.quant_api_sa.email}"
}

# --- Cloud Run service running the FastAPI backend ---
resource "google_cloud_run_v2_service" "quant_api" {
  name       = "quant-api"
  location   = var.region
  depends_on = [google_project_service.run]

  template {
    service_account = google_service_account.quant_api_sa.email

    scaling {
      min_instance_count = 0 # scale to zero when idle -> $0 when unused
      max_instance_count = 3
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8080
      }

      env {
        name = "DATABASE_URL"
        value = join("", [
          "postgresql://${google_sql_user.quant_app_user.name}:${var.db_password}",
          "@/${google_sql_database.quant_db.name}",
          "?host=/cloudsql/${google_sql_database_instance.quant_db_instance.connection_name}",
        ])
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    annotations = {
      "run.googleapis.com/cloudsql-instances" = google_sql_database_instance.quant_db_instance.connection_name
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }
}

# Allow public HTTP access to the API (remove this if you want to
# require authentication - fine for a portfolio demo to leave public).
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  location = google_cloud_run_v2_service.quant_api.location
  name     = google_cloud_run_v2_service.quant_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
