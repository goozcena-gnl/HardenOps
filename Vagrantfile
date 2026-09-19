# frozen_string_literal: true

require "json"

state_file = File.join(__dir__, ".lab", "state.json")
state = File.exist?(state_file) ? JSON.parse(File.read(state_file)) : {}
distro = ENV.fetch("HARDENOPS_DISTRO", state.fetch("distro", "ubuntu2404"))
boxes = {
  "ubuntu2404" => ["bento/ubuntu-24.04", "202508.03.0"],
  "rocky9" => ["rockylinux/9", "6.0.0"]
}.freeze
abort "Supported DISTRO values: #{boxes.keys.join(', ')}" unless boxes.key?(distro)

Vagrant.configure("2") do |config|
  config.vm.box, config.vm.box_version = boxes.fetch(distro)
  config.vm.box_architecture = "amd64"
  config.vm.box_check_update = false
  config.vm.hostname = "hardenops-#{distro}"
  config.vm.synced_folder ".", "/vagrant", disabled: true
  config.ssh.insert_key = true
  config.vm.boot_timeout = 600

  config.vm.provider "libvirt" do |provider|
    provider.memory = 2048
    provider.cpus = 2
  end
  config.vm.provider "virtualbox" do |provider|
    provider.memory = 2048
    provider.cpus = 2
    provider.gui = false
  end
end
