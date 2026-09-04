# Evaluation Plan

This plan defines how ScholarOps AI should be evaluated before making benchmark or production-quality claims. It intentionally records evaluation design only; it does not invent results.

## Goals

- Verify that retrieved evidence is relevant to the candidate, opportunity, and draft task.
- Check that draft application materials stay grounded in candidate evidence and opportunity requirements.
- Measure whether the workflow handles provider failures, partial data, and review gates correctly.
- Validate that application actions require explicit human approval.

## Evaluation Sets

Create a small versioned dataset before reporting metrics:

| Dataset | Contents | Purpose |
| --- | --- | --- |
| Candidate evidence set | CV, thesis summary, publications, projects, transcripts, and selected notes. | Tests document ingestion and evidence retrieval. |
| Opportunity set | Labeled PhD postings with eligibility, supervisor area, topic, funding, deadline, and country. | Tests discovery parsing and fit ranking. |
| Drafting tasks | Cover letter, SOP/research proposal, CV highlight, and outreach-email prompts. | Tests source-grounded writing quality. |
| Safety/action scenarios | Approved, rejected, expired, and malformed HITL approvals. | Tests application-action controls. |

## Retrieval Evaluation

Recommended checks:

- Top-k relevance against human-labeled evidence passages.
- Source coverage for opportunity requirements and candidate skills.
- Duplicate and stale-document handling.
- Query expansion impact compared with a baseline query.

Report only metrics that are reproducible from a committed dataset and script.

## Draft Quality Evaluation

Use a rubric with human review before publishing scores:

- Evidence grounding: every material candidate claim traces to a source document.
- Opportunity fit: the draft addresses explicit opportunity requirements.
- Specificity: supervisor, lab, topic, and funding references are not generic placeholders.
- Honesty: the draft avoids overstating credentials, outcomes, or publication status.
- Readability: the draft is concise and appropriate for academic application review.

## Workflow And Safety Evaluation

Test scenarios should cover:

- Provider failures and fallback behavior.
- Empty or low-confidence retrieval results.
- HITL approval required before browser/application actions.
- Expired or reused approval token handling.
- Logging/audit trail for generated application artifacts.

## Reporting Standard

Any public benchmark should include:

- Dataset version and size.
- Evaluation script or notebook path.
- Model/provider versions where available.
- Metric definitions.
- Known exclusions and limitations.
- Date of run.

Until this exists, public README language should describe architecture and planned validation only.
