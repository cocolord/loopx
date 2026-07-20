from __future__ import annotations

from typing import Any


FINANCE_EXTENSION_ID = "loopx-finance-value-discovery"
LEGACY_FINANCE_CONNECTOR_ID = "finance_market_snapshot"
FINANCE_EXTENSION_MIGRATION_SCHEMA_VERSION = (
    "value_connector_extension_migration_v0"
)


def build_finance_extension_migration_contract() -> dict[str, Any]:
    """Describe the bounded route from the retired connector to the extension."""

    return {
        "schema_version": FINANCE_EXTENSION_MIGRATION_SCHEMA_VERSION,
        "status": "migrated_to_extension",
        "legacy_connector_id": LEGACY_FINANCE_CONNECTOR_ID,
        "replacement_extension_id": FINANCE_EXTENSION_ID,
        "replacement_capability_id": None,
        "provider_distribution": "co_located_source_package",
        "automatic_provider_install_supported": False,
        "packaged_loopx_only_start_supported": False,
        "agent_start_mode": "guided_when_provider_source_is_available",
        "recommended_action": "inspect_then_install_register_run",
        "source_checkout_required": True,
        "source_checkout_paths": {
            "package": "extensions/loopx-finance-value-discovery",
            "manifest": "extensions/loopx-finance-value-discovery/extension.toml",
            "example_input": (
                "extensions/loopx-finance-value-discovery/examples/"
                "paypal-debeta-discovery.json"
            ),
        },
        "agent_start_sequence": [
            {
                "step": "inspect_installed_extensions",
                "command": "loopx extension list --format json",
                "local_environment_write": False,
            },
            {
                "step": "install_provider_from_source_checkout",
                "command": (
                    "python3 -m pip install "
                    "./extensions/loopx-finance-value-discovery"
                ),
                "local_environment_write": True,
                "condition": "provider entrypoint is absent and source checkout exists",
            },
            {
                "step": "register_extension",
                "command": (
                    "loopx extension install --manifest "
                    "extensions/loopx-finance-value-discovery/extension.toml "
                    "--execute --format json"
                ),
                "local_environment_write": True,
                "condition": "provider entrypoint is installed but extension is absent",
            },
            {
                "step": "run_extension",
                "command": (
                    "loopx extension run loopx-finance-value-discovery "
                    "--input-json "
                    "extensions/loopx-finance-value-discovery/examples/"
                    "paypal-debeta-discovery.json --execute --format json"
                ),
                "local_environment_write": False,
                "condition": "extension is installed, enabled, and doctor-ready",
            },
        ],
        "blocked_when": [
            "the separately distributed provider source or package is unavailable",
            "local environment writes are not authorized",
            "extension doctor does not pass",
        ],
        "truth_contract": {
            "legacy_connector_executes_finance": False,
            "finance_capability_registered": False,
            "provider_install_is_implicit": False,
            "external_reads_performed": False,
            "external_writes_performed": False,
        },
    }
