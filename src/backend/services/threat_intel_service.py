"""Aggregate threat intelligence signals for canonical findings."""

from __future__ import annotations

import logging
from typing import List

from models.messages_kernel import ConfidenceLevel, ThreatSignal
from services.defender_ti_client import DefenderTIClient
from services.epss_client import EpssClient
from services.kev_client import KevClient

logger = logging.getLogger(__name__)


class ThreatIntelService:
    """High-level threat intel aggregator."""

    def __init__(
        self,
        defender_client: DefenderTIClient | None = None,
        kev_client: KevClient | None = None,
        epss_client: EpssClient | None = None,
    ) -> None:
        self._defender = defender_client or DefenderTIClient()
        self._kev = kev_client or KevClient()
        self._epss = epss_client or EpssClient()

    async def close(self) -> None:
        await self._defender.close()

    async def gather_signals(self, vuln_key: str) -> List[ThreatSignal]:
        signals: List[ThreatSignal] = []
        cve = (vuln_key or "").upper()
        if not cve.startswith("CVE-"):
            return signals

        kev_entry = await self._kev.lookup(cve)
        if kev_entry:
            details = {
                "dateAdded": kev_entry.get("dateAdded"),
                "dueDate": kev_entry.get("dueDate"),
                "shortDescription": kev_entry.get("shortDescription"),
                "requiredAction": kev_entry.get("requiredAction"),
            }
            signals.append(
                ThreatSignal(
                    source="cisa_kev",
                    signal_type="known_exploited",
                    confidence=ConfidenceLevel.HIGH,
                    details={k: v for k, v in details.items() if v},
                )
            )

        defender_payload = await self._defender.get_vulnerability(cve)
        if defender_payload:
            signals.append(self._defender.to_threat_signal(defender_payload))

        try:
            epss_entry = await self._epss.get_score(cve)
        except Exception as exc:  # keep enrichment resilient if EPSS API unavailable
            logger.debug("EPSS lookup failed for %s: %s", cve, exc)
            epss_entry = None

        if epss_entry:
            details = {
                "score": epss_entry.get("epss"),
                "percentile": epss_entry.get("percentile"),
                "date": epss_entry.get("date"),
            }
            signals.append(
                ThreatSignal(
                    source="epss",
                    signal_type="exploit_probability",
                    confidence=ConfidenceLevel.MEDIUM,
                    details={k: v for k, v in details.items() if v},
                )
            )

        return signals
