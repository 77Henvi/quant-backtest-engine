output "cloud_run_url" {
  description = "Public URL of the deployed API"
  value       = google_cloud_run_v2_service.quant_api.uri
}

output "cloud_sql_connection_name" {
  description = "Pass this to `gcloud sql connect` or the Cloud SQL Auth Proxy"
  value       = google_sql_database_instance.quant_db_instance.connection_name
}

output "artifact_registry_repo" {
  description = "Push your Docker image here: docker push <this>/backend:latest"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.quant_repo.repository_id}"
}
