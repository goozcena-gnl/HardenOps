"""Connection metadata must not import Vagrant's relaxed host-key policy."""

from pathlib import Path
import shlex

import pytest

from tools.lab import choose_state, make_inventory, parse_ssh_config


def test_inventory_uses_private_key_but_rejects_changed_host_keys():
    ssh = parse_ssh_config('''Host default
  HostName 127.0.0.1
  User vagrant
  Port 2222
  IdentityFile "/home/test/lab with spaces/private_key"
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
''')
    host = make_inventory(ssh, Path("/home/test/lab with spaces/.lab"))["all"]["children"]["hardenops"]["hosts"]["lab"]
    args = shlex.split(host["ansible_ssh_common_args"])
    assert "StrictHostKeyChecking=accept-new" in args
    assert "UserKnownHostsFile=/home/test/lab with spaces/.lab/known_hosts" in args
    assert "/dev/null" not in host["ansible_ssh_common_args"]
    assert host["ansible_ssh_private_key_file"].endswith("lab with spaces/private_key")


def test_multiple_vagrant_identities_are_preserved_for_ssh_fallback():
    first = "/home/test/keys with spaces/vagrant.key.ed25519"
    second = "/home/test/keys with spaces/vagrant.key.rsa"
    ssh = parse_ssh_config(f'''Host default
  HostName 127.0.0.1
  User vagrant
  Port 2222
  IdentityFile "{first}"
  IdentityFile "{second}"
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
''')
    host = make_inventory(ssh)["all"]["children"]["hardenops"]["hosts"]["lab"]
    args = shlex.split(host["ansible_ssh_common_args"])
    assert host["ansible_ssh_private_key_file"] == first
    assert args[args.index("-i") + 1] == second
    assert "IdentitiesOnly=yes" in args
    assert "StrictHostKeyChecking=accept-new" in args
    assert "/dev/null" not in host["ansible_ssh_common_args"]


@pytest.mark.parametrize("extra", [
    "Host second\n  IdentityFile /tmp/second",
    "Match host second\n  IdentityFile /tmp/second",
    "HostName 192.0.2.1",
    "User another",
    "Port 2223",
    'IdentityFile ""',
    "IdentityFile /tmp/one /tmp/two",
])
def test_multiple_keys_do_not_allow_ambiguous_connection_metadata(extra):
    with pytest.raises(ValueError):
        parse_ssh_config('''Host default
  HostName 127.0.0.1
  User vagrant
  Port 2222
  IdentityFile /tmp/first
''' + extra)


@pytest.mark.parametrize("value", ["", "HostName 1\nHostName 2", "Port 0", "Host default"])
def test_partial_or_ambiguous_inventory_fails_closed(value):
    with pytest.raises(ValueError):
        parse_ssh_config(value)


def test_followup_commands_remember_rocky_and_virtualbox():
    state = {"distro": "rocky9", "provider": "virtualbox"}
    assert choose_state(state, None, None) == state
    with pytest.raises(ValueError, match="Destroy"):
        choose_state(state, "ubuntu2404", None)


def test_invalid_saved_state_is_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        choose_state({"distro": "fedora", "provider": "libvirt"}, None, None)
