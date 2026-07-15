variable "project_id" {
  description = "Exact GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone."
  type        = string
  default     = "us-central1-a"
}

variable "instance_name" {
  description = "Compute Engine VM name."
  type        = string
  default     = "neuroswarm-axion"
}

variable "machine_type" {
  description = "Axion machine type."
  type        = string
  default     = "c4a-standard-8"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size in GB."
  type        = number
  default     = 200
}

variable "firewall_rule_name" {
  description = "Firewall rule name for demo ports."
  type        = string
  default     = "neuroswarm-demo"
}

variable "network_tag" {
  description = "Network tag attached to the VM and firewall rule."
  type        = string
  default     = "neuroswarm-demo"
}

variable "source_ranges" {
  description = "CIDR ranges allowed to access demo ports. Must be your current public IP CIDR, for example [\"203.0.113.10/32\"]."
  type        = list(string)

  validation {
    condition     = length(var.source_ranges) > 0 && !contains(var.source_ranges, "0.0.0.0/0")
    error_message = "Do not expose demo ports to 0.0.0.0/0. Use your current public IP /32 or an approved private CIDR."
  }
}

variable "enable_os_login" {
  description = "Enable OS Login metadata on the VM."
  type        = bool
  default     = true
}
