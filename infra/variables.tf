variable "project_id" {
  description = "Your GCP project ID (find it: gcloud config get-value project)"
  type        = string
}

variable "region" {
  description = "GCP region to deploy into"
  type        = string
  default     = "asia-southeast1" # Singapore - closest low-latency region to Thailand
}

variable "db_password" {
  description = "Password for the Postgres app user. Set via TF_VAR_db_password env var - never commit this."
  type        = string
  sensitive   = true
}

variable "container_image" {
  description = "Full image path, e.g. asia-southeast1-docker.pkg.dev/PROJECT/quant-repo/backend:latest"
  type        = string
}
