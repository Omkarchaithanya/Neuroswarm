output "instance_name" {
  value = google_compute_instance.vm.name
}

output "zone" {
  value = google_compute_instance.vm.zone
}

output "external_ip" {
  value = google_compute_instance.vm.network_interface[0].access_config[0].nat_ip
}

output "service_account_email" {
  value = google_service_account.vm.email
}

output "ssh_alias_hint" {
  value = "${google_compute_instance.vm.name}.${var.zone}.${var.project_id}"
}
