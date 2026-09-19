"""Popula data/incidents.db com incidentes canônicos + ingere os runbooks.

Idempotente: `save_incident` faz upsert por `incident_id`, e
`ingest_runbooks` só reescreve chunks de arquivos que mudaram. Seguro
rodar em todo start de container ou quantas vezes for preciso localmente.

Uso:
    python scripts/seed_incidents.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.memory.db import connect  # noqa: E402
from app.memory.incident_repository import save_incident  # noqa: E402
from app.memory.ingest_runbooks import ingest_runbooks  # noqa: E402

INCIDENTS: list[dict] = [
    {
        "incident_id": "INC-00001",
        "service": "payments-api",
        "environment": "production",
        "category": "database_connectivity",
        "severity": "high",
        "description": (
            "Payments API failing with database connection timeouts after a traffic spike"
        ),
        "probable_cause": "Connection pool exhausted (max_size too low for the traffic spike)",
        "resolution": "Raised pool max_size from 20 to 50 and added PgBouncer in front of Postgres",
        "recommended_actions": [
            "Check database availability",
            "Inspect connection pool utilization",
            "Review recent deployment changes",
        ],
        "logs_excerpt": "ERROR connection pool exhausted; ERROR database connection timeout",
    },
    {
        "incident_id": "INC-00002",
        "service": "payments-api",
        "environment": "production",
        "category": "database_connectivity",
        "severity": "medium",
        "description": "Intermittent database connection resets during nightly batch job",
        "probable_cause": "Batch job opening too many short-lived connections",
        "resolution": "Reused a single pooled connection across the batch instead of one per row",
        "recommended_actions": [
            "Review batch job connection handling",
            "Add connection reuse",
            "Monitor pool saturation during batch window",
        ],
        "logs_excerpt": "ERROR connection reset by peer",
    },
    {
        "incident_id": "INC-00003",
        "service": "checkout-api",
        "environment": "production",
        "category": "latency_degradation",
        "severity": "high",
        "description": "Checkout API p95 latency jumped from 300ms to 4s",
        "probable_cause": "Slow downstream call to the fraud-check service without a timeout",
        "resolution": "Added a 500ms timeout and circuit breaker around the fraud-check call",
        "recommended_actions": [
            "Compare current p95/p99 latency against baseline",
            "Check downstream dependencies for slow responses",
            "Add timeout/circuit breaker",
        ],
        "logs_excerpt": "WARN latency=4200ms; WARN downstream fraud-check slow",
    },
    {
        "incident_id": "INC-00004",
        "service": "worker-jobs",
        "environment": "production",
        "category": "memory_pressure",
        "severity": "high",
        "description": "Worker pods repeatedly OOMKilled during large export jobs",
        "probable_cause": "Export job loading the entire dataset into memory instead of streaming",
        "resolution": "Rewrote export to stream results in batches of 1000 rows",
        "recommended_actions": [
            "Inspect heap/memory usage graphs",
            "Check for recent code changes introducing memory leaks",
            "Stream large exports instead of loading fully",
        ],
        "logs_excerpt": "ERROR OOMKilled; WARN heap usage 98%",
    },
    {
        "incident_id": "INC-00005",
        "service": "checkout-api",
        "environment": "production",
        "category": "deployment_regression",
        "severity": "critical",
        "description": "Error rate spiked to 40% right after the 14:32 deploy",
        "probable_cause": "New deploy introduced a null pointer on a rarely-used discount code path",
        "resolution": "Rolled back to the previous version and fixed the null check before redeploying",
        "recommended_actions": [
            "Compare error rate before/after the most recent deploy",
            "Consider rolling back",
            "Review the diff of the last deployment",
        ],
        "logs_excerpt": "ERROR NoneType has no attribute 'code'; deploy_id=2026-08-14-1432",
    },
    {
        "incident_id": "INC-00006",
        "service": "notifications-api",
        "environment": "production",
        "category": "dependency_failure",
        "severity": "medium",
        "description": "Email notifications delayed by several hours",
        "probable_cause": "Upstream email provider API degraded, retries backing up the queue",
        "resolution": "Enabled a fallback provider and added a dead-letter queue for failed sends",
        "recommended_actions": [
            "Check the status page of the affected upstream dependency",
            "Verify retry/circuit-breaker configuration",
            "Confirm a fallback path exists",
        ],
        "logs_excerpt": "ERROR upstream email-provider 503",
    },
    {
        "incident_id": "INC-00007",
        "service": "auth-api",
        "environment": "production",
        "category": "auth_failure",
        "severity": "high",
        "description": "Users unable to log in, auth-api returning 401 for valid credentials",
        "probable_cause": "Signing key rotated without updating the auth-api's key cache",
        "resolution": "Forced a cache refresh and added a shorter TTL for the signing key cache",
        "recommended_actions": [
            "Check for expired credentials, tokens or certificates",
            "Verify identity provider health",
            "Review recent auth configuration changes",
        ],
        "logs_excerpt": "ERROR 401 invalid token signature",
    },
    {
        "incident_id": "INC-00008",
        "service": "legacy-batch",
        "environment": "production",
        "category": "disk_capacity",
        "severity": "high",
        "description": "Nightly batch job failing with no space left on device",
        "probable_cause": "Old log files were never rotated, filling the data volume",
        "resolution": "Added log rotation and cleaned up 40GB of stale logs",
        "recommended_actions": [
            "Check disk usage on the affected host/volume",
            "Identify and rotate/purge large log or temp files",
            "Verify autoscaling or volume expansion policies",
        ],
        "logs_excerpt": "ERROR no space left on device",
    },
]


def main() -> None:
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.incidents_db_path)

    for incident in INCIDENTS:
        save_incident(conn, **incident)

    written = ingest_runbooks(conn, settings.runbooks_dir)
    print(
        f"Seed concluído: {len(INCIDENTS)} incidentes upsertados, "
        f"{written} chunks de runbook (re)escritos em {settings.incidents_db_path}."
    )


if __name__ == "__main__":
    main()
