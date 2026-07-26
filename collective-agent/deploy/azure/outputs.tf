output "public_ip" {
  description = "Point the DNS A record for agents. at this address."
  value       = azurerm_public_ip.ip.ip_address
}

output "ssh_command" {
  value = "ssh ${var.admin_username}@${azurerm_public_ip.ip.ip_address}"
}

output "next_steps" {
  value = <<-EOT

    1. Add a DNS A record at Namecheap:
         host: agents      value: ${azurerm_public_ip.ip.ip_address}
       Confirm:  dig +short agents.openedgetechnologies.com

    2. Deploy (cloud-init has already installed Docker):
         cd ../..
         deploy/deploy.sh ${azurerm_public_ip.ip.ip_address} ${var.admin_username}

    3. On the server, create the secrets file:
         cd /opt/collective/deploy
         cp .env.prod.example .env.prod && chmod 600 .env.prod
         # POSTGRES_PASSWORD, SERVICE_TOKEN, then any provider keys

    Stop billing entirely:  terraform destroy
    Pause it (~£5/mo, keeps the IP and disk):
      az vm deallocate -g ${var.resource_group_name} -n vm-collective
  EOT
}
