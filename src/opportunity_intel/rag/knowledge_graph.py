"""Academic Knowledge Graph for ScholarOps AI using NetworkX.

Constructs a structured property graph linking:
  - Candidate (Profile, Skills, Experiences, Evidence Items)
  - Discovered Opportunities (Institutions, Requirements, Funding)
  - Professors / PIs & their Research Publications
Enables multi-hop relational retrieval to enrich RAG context with interconnected facts.
"""

from __future__ import annotations

import json
import logging

import networkx as nx
from sqlalchemy.orm import Session

from opportunity_intel.config import Settings
from opportunity_intel.domain.models import (
    EvidenceItem,
    Opportunity,
    ProfessorPaper,
    UserProfile,
)
from opportunity_intel.scoring.rules import parse_csv

logger = logging.getLogger("opportunity_intel.rag.knowledge_graph")


class AcademicKnowledgeGraph:
    """Manages the academic entity-relationship graph in NetworkX with JSON serialization."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.kg_path = settings.kg_path
        self.kg_path.parent.mkdir(parents=True, exist_ok=True)
        self.graph = nx.MultiDiGraph()
        self.load_graph()

    def load_graph(self) -> None:
        """Load the persisted graph from JSON if available."""
        if self.kg_path.exists():
            try:
                data = json.loads(self.kg_path.read_text(encoding="utf-8"))
                self.graph = nx.node_link_graph(data, directed=True, multigraph=True)
                logger.info(
                    "Loaded Knowledge Graph with %d nodes and %d edges",
                    self.graph.number_of_nodes(),
                    self.graph.number_of_edges(),
                )
            except Exception as exc:
                logger.warning("Could not load existing KG from %s: %s", self.kg_path, exc)
                self.graph = nx.MultiDiGraph()

    def save_graph(self) -> None:
        """Persist the graph to JSON."""
        try:
            data = nx.node_link_data(self.graph)
            self.kg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to save Knowledge Graph: %s", exc)

    def build_from_database(self, session: Session) -> dict[str, int]:
        """Reconstructs the full knowledge graph from SQLite database models."""
        self.graph.clear()

        # 1. Candidate Node
        profile = session.query(UserProfile).order_by(UserProfile.id).first()
        candidate_id = "candidate:me"
        cand_name = profile.full_name if profile else "Applicant"
        self.graph.add_node(
            candidate_id,
            node_type="Candidate",
            name=cand_name,
            degree=profile.highest_degree if profile else "",
            summary=profile.profile_summary if profile else "",
        )

        # 2. Skills Nodes & Edges
        skills = parse_csv(profile.skills if profile else "")
        for skill in skills:
            if not skill:
                continue
            skill_id = f"skill:{skill.lower()}"
            self.graph.add_node(skill_id, node_type="Skill", name=skill)
            self.graph.add_edge(candidate_id, skill_id, relation="HAS_SKILL")

        # 3. Research Interests
        interests = parse_csv(profile.research_interests if profile else "")
        for interest in interests:
            if not interest:
                continue
            int_id = f"interest:{interest.lower()}"
            self.graph.add_node(int_id, node_type="ResearchInterest", name=interest)
            self.graph.add_edge(candidate_id, int_id, relation="PURSUES_INTEREST")

        # 4. Evidence Items
        for ev in session.query(EvidenceItem).all():
            ev_id = f"evidence:EV-{ev.id}"
            self.graph.add_node(
                ev_id,
                node_type="EvidenceItem",
                category=ev.category or "general",
                content=ev.content or "",
                quote=ev.source_quote or "",
            )
            self.graph.add_edge(candidate_id, ev_id, relation="SUPPORTED_BY")

        # 5. Opportunities, Institutions & Supervisors
        for opp in session.query(Opportunity).all():
            opp_id = f"opportunity:{opp.id}"
            self.graph.add_node(
                opp_id,
                node_type="Opportunity",
                title=opp.title or "",
                funding=opp.funding or "",
                country=opp.country_code or "",
                url=opp.source_url or "",
            )

            # Link Institution
            if opp.organization:
                inst_id = f"institution:{opp.organization.lower()}"
                self.graph.add_node(inst_id, node_type="Institution", name=opp.organization)
                self.graph.add_edge(opp_id, inst_id, relation="HOSTED_BY")

            # Link Supervisor
            if opp.supervisor:
                sup_id = f"supervisor:{opp.supervisor.lower()}"
                self.graph.add_node(sup_id, node_type="Supervisor", name=opp.supervisor)
                self.graph.add_edge(opp_id, sup_id, relation="SUPERVISED_BY")

            # Link matched skills to opportunity
            for skill in skills:
                if (
                    skill.lower() in (opp.summary or "").lower()
                    or skill.lower() in (opp.title or "").lower()
                ):
                    skill_id = f"skill:{skill.lower()}"
                    self.graph.add_edge(opp_id, skill_id, relation="REQUIRES_SKILL")

        # 6. Professor Papers
        for paper in session.query(ProfessorPaper).all():
            paper_id = f"paper:{paper.id}"
            self.graph.add_node(
                paper_id,
                node_type="Paper",
                title=paper.title or "",
                authors=paper.authors or "",
                venue=paper.venue or "",
            )
            if paper.authors:
                sup_id = f"supervisor:{paper.authors.split(',')[0].strip().lower()}"
                if self.graph.has_node(sup_id):
                    self.graph.add_edge(sup_id, paper_id, relation="AUTHORED")

        self.save_graph()
        stats = {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
        }
        logger.info("Knowledge graph built from DB: %s", stats)
        return stats

    def get_related_subgraph_context(self, opp_id_num: int, max_depth: int = 2) -> list[str]:
        """Extract multi-hop relational context surrounding a specific opportunity."""
        opp_node = f"opportunity:{opp_id_num}"
        if not self.graph.has_node(opp_node):
            return []

        lines: list[str] = []
        opp_data = self.graph.nodes[opp_node]
        lines.append(f"Opportunity: {opp_data.get('title')} ({opp_data.get('funding', '')})")

        # Get connected neighbors
        for neighbor in self.graph.neighbors(opp_node):
            edge_data = self.graph.get_edge_data(opp_node, neighbor)
            for key, val in edge_data.items():
                rel = val.get("relation", "CONNECTED_TO")
                n_data = self.graph.nodes[neighbor]
                n_type = n_data.get("node_type", "Entity")
                n_name = n_data.get("name") or n_data.get("title") or neighbor
                lines.append(f" - [{rel}] -> {n_type}: {n_name}")

                # Check if Candidate also shares this neighbor (e.g. Skill)
                if self.graph.has_edge("candidate:me", neighbor):
                    lines.append(f"   * DIRECT MATCH: Candidate also possesses {n_name}")

        return lines
