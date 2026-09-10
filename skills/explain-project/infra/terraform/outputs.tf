output "compose_file" {
  value       = local.compose_file
  description = "Docker Compose file modeled by this detection-only module."
}

output "ingress_rules" {
  value       = local.ingress_rules
  description = "Security-group-like ingress contract for downstream ops modules."
}

output "service_urls" {
  value       = local.service_urls
  description = "Optional external service URLs for Memory, Chatterbox, and RealtimeSTT."
}

output "env" {
  value       = local.env
  description = "Environment values to render into deploy/.env."
}

output "schema_catalog" {
  value       = local.schema_catalog
  description = "Schema catalog artifact that can be ingested through $memory."
}
