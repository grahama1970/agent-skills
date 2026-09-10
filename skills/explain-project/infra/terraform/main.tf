locals {
  compose_file = "${path.module}/../../deploy/docker-compose.yml"

  ingress_rules = [
    {
      name          = "${var.name}-api"
      host          = var.container_host
      port          = var.api_port
      protocol      = "tcp"
      allowed_cidrs = var.allowed_cidrs
    },
    {
      name          = "${var.name}-ui"
      host          = var.container_host
      port          = var.ui_port
      protocol      = "tcp"
      allowed_cidrs = var.allowed_cidrs
    }
  ]

  service_urls = {
    memory      = var.memory_url
    chatterbox  = var.chatterbox_url
    realtimestt = var.realtimestt_url
  }

  schema_catalog = {
    path                    = "${path.module}/../../deploy/schema-catalog.json"
    memory_collection       = var.schema_memory_collection
    graph_export_path       = "${path.module}/../../deploy/memory-graph-export.example.json"
    graph_memory_collection = var.graph_memory_collection
  }

  env = {
    EXPLAIN_PROJECT_API_PORT = tostring(var.api_port)
    EXPLAIN_PROJECT_UI_PORT  = tostring(var.ui_port)
    MEMORY_URL               = var.memory_url
    CHATTERBOX_URL           = var.chatterbox_url
    REALTIMESTT_URL          = var.realtimestt_url
  }
}
