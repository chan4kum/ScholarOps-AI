"""Shared API test helpers. Isolated SQLite via tmp_app / keyed_app."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from opportunity_intel.db import session_factory
from opportunity_intel.domain.models import (
    ApplicationPacket,
    DraftDocument,
    EvidenceItem,
    Opportunity,
    UserProfile,
)


def seed_ready_packet(client: TestClient) -> int:
    """Insert a ready packet with profile, evidence, and three drafts."""
    session = session_factory()()
    try:
        session.add(
            UserProfile(
                full_name="Chandan Kumar",
                email="chandan@example.com",
                highest_degree="MSc Data Science",
                research_interests="Agentic AI",
                skills="Python",
                target_countries="NL,DE",
            )
        )
        opp = Opportunity(
            title="PhD Agentic AI",
            organization="TU Delft",
            country_code="NL",
            source_url="https://www.tudelft.nl/jobs/phd-apply-test",
            funding="fully funded",
            supervisor="Ada Lovelace",
            deadline=date(2026, 10, 1),
            status="prepared",
            apply_channel="email",
            apply_email="phd-apply@tudelft.nl",
            apply_url="https://www.tudelft.nl/jobs/phd-apply-test",
            apply_notes="Send the packet to the listed application mailbox.",
        )
        session.add(opp)
        session.flush()
        packet = ApplicationPacket(opportunity_id=opp.id, status="ready")
        session.add(packet)
        session.flush()
        session.add(
            EvidenceItem(category="thesis", content="MSc thesis on agents", source_quote="thesis")
        )
        session.flush()
        for kind, body in (
            ("cv_tailor", "CV citing EV-1 thesis"),
            ("cover_letter", "Cover letter"),
            ("research_proposal", "Proposal citing thesis"),
        ):
            session.add(
                DraftDocument(
                    packet_id=packet.id,
                    kind=kind,
                    body=body,
                    cited_evidence_ids="[1]",
                    cited_paper_titles="[]",
                )
            )
        session.commit()
        return packet.id
    finally:
        session.close()
