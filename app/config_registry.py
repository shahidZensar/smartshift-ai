"""
CONFIG-intent playbook registry.

The PLAYBOOK FILES ARE THE SINGLE SOURCE OF TRUTH. There is no required_fields.yaml
anymore — the contract for each config type is derived directly from the vetted
playbook by walking `repositories/playbook-registry/<category>/*.yml` and parsing:

  • config_type   — from the `# CONFIG intent: <TYPE>` header
  • category       — from the containing sub-directory (management/layer2/…)
  • required_fields / optional_fields — from the `# required_fields:` / `# optional:`
                     header lines (author intent), cross-checked with the playbook's
                     Jinja `{{ vars }}`
  • target_group   — from `hosts: "{{ target_hosts | default('…') }}"`
  • risk           — `high` when the playbook pushes command templates
                     (`ios_config` + `lines:`), else `low`

A second layer, ENRICHMENT (below, keyed by config_type), adds agent-side refinement
metadata that is NOT part of the playbook contract: per-type `keywords`, a
disambiguation `example`, and per-field prompt/example/validator.

Adding a new config type = drop a playbook in the right category folder (with the
standard header comments) + optionally a keywords/field block below. No other changes.
"""
import os
import re
from typing import Optional

from pydantic import BaseModel, Field

from . import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Registry directory: smartshift-ai/repositories/playbook-registry
DEFAULT_REGISTRY_DIR = os.path.normpath(
    os.path.join(BASE_DIR, "..", "repositories", "playbook-registry")
)
REGISTRY_DIR = os.getenv("CONFIG_REGISTRY_DIR", DEFAULT_REGISTRY_DIR)

# Sensible display/iteration order for types (by domain).
_CATEGORY_ORDER = ["management", "layer2", "layer3", "security", "services",
                   "redundancy", "segmentation", "general"]


# ---------------------------------------------------------------------------
# Agent-side refinement metadata (keywords + per-field prompts + disambig example)
# Keyed by config_type. Field metadata is keyed by the EXACT field name the playbook
# uses so the two layers line up.
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
    playbook_file: Optional[str] = Field(None, description="Resolved absolute path on disk, if found")
    playbook_name: str = Field("", description="Playbook basename, e.g. vlan.yml")
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


def _clean_field_list(raw: str) -> list[str]:
    """Parse a `# required_fields:`/`# optional:` header value into field names.

    Strips parenthetical notes ("member_interfaces (list)" -> "member_interfaces"),
    handles "(none)"/empty, and de-dupes while preserving order.
    """
    raw = (raw or "").strip()
    if not raw or raw.lower() in ("(none)", "none", "-"):
        return []
    out: list[str] = []
    for part in raw.split(","):
        name = re.sub(r"\(.*?\)", "", part).strip()           # drop "(...)" notes
        name = name.strip(" .`")
        if name and name not in out:
            out.append(name)
    return out


def parse_playbook_contract(text: str) -> dict:
    """Derive a config type's contract straight from the vetted playbook text.

    The playbook is the single source of truth — see module docstring.
    """
    # config_type: first token after "CONFIG intent:"
    m = re.search(r"#\s*CONFIG intent:\s*([A-Za-z0-9_]+)", text)
    config_type = m.group(1).lower() if m else None

    req_m = re.search(r"#\s*required_fields?:\s*(.+)", text)
    opt_m = re.search(r"#\s*optional:\s*(.+)", text)
    required = _clean_field_list(req_m.group(1)) if req_m else []
    optional = _clean_field_list(opt_m.group(1)) if opt_m else []

    # target group from `hosts: "{{ target_hosts | default('routers') }}"`
    tg = re.search(r"target_hosts\s*\|\s*default\(\s*'([^']+)'\s*\)", text)
    target_group = tg.group(1) if tg else "all"

    # risk: command-template playbooks (ios_config + lines:) are high-risk.
    risk = "high" if ("ios_config" in text and "lines:" in text) else "low"

    return {
        "config_type": config_type,
        "required_fields": required,
        "optional_fields": optional,
        "target_group": target_group,
        "risk": risk,
    }


class ConfigRegistry:
    """Builds the type catalogue by parsing the vetted playbooks (no YAML index)."""

    def __init__(self, registry_dir: str = REGISTRY_DIR):
        self.registry_dir = registry_dir
        self._specs: dict[str, ConfigTypeSpec] = {}
        self._load()

    def _discover_playbooks(self) -> list[str]:
        """All *.yml/*.yaml playbooks under the registry (skip non-playbook files)."""
        found = []
        for root, _dirs, files in os.walk(self.registry_dir):
            for fn in files:
                if fn.lower().endswith((".yml", ".yaml")):
                    found.append(os.path.join(root, fn))
        return sorted(found)

    def _load(self) -> None:
        if not os.path.isdir(self.registry_dir):
            logger.error("CONFIG registry dir not found at %r", self.registry_dir)
            self._specs = {}
            return

        specs: dict[str, ConfigTypeSpec] = {}
        for path in self._discover_playbooks():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as exc:
                logger.warning("CONFIG registry: cannot read %r: %s", path, exc)
                continue

            contract = parse_playbook_contract(text)
            config_type = contract["config_type"]
            if not config_type:
                # Not a CONFIG playbook (e.g. a stray file) — skip silently.
                continue
            if config_type in specs:
                logger.warning("CONFIG registry: duplicate type %r (%s) — keeping first",
                               config_type, path)
                continue

            rel = os.path.relpath(path, self.registry_dir).replace(os.sep, "/")
            category = rel.split("/")[0] if "/" in rel else "general"

            enrich = ENRICHMENT.get(config_type, {})
            required = contract["required_fields"]
            optional = contract["optional_fields"]
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
                playbook_file=path,
                playbook_name=os.path.basename(path),
                playbook_rel=rel,
                category=category,
                target_group=contract["target_group"],
                required_fields=required,
                optional_fields=optional,
                risk=contract["risk"],
                keywords=enrich.get("keywords", []),
                example=enrich.get("example"),
                fields=fields,
            )

        # Order by domain for stable iteration / disambiguation examples.
        def _sort_key(item):
            cat = item[1].category
            return (_CATEGORY_ORDER.index(cat) if cat in _CATEGORY_ORDER else 99,
                    item[1].config_type)

        self._specs = dict(sorted(specs.items(), key=_sort_key))
        logger.info("CONFIG registry derived %d config types from playbooks in %r",
                    len(self._specs), self.registry_dir)

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
