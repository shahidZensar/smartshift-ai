"""
CONFIG-intent playbook registry + mapping.

Single source of truth for the CONFIG refinement loop and (future) execution layer.

Two layers are merged here:
  1. The vetted *playbook contract* — loaded from the colleague's
     `repositories/playbook-registry/required_fields.yaml`:
        config_type -> {playbook, target_group, required_fields, optional_fields, risk}
     This file is authoritative for field NAMES and risk; do not duplicate it.
  2. Agent-specific *refinement metadata* (this file): per-type `keywords`, a
     disambiguation `example`, and per-field prompt/example/validator. The loop reads
     these to ask dynamic follow-up questions; they are NOT part of the playbook
     contract, so they live alongside rather than inside the YAML.

Adding a new config type = add a playbook + a `required_fields.yaml` entry + (optionally)
a keywords/field block below. No other code changes.
"""
import os
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from . import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Registry directory: smartshift-ai/repositories/playbook-registry
DEFAULT_REGISTRY_DIR = os.path.normpath(
    os.path.join(BASE_DIR, "..", "repositories", "playbook-registry")
)
REGISTRY_DIR = os.getenv("CONFIG_REGISTRY_DIR", DEFAULT_REGISTRY_DIR)
MAPPING_FILE = os.path.join(REGISTRY_DIR, "required_fields.yaml")


# ---------------------------------------------------------------------------
# Agent-side refinement metadata (keywords + per-field prompts + disambig example)
# Keyed by config_type. Field metadata is keyed by the EXACT field name from
# required_fields.yaml so the two layers line up.
# ---------------------------------------------------------------------------
ENRICHMENT: dict[str, dict] = {
    "hostname": {
        "keywords": ["hostname", "host name", "device name", "rename", "name the device"],
        "example": "Set the hostname on R1 to CORE-RTR-01",
        "fields": {
            "hostname": {"prompt": "What hostname should the device have?", "example": "CORE-RTR-01"},
        },
    },
    "ssh_access": {
        "keywords": ["ssh", "secure management", "vty", "enable ssh", "remote access"],
        "example": "Enable SSH with domain name smartshift.local",
        "fields": {
            "domain_name": {"prompt": "Which IP domain name should be set for the SSH key?", "example": "smartshift.local"},
            "key_size": {"prompt": "RSA key size (modulus)?", "example": "2048", "validate": "int"},
        },
    },
    "user_account": {
        "keywords": ["user account", "local user", "create user", "add user", "username"],
        "example": "Create local user netadmin with privilege 15",
        "fields": {
            "username": {"prompt": "What username should be created?", "example": "netadmin"},
            "user_password": {"prompt": "What password for the account? (kept session-only, never logged)", "example": "Demo@123", "secret": True},
            "privilege": {"prompt": "Privilege level (0-15)?", "example": "15", "validate": "int"},
            "state": {"prompt": "Should the user be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "banner": {
        "keywords": ["banner", "login banner", "motd", "message of the day"],
        "example": "Set the login banner to 'Authorized access only'",
        "fields": {
            "banner_text": {"prompt": "What text should the banner display?", "example": "Authorized access only"},
            "banner_type": {"prompt": "Banner type (login/motd/exec)?", "example": "login"},
            "state": {"prompt": "Should the banner be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "save_config": {
        "keywords": ["save config", "save configuration", "write memory", "copy run start", "write mem"],
        "example": "Save the running configuration to startup",
        "fields": {},
    },
    "vlan": {
        "keywords": ["vlan", "virtual lan"],
        "example": "Create VLAN 30 named FINANCE",
        "fields": {
            "vlan_id": {"prompt": "Which VLAN ID (1-4094)?", "example": "30", "validate": "vlan_id"},
            "vlan_name": {"prompt": "What name should the VLAN have?", "example": "FINANCE"},
            "state": {"prompt": "Should the VLAN be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "interface_l2": {
        "keywords": ["switchport", "access port", "trunk port", "l2 interface", "assign port", "layer 2 interface"],
        "example": "Configure GigabitEthernet0/1 as an access port in VLAN 30",
        "fields": {
            "interface_name": {"prompt": "Which interface? (full name)", "example": "GigabitEthernet0/1"},
            "mode": {"prompt": "Switchport mode (access/trunk)?", "example": "access"},
            "access_vlan": {"prompt": "Which access VLAN should the port belong to?", "example": "30", "validate": "vlan_id"},
            "description": {"prompt": "Interface description?", "example": "Finance desk"},
            "admin_state": {"prompt": "Admin state (up/down)?", "example": "up"},
        },
    },
    "port_channel": {
        "keywords": ["port-channel", "port channel", "etherchannel", "lag", "link aggregation", "lacp"],
        "example": "Bundle Gi0/1 and Gi0/2 into Port-channel 10 using LACP active",
        "fields": {
            "channel_group_id": {"prompt": "Which channel-group / port-channel number?", "example": "10", "validate": "int"},
            "member_interfaces": {"prompt": "Which member interfaces? (comma-separated list)", "example": "GigabitEthernet0/1, GigabitEthernet0/2", "validate": "list"},
            "mode": {"prompt": "Channel mode (active/passive for LACP, or on for static)?", "example": "active"},
            "state": {"prompt": "Should the port-channel be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "interface_l3": {
        "keywords": ["interface ip", "ip address", "configure interface", "l3 interface", "ip on interface", "layer 3 interface"],
        "example": "Configure GigabitEthernet0/1 with IP 10.1.1.1/24",
        "fields": {
            "interface_name": {"prompt": "Which interface? (full name)", "example": "GigabitEthernet0/1"},
            "ip_address": {"prompt": "Which IPv4 address?", "example": "10.1.1.1", "validate": "ipv4"},
            "subnet_mask": {"prompt": "Subnet mask as prefix length (e.g. 24)?", "example": "24", "validate": "prefix"},
            "description": {"prompt": "Interface description?", "example": "Uplink to core"},
            "admin_state": {"prompt": "Admin state (up/down)?", "example": "up"},
        },
    },
    "static_route": {
        "keywords": ["static route", "ip route", "next hop", "route to"],
        "example": "Add a static route to 10.10.10.0/24 via 192.168.1.254",
        "fields": {
            "destination_network": {"prompt": "Destination network address?", "example": "10.10.10.0", "validate": "ipv4"},
            "subnet_mask": {"prompt": "Subnet mask as prefix length (e.g. 24)?", "example": "24", "validate": "prefix"},
            "next_hop": {"prompt": "Next-hop IP address?", "example": "192.168.1.254", "validate": "ipv4"},
            "admin_distance": {"prompt": "Administrative distance?", "example": "1", "validate": "int"},
            "state": {"prompt": "Should the route be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "ospf": {
        "keywords": ["ospf", "open shortest path first", "routing protocol ospf"],
        "example": "Enable OSPF process 1 for network 10.1.1.0 wildcard 0.0.0.255 in area 0",
        "fields": {
            "process_id": {"prompt": "OSPF process ID?", "example": "1", "validate": "int"},
            "network": {"prompt": "Network address to advertise?", "example": "10.1.1.0", "validate": "ipv4"},
            "wildcard_mask": {"prompt": "Wildcard mask?", "example": "0.0.0.255", "validate": "ipv4"},
            "area_id": {"prompt": "Which OSPF area?", "example": "0"},
            "router_id": {"prompt": "Router ID?", "example": "1.1.1.1", "validate": "ipv4"},
            "state": {"prompt": "Should the OSPF config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "acl": {
        "keywords": ["acl", "access list", "access-list", "permit", "deny traffic", "block traffic"],
        "example": "Create ACL BLOCK_GUEST to deny 10.20.0.0 to any",
        "fields": {
            "acl_name": {"prompt": "What name for the ACL?", "example": "BLOCK_GUEST"},
            "action": {"prompt": "Action (permit/deny)?", "example": "deny"},
            "source": {"prompt": "Source ('any', a host IP, or an A.B.C.D address)?", "example": "10.20.0.0"},
            "destination": {"prompt": "Destination ('any', a host IP, or an A.B.C.D address)?", "example": "any"},
            "protocol": {"prompt": "Protocol (ip/tcp/udp)?", "example": "ip"},
            "port": {"prompt": "Port (if applicable)?", "example": "80"},
            "state": {"prompt": "Should the ACL be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "ntp": {
        "keywords": ["ntp", "time server", "network time", "clock source"],
        "example": "Configure NTP server 10.0.0.200",
        "fields": {
            "ntp_server": {"prompt": "Which NTP server IP/hostname?", "example": "10.0.0.200"},
            "state": {"prompt": "Should the NTP server be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "snmp": {
        "keywords": ["snmp", "monitoring community", "snmp community", "snmp host"],
        "example": "Configure SNMP community public read-only for host 10.0.0.50",
        "fields": {
            "community": {"prompt": "SNMP community string?", "example": "public"},
            "host": {"prompt": "SNMP host (trap receiver) IP?", "example": "10.0.0.50", "validate": "ipv4"},
            "access": {"prompt": "Access (ro/rw)?", "example": "ro"},
            "version": {"prompt": "SNMP version?", "example": "2c"},
            "state": {"prompt": "Should the SNMP config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "syslog": {
        "keywords": ["syslog", "logging server", "log server", "remote logging"],
        "example": "Send syslog to 10.0.0.60 at informational level",
        "fields": {
            "syslog_server": {"prompt": "Which syslog server IP/hostname?", "example": "10.0.0.60"},
            "severity_level": {"prompt": "Severity level (e.g. informational)?", "example": "informational"},
            "state": {"prompt": "Should the syslog config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "aaa": {
        "keywords": ["aaa", "tacacs", "radius", "authentication server", "new-model"],
        "example": "Configure AAA with TACACS+ server 10.0.0.30 key Secret123",
        "fields": {
            "server_ip": {"prompt": "AAA server IP address?", "example": "10.0.0.30", "validate": "ipv4"},
            "shared_key": {"prompt": "Shared key for the AAA server? (kept session-only, never logged)", "example": "Secret123", "secret": True},
            "auth_type": {"prompt": "Authentication protocol (tacacs+ or radius)?", "example": "tacacs+"},
            "server_name": {"prompt": "A name for the AAA server entry?", "example": "AAA-SRV"},
            "state": {"prompt": "Should the AAA config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "hsrp": {
        "keywords": ["hsrp", "hot standby", "standby group", "first hop redundancy", "fhrp"],
        "example": "Configure HSRP group 1 on Vlan10 with virtual IP 10.1.1.1 priority 110",
        "fields": {
            "interface_name": {"prompt": "Which interface? (e.g. Vlan10)", "example": "Vlan10"},
            "group_id": {"prompt": "HSRP group number?", "example": "1", "validate": "int"},
            "virtual_ip": {"prompt": "Virtual (shared) IP address?", "example": "10.1.1.1", "validate": "ipv4"},
            "priority": {"prompt": "Priority (higher wins active)?", "example": "110", "validate": "int"},
            "preempt": {"prompt": "Allow preempt (true/false)?", "example": "true"},
            "state": {"prompt": "Should the HSRP config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "vrrp": {
        "keywords": ["vrrp", "virtual router redundancy"],
        "example": "Configure VRRP group 1 on Vlan10 with virtual IP 10.1.1.1 priority 110",
        "fields": {
            "interface_name": {"prompt": "Which interface? (e.g. Vlan10)", "example": "Vlan10"},
            "group_id": {"prompt": "VRRP group number?", "example": "1", "validate": "int"},
            "virtual_ip": {"prompt": "Virtual (shared) IP address?", "example": "10.1.1.1", "validate": "ipv4"},
            "priority": {"prompt": "Priority (higher wins master)?", "example": "110", "validate": "int"},
            "state": {"prompt": "Should the VRRP config be present or absent?", "example": "present", "validate": "state"},
        },
    },
    "vrf": {
        "keywords": ["vrf", "virtual routing", "routing instance", "segmentation", "tenant"],
        "example": "Create VRF CUSTOMER_A with route distinguisher 100:1",
        "fields": {
            "vrf_name": {"prompt": "What name for the VRF?", "example": "CUSTOMER_A"},
            "rd": {"prompt": "Route distinguisher (ASN:nn or A.B.C.D:nn)?", "example": "100:1"},
            "interfaces": {"prompt": "Which interfaces to bind? (comma-separated; clears their IPs)", "example": "GigabitEthernet0/2", "validate": "list"},
            "description": {"prompt": "VRF description?", "example": "Customer A tenant"},
            "state": {"prompt": "Should the VRF be present or absent?", "example": "present", "validate": "state"},
        },
    },
}


class FieldMeta(BaseModel):
    name: str
    required: bool
    prompt: str = Field(..., description="Human-readable question used in COLLECT_FIELDS")
    example: Optional[str] = None
    validate_as: Optional[str] = Field(None, description="Validator key, e.g. vlan_id/ipv4/prefix/int/list/state")
    secret: bool = False


class ConfigTypeSpec(BaseModel):
    config_type: str
    playbook_ref: str = Field(..., description="Playbook path as written in required_fields.yaml")
    playbook_file: Optional[str] = Field(None, description="Resolved absolute path on disk, if found")
    playbook_name: str = Field(..., description="Playbook basename, e.g. vlan.yml")
    playbook_rel: str = Field("", description="Path relative to the registry, e.g. layer2/vlan.yml")
    category: str = Field("general", description="Domain classification: management/layer2/layer3/security/services/redundancy/segmentation")
    target_group: str = "all"
    required_fields: list[str] = []
    optional_fields: list[str] = []
    risk: str = "low"
    keywords: list[str] = []
    example: Optional[str] = None
    fields: dict[str, FieldMeta] = {}

    def field_meta(self, name: str) -> FieldMeta:
        if name in self.fields:
            return self.fields[name]
        # Fallback for fields with no enrichment block.
        return FieldMeta(
            name=name,
            required=name in self.required_fields,
            prompt=f"Please provide a value for '{name}'.",
        )


class ConfigRegistry:
    """Loads + merges the playbook contract and the refinement metadata."""

    def __init__(self, mapping_file: str = MAPPING_FILE, registry_dir: str = REGISTRY_DIR):
        self.mapping_file = mapping_file
        self.registry_dir = registry_dir
        self._specs: dict[str, ConfigTypeSpec] = {}
        self._load()

    def _find_playbook(self, basename: str) -> Optional[str]:
        """Locate a playbook by basename anywhere under the registry directory."""
        for root, _dirs, files in os.walk(self.registry_dir):
            if basename in files:
                return os.path.join(root, basename)
        return None

    def _load(self) -> None:
        if not os.path.exists(self.mapping_file):
            logger.error("CONFIG registry mapping not found at %r", self.mapping_file)
            self._specs = {}
            return

        with open(self.mapping_file, "r", encoding="utf-8") as fh:
            mapping = yaml.safe_load(fh) or {}

        specs: dict[str, ConfigTypeSpec] = {}
        for config_type, entry in mapping.items():
            entry = entry or {}
            enrich = ENRICHMENT.get(config_type, {})
            playbook_ref = entry.get("playbook", "")
            playbook_name = os.path.basename(playbook_ref) if playbook_ref else ""
            # Path relative to the registry: drop a leading "playbooks/" convention prefix.
            rel = playbook_ref[len("playbooks/"):] if playbook_ref.startswith("playbooks/") else playbook_ref
            resolved = os.path.join(self.registry_dir, *rel.split("/")) if rel else None
            if resolved and not os.path.exists(resolved):
                # Fallback: locate the basename anywhere under the registry (resilient to
                # category/path drift between the mapping and the actual folder layout).
                found = self._find_playbook(playbook_name) if playbook_name else None
                if found:
                    resolved = found
                    rel = os.path.relpath(found, self.registry_dir).replace(os.sep, "/")
                else:
                    logger.warning(
                        "CONFIG type %r references playbook %r which is missing on disk",
                        config_type, playbook_ref,
                    )
                    resolved = None

            required = list(entry.get("required_fields", []) or [])
            optional = list(entry.get("optional_fields", []) or [])
            field_enrich = enrich.get("fields", {})

            fields: dict[str, FieldMeta] = {}
            for fname in required + optional:
                fe = field_enrich.get(fname, {})
                fields[fname] = FieldMeta(
                    name=fname,
                    required=fname in required,
                    prompt=fe.get("prompt", f"Please provide a value for '{fname}'."),
                    example=fe.get("example"),
                    validate_as=fe.get("validate"),
                    secret=fe.get("secret", False),
                )

            specs[config_type] = ConfigTypeSpec(
                config_type=config_type,
                playbook_ref=playbook_ref,
                playbook_file=resolved,
                playbook_name=playbook_name,
                playbook_rel=rel,
                category=entry.get("category", "general"),
                target_group=entry.get("target_group", "all"),
                required_fields=required,
                optional_fields=optional,
                risk=entry.get("risk", "low"),
                keywords=enrich.get("keywords", []),
                example=enrich.get("example"),
                fields=fields,
            )

        self._specs = specs
        logger.info("CONFIG registry loaded %d config types from %r", len(specs), self.mapping_file)

    # ----- public API -----
    def types(self) -> list[str]:
        return list(self._specs.keys())

    def get(self, config_type: str) -> Optional[ConfigTypeSpec]:
        return self._specs.get(config_type)

    def all(self) -> dict[str, ConfigTypeSpec]:
        return dict(self._specs)

    def match_keywords(self, text: str) -> list[str]:
        """Return every config_type whose keywords appear in the text (substring match)."""
        low = (text or "").lower()
        hits: list[str] = []
        for ctype, spec in self._specs.items():
            if any(kw in low for kw in spec.keywords):
                hits.append(ctype)
        return hits

    def examples(self, n: int = 3) -> list[str]:
        """A few example prompts for disambiguation (only advertises real capabilities)."""
        out = []
        for spec in self._specs.values():
            if spec.example:
                out.append(spec.example)
            if len(out) >= n:
                break
        return out


# Module-level singleton.
config_registry = ConfigRegistry()
