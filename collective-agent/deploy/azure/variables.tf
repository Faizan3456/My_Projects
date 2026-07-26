variable "subscription_id" {
  description = "Azure subscription to bill. Defaults to the OpenEdge subscription."
  type        = string
  default     = "0466d867-fadc-4978-a682-a644860c913c"
}

variable "location" {
  description = "Azure region. UK South keeps latency and data residency local."
  type        = string
  default     = "uksouth"
}

variable "resource_group_name" {
  type    = string
  default = "rg-collective-agent"
}

variable "vm_size" {
  description = <<-EOT
    Standard_B1ms: 1 vCPU / 2 GiB, ~£12/month. Comfortable for Postgres +
    FastAPI + a standalone Next.js server + Caddy. B1s (1 GiB) is too tight once
    Postgres and Node are both resident.
  EOT
  type        = string
  default     = "Standard_B1ms"
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/id_ed25519.pub"
}

variable "ssh_source_addresses" {
  description = <<-EOT
    CIDRs allowed to reach port 22. Set this to your current address:
      terraform apply -var='ssh_source_addresses=["1.2.3.4/32"]'
    Defaults to blocking everything, so SSH must be opened deliberately.
  EOT
  type        = list(string)
  default     = ["127.0.0.1/32"]
}
