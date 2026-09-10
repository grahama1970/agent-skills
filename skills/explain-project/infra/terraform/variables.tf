variable "name" {
  type        = string
  default     = "explain-project"
  description = "Deployment name used by downstream ops modules."
}

variable "container_host" {
  type        = string
  default     = "docker-compose-host"
  description = "Logical host that runs deploy/docker-compose.yml."
}

variable "api_port" {
  type        = number
  default     = 8766
  description = "Published explain-project cockpit API port."

  validation {
    condition     = var.api_port > 0 && var.api_port < 65536
    error_message = "api_port must be a TCP port number."
  }
}

variable "ui_port" {
  type        = number
  default     = 5174
  description = "Published explain-project cockpit UI port."

  validation {
    condition     = var.ui_port > 0 && var.ui_port < 65536
    error_message = "ui_port must be a TCP port number."
  }
}

variable "allowed_cidrs" {
  type        = list(string)
  default     = ["0.0.0.0/0"]
  description = "CIDR blocks allowed to reach the published cockpit ports."
}

variable "memory_url" {
  type        = string
  default     = ""
  description = "External Memory service URL; empty means caller supplies it at deploy time."
}

variable "chatterbox_url" {
  type        = string
  default     = ""
  description = "External Chatterbox service URL; empty means not wired."
}

variable "realtimestt_url" {
  type        = string
  default     = ""
  description = "External RealtimeSTT service URL; empty means not wired."
}

variable "schema_memory_collection" {
  type        = string
  default     = "skill_schemas"
  description = "Memory collection intended for deploy/schema-catalog.json ingestion."
}

variable "graph_memory_collection" {
  type        = string
  default     = "explain_project_graph_exports"
  description = "Memory collection intended for deploy/memory-graph-export.example.json ingestion."
}
