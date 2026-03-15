"""Contract Review & Revise skill — guided workflow for contract analysis."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from skills import BaseSkill, register_skill
from skills.models import SkillSession, SkillResponse
from document_processor import parse_document, apply_revisions, generate_revision_summary
from redline_generator import generate_redline
from claude_runner import ClaudeRunner

UPLOADS_DIR = Path(__file__).parent.parent / "uploads"
PLAYBOOKS_DIR = Path.home() / ".claude-code-web" / "playbooks"

PARTY_OPTIONS = [
    "Buyer", "Seller", "Licensor", "Licensee",
    "Customer", "Vendor", "Landlord", "Tenant",
    "Employer", "Employee", "Lender", "Borrower",
]

REVIEW_SYSTEM_PROMPT = """You are a contract review attorney representing {party}.

You are reviewing the following contract. For each issue you identify, you MUST respond with a JSON array of issue objects. Output ONLY the JSON array, no other text.

Each issue object:
{{
  "section": "section name from the contract",
  "clause_text": "the exact original text of the problematic clause (copy it verbatim)",
  "issue": "description of the problem",
  "confidence": <1-4>,
  "suggested_revision": "the revised clause text",
  "alternatives": ["alternative revision 1", "alternative revision 2"],
  "reasoning": "why this change matters for {party}"
}}

Confidence levels:
- 1: Standard/minor language tweak (still requires user approval)
- 2: Moderate issue with clear best practice fix
- 3: Significant issue with multiple viable approaches
- 4: Critical/complex issue requiring user's specific legal judgment

{playbook_instructions}

Review these sections: {scope}

CONTRACT TEXT:
{contract_text}"""

QA_SYSTEM_PROMPT = """You are a contract review attorney representing {party}.
You are in an interactive Q&A session about a contract review.

Previous decisions made:
{decisions}

Current context: The user is asking a follow-up question about the contract.
Answer based on the contract text and prior decisions. If the question leads to
a new revision, respond with JSON:
{{"new_revision": true, "section": "...", "clause_text": "...", "issue": "...",
  "confidence": 3, "suggested_revision": "...", "alternatives": [], "reasoning": "..."}}

Otherwise respond with plain text.

CONTRACT TEXT:
{contract_text}"""


class ContractReviewSkill(BaseSkill):
    id = "contract-review"
    name = "Contract Review & Revise"
    icon = "📋"
    description = "Upload a contract, review terms, approve revisions, and generate a redline."
    stages = [
        "upload", "playbook", "party", "scope",
        "initial_review", "qa_session", "revisions",
        "redline", "summary",
    ]

    async def get_stage_prompt(self, session: SkillSession) -> SkillResponse:
        stage = session.current_stage

        if stage == "upload":
            return SkillResponse(
                type="question",
                content="Upload the contract you'd like to review. Drag and drop or click to select a `.docx` file.",
                confidence=4,
                stage=stage,
                metadata={"input_type": "file", "accept": ".docx"},
            )

        elif stage == "playbook":
            return SkillResponse(
                type="question",
                content="Do you have an existing review playbook to guide the analysis? Upload a `.docx` or `.json` playbook, or skip to start fresh.",
                confidence=4,
                options=["Skip — start fresh"],
                stage=stage,
                metadata={"input_type": "file_or_choice", "accept": ".docx,.json"},
            )

        elif stage == "party":
            return SkillResponse(
                type="question",
                content="Which party do you represent in this agreement?",
                confidence=4,
                options=PARTY_OPTIONS + ["Other"],
                stage=stage,
            )

        elif stage == "scope":
            sections = session.context.get("section_names", [])
            return SkillResponse(
                type="question",
                content="Which sections would you like to review? Select specific sections or review the entire document.",
                confidence=4,
                options=["Entire Document"] + sections,
                stage=stage,
                metadata={"multi_select": True},
            )

        elif stage == "initial_review":
            return SkillResponse(
                type="info",
                content="Starting contract review. Claude will analyze the document and identify issues...",
                confidence=1,
                stage=stage,
                metadata={"auto_advance": True},
            )

        elif stage == "qa_session":
            return SkillResponse(
                type="info",
                content="Review complete. Let's go through each issue. You must approve, modify, or reject each proposed revision.\n\nYou can also ask follow-up questions at any time. Type **done** when you're finished.",
                confidence=2,
                stage=stage,
            )

        elif stage == "revisions":
            return SkillResponse(
                type="info",
                content="Applying your approved revisions to the document...",
                confidence=1,
                stage=stage,
                metadata={"auto_advance": True},
            )

        elif stage == "redline":
            return SkillResponse(
                type="info",
                content="Generating redline comparison document...",
                confidence=1,
                stage=stage,
                metadata={"auto_advance": True},
            )

        elif stage == "summary":
            return SkillResponse(
                type="complete",
                content="Review complete! Your files are ready for download.",
                confidence=1,
                stage=stage,
            )

        return SkillResponse(type="error", content="Unknown stage", stage=stage)

    async def handle_message(
        self,
        session: SkillSession,
        user_input: str,
        uploaded_file: Optional[dict] = None,
    ) -> list[SkillResponse]:
        stage = session.current_stage
        responses: list[SkillResponse] = []

        if stage == "upload":
            responses = await self._handle_upload(session, uploaded_file)
        elif stage == "playbook":
            responses = await self._handle_playbook(session, user_input, uploaded_file)
        elif stage == "party":
            responses = await self._handle_party(session, user_input)
        elif stage == "scope":
            responses = await self._handle_scope(session, user_input)
        elif stage == "initial_review":
            responses = await self._handle_initial_review(session)
        elif stage == "qa_session":
            responses = await self._handle_qa(session, user_input)
        elif stage == "revisions":
            responses = await self._handle_revisions(session)
        elif stage == "redline":
            responses = await self._handle_redline(session)
        elif stage == "summary":
            responses = await self._handle_summary(session)

        return responses

    # ── Stage handlers ──────────────────────────────────────────

    async def _handle_upload(
        self, session: SkillSession, uploaded_file: Optional[dict]
    ) -> list[SkillResponse]:
        if not uploaded_file or not uploaded_file.get("path"):
            return [SkillResponse(
                type="question",
                content="Please upload a `.docx` file to continue.",
                confidence=4,
                stage="upload",
                metadata={"input_type": "file", "accept": ".docx"},
            )]

        file_path = uploaded_file["path"]
        filename = uploaded_file.get("filename", "contract.docx")
        session.files["original"] = file_path
        session.context["original_filename"] = filename

        # Parse document
        doc_data = parse_document(file_path)
        session.context["sections"] = doc_data["sections"]
        session.context["section_names"] = doc_data["section_names"]
        session.context["full_text"] = doc_data["full_text"]
        session.context["paragraph_count"] = doc_data["paragraph_count"]

        self.log_transcript(
            session,
            claude_message=f"Document uploaded: {filename}",
            decision=f"Parsed {doc_data['section_count']} sections, {doc_data['paragraph_count']} paragraphs",
            confidence=1,
            section="upload",
        )

        self.advance_stage(session)

        section_list = "\n".join(f"  • {name}" for name in doc_data["section_names"])
        return [
            SkillResponse(
                type="info",
                content=f"**{filename}** loaded successfully.\n\n"
                        f"**{doc_data['section_count']}** sections detected, "
                        f"**{doc_data['paragraph_count']}** paragraphs.\n\n"
                        f"**Sections found:**\n{section_list}",
                confidence=1,
                stage="upload",
            ),
            await self.get_stage_prompt(session),
        ]

    async def _handle_playbook(
        self, session: SkillSession, user_input: str, uploaded_file: Optional[dict]
    ) -> list[SkillResponse]:
        if user_input.lower().startswith("skip") or "fresh" in user_input.lower():
            session.context["playbook"] = None
            self.log_transcript(
                session,
                claude_message="Playbook option presented",
                user_response="Skipped — starting fresh",
                decision="No playbook",
                confidence=4,
            )
            self.advance_stage(session)
            return [
                SkillResponse(type="info", content="Starting fresh — no playbook loaded.", confidence=1, stage="playbook"),
                await self.get_stage_prompt(session),
            ]

        if uploaded_file and uploaded_file.get("path"):
            file_path = uploaded_file["path"]
            filename = uploaded_file.get("filename", "playbook")
            session.files["playbook"] = file_path

            if filename.endswith(".json"):
                with open(file_path) as f:
                    playbook = json.load(f)
            else:
                # Parse playbook from docx
                pb_data = parse_document(file_path)
                playbook = {"rules": [], "raw_text": pb_data["full_text"]}

            session.context["playbook"] = playbook
            rule_count = len(playbook.get("rules", []))
            self.log_transcript(
                session,
                claude_message="Playbook uploaded",
                user_response=filename,
                decision=f"Loaded playbook with {rule_count} rules",
                confidence=1,
            )
            self.advance_stage(session)
            return [
                SkillResponse(
                    type="info",
                    content=f"Playbook **{filename}** loaded ({rule_count} rules).",
                    confidence=1,
                    stage="playbook",
                ),
                await self.get_stage_prompt(session),
            ]

        return [SkillResponse(
            type="question",
            content="Upload a playbook file or click 'Skip' to start fresh.",
            confidence=4,
            options=["Skip — start fresh"],
            stage="playbook",
            metadata={"input_type": "file_or_choice", "accept": ".docx,.json"},
        )]

    async def _handle_party(self, session: SkillSession, user_input: str) -> list[SkillResponse]:
        party = user_input.strip()
        session.context["party"] = party

        self.log_transcript(
            session,
            claude_message="Which party do you represent?",
            user_response=party,
            decision=f"Representing: {party}",
            confidence=4,
        )

        self.advance_stage(session)
        return [
            SkillResponse(
                type="info",
                content=f"You're representing the **{party}**. All review will be from this perspective.",
                confidence=1,
                stage="party",
            ),
            await self.get_stage_prompt(session),
        ]

    async def _handle_scope(self, session: SkillSession, user_input: str) -> list[SkillResponse]:
        if "entire" in user_input.lower() or "all" in user_input.lower():
            scope = session.context["section_names"]
            scope_desc = "Entire Document"
        else:
            # Parse comma-separated or multi-select input
            scope = [s.strip() for s in user_input.split(",") if s.strip()]
            scope_desc = ", ".join(scope)

        session.context["scope"] = scope
        session.context["scope_description"] = scope_desc

        self.log_transcript(
            session,
            claude_message="Select review scope",
            user_response=scope_desc,
            decision=f"Reviewing: {scope_desc}",
            confidence=4,
        )

        self.advance_stage(session)
        return [
            SkillResponse(
                type="info",
                content=f"Review scope set to: **{scope_desc}**\n\nStarting analysis...",
                confidence=1,
                stage="scope",
            ),
            await self.get_stage_prompt(session),
        ]

    async def _handle_initial_review(self, session: SkillSession) -> list[SkillResponse]:
        party = session.context.get("party", "Client")
        scope = session.context.get("scope_description", "Entire Document")
        contract_text = session.context.get("full_text", "")
        playbook = session.context.get("playbook")

        playbook_instructions = ""
        if playbook:
            if playbook.get("rules"):
                rules_text = json.dumps(playbook["rules"], indent=2)
                playbook_instructions = f"Apply these playbook rules where applicable:\n{rules_text}"
            elif playbook.get("raw_text"):
                playbook_instructions = f"Consider this playbook guidance:\n{playbook['raw_text'][:3000]}"

        prompt = REVIEW_SYSTEM_PROMPT.format(
            party=party,
            scope=scope,
            contract_text=contract_text[:15000],  # Limit to avoid token issues
            playbook_instructions=playbook_instructions,
        )

        # Run through Claude CLI
        runner = ClaudeRunner()
        full_response = ""
        async for event in runner.run(
            prompt=prompt,
            model="sonnet",
            working_dir=str(UPLOADS_DIR),
            auto_approve=True,
        ):
            if event.get("type") == "result":
                full_response = event.get("result", "")

        # Parse issues from response
        issues = self._parse_issues(full_response)
        session.pending_revisions = issues
        session.revision_index = 0
        session.context["issue_count"] = len(issues)

        self.log_transcript(
            session,
            claude_message=f"Initial review complete: {len(issues)} issues found",
            decision=f"Found {len(issues)} issues across contract",
            confidence=1,
        )

        self.advance_stage(session)

        # Build summary of issues by confidence
        conf_counts = {1: 0, 2: 0, 3: 0, 4: 0}
        for issue in issues:
            c = issue.get("confidence", 2)
            conf_counts[min(max(c, 1), 4)] += 1

        summary = (
            f"**Review complete — {len(issues)} issues identified.**\n\n"
            f"| Level | Count | Meaning |\n"
            f"|-------|-------|---------|\n"
            f"| 1 (Minor) | {conf_counts[1]} | Standard language tweak |\n"
            f"| 2 (Moderate) | {conf_counts[2]} | Clear best-practice fix |\n"
            f"| 3 (Significant) | {conf_counts[3]} | Multiple viable approaches |\n"
            f"| 4 (Critical) | {conf_counts[4]} | Requires your legal judgment |\n\n"
            f"**Every revision requires your approval.** Let's go through them one by one."
        )

        responses: list[SkillResponse] = [
            SkillResponse(type="info", content=summary, confidence=1, stage="initial_review"),
        ]

        # Present first revision for approval
        if issues:
            responses.append(self._present_revision(session))

        return responses

    async def _handle_qa(self, session: SkillSession, user_input: str) -> list[SkillResponse]:
        lower = user_input.strip().lower()

        # Check if user is done
        if lower == "done":
            approved_count = len(session.approved_revisions)
            if approved_count == 0:
                return [SkillResponse(
                    type="question",
                    content="No revisions were approved. Are you sure you want to finish without changes?",
                    confidence=4,
                    options=["Yes, finish", "No, continue reviewing"],
                    stage="qa_session",
                )]
            self.advance_stage(session)
            return [
                SkillResponse(
                    type="info",
                    content=f"**{approved_count}** revisions approved. Proceeding to apply changes...",
                    confidence=1,
                    stage="qa_session",
                ),
                await self.get_stage_prompt(session),
            ]

        if lower in ("yes, finish", "yes"):
            self.advance_stage(session)
            return [await self.get_stage_prompt(session)]

        if lower in ("no, continue reviewing", "no, continue"):
            if session.revision_index < len(session.pending_revisions):
                return [self._present_revision(session)]
            return [SkillResponse(
                type="info",
                content="All issues have been reviewed. Type **done** to proceed, or ask follow-up questions.",
                confidence=2,
                stage="qa_session",
            )]

        # Handle approval/rejection of current revision
        idx = session.revision_index
        pending = session.pending_revisions

        if idx <= len(pending):
            current = pending[idx - 1] if idx > 0 else None

            if current and lower in ("approve", "yes", "accept", "ok", "a"):
                session.approved_revisions.append(current)
                self.log_transcript(
                    session,
                    claude_message=f"Revision for {current.get('section', 'unknown')}: {current.get('issue', '')}",
                    user_response="Approved",
                    decision=f"Approved: {current.get('description', current.get('issue', ''))}",
                    confidence=current.get("confidence", 2),
                    section=current.get("section", ""),
                )

                if session.revision_index < len(pending):
                    return [
                        SkillResponse(
                            type="info",
                            content="**Approved.** ✓",
                            confidence=1,
                            stage="qa_session",
                        ),
                        self._present_revision(session),
                    ]
                else:
                    return [SkillResponse(
                        type="info",
                        content=f"**Approved.** ✓\n\nAll {len(pending)} issues reviewed. "
                                f"**{len(session.approved_revisions)}** approved. "
                                f"Type **done** to apply revisions, or ask follow-up questions.",
                        confidence=2,
                        stage="qa_session",
                    )]

            elif current and lower in ("reject", "no", "skip", "deny", "r", "s"):
                self.log_transcript(
                    session,
                    claude_message=f"Revision for {current.get('section', 'unknown')}: {current.get('issue', '')}",
                    user_response="Rejected",
                    decision=f"Rejected: {current.get('description', current.get('issue', ''))}",
                    confidence=current.get("confidence", 2),
                    section=current.get("section", ""),
                )

                if session.revision_index < len(pending):
                    return [
                        SkillResponse(
                            type="info",
                            content="**Rejected.** Skipping this revision.",
                            confidence=1,
                            stage="qa_session",
                        ),
                        self._present_revision(session),
                    ]
                else:
                    return [SkillResponse(
                        type="info",
                        content=f"**Rejected.**\n\nAll {len(pending)} issues reviewed. "
                                f"**{len(session.approved_revisions)}** approved. "
                                f"Type **done** to apply revisions, or ask follow-up questions.",
                        confidence=2,
                        stage="qa_session",
                    )]

            elif current and lower.startswith("modify"):
                # User wants to provide custom revision text
                custom_text = user_input[len("modify"):].strip().lstrip(":").strip()
                if custom_text:
                    modified = {**current, "suggested_revision": custom_text}
                    session.approved_revisions.append(modified)
                    self.log_transcript(
                        session,
                        claude_message=f"Revision for {current.get('section', 'unknown')}",
                        user_response=f"Modified: {custom_text[:200]}",
                        decision="Approved with user modification",
                        confidence=current.get("confidence", 2),
                        section=current.get("section", ""),
                    )
                    if session.revision_index < len(pending):
                        return [
                            SkillResponse(type="info", content="**Approved with your modification.** ✓", confidence=1, stage="qa_session"),
                            self._present_revision(session),
                        ]
                    return [SkillResponse(
                        type="info",
                        content="**Approved with modification.** ✓\n\nAll issues reviewed. Type **done** to proceed.",
                        confidence=2,
                        stage="qa_session",
                    )]
                else:
                    return [SkillResponse(
                        type="question",
                        content="Please provide your revised text after 'modify:'\n\nExample: `modify: The Seller shall indemnify the Buyer for...`",
                        confidence=4,
                        stage="qa_session",
                    )]

            elif current and lower.startswith("alt"):
                # User selects an alternative
                alts = current.get("alternatives", [])
                try:
                    alt_num = int(lower.replace("alt", "").strip()) - 1
                    if 0 <= alt_num < len(alts):
                        modified = {**current, "suggested_revision": alts[alt_num]}
                        session.approved_revisions.append(modified)
                        self.log_transcript(
                            session,
                            claude_message=f"Alternative selected for {current.get('section', '')}",
                            user_response=f"Selected alternative {alt_num + 1}",
                            decision=f"Approved alternative: {alts[alt_num][:100]}",
                            confidence=current.get("confidence", 2),
                            section=current.get("section", ""),
                        )
                        if session.revision_index < len(pending):
                            return [
                                SkillResponse(type="info", content=f"**Approved alternative {alt_num + 1}.** ✓", confidence=1, stage="qa_session"),
                                self._present_revision(session),
                            ]
                        return [SkillResponse(
                            type="info",
                            content=f"**Approved alternative.** ✓\n\nAll issues reviewed. Type **done** to proceed.",
                            confidence=2,
                            stage="qa_session",
                        )]
                except (ValueError, IndexError):
                    pass

        # If input doesn't match a command, treat as follow-up question
        return await self._handle_followup(session, user_input)

    async def _handle_followup(self, session: SkillSession, question: str) -> list[SkillResponse]:
        """Handle free-form follow-up questions during Q&A."""
        party = session.context.get("party", "Client")
        contract_text = session.context.get("full_text", "")[:10000]
        decisions = json.dumps([
            {"section": r.get("section"), "decision": r.get("description", r.get("issue", ""))}
            for r in session.approved_revisions
        ], indent=2)

        prompt = QA_SYSTEM_PROMPT.format(
            party=party,
            contract_text=contract_text,
            decisions=decisions,
        ) + f"\n\nUser question: {question}"

        runner = ClaudeRunner()
        full_response = ""
        async for event in runner.run(
            prompt=prompt,
            model="sonnet",
            working_dir=str(UPLOADS_DIR),
            auto_approve=True,
        ):
            if event.get("type") == "result":
                full_response = event.get("result", "")

        self.log_transcript(
            session,
            claude_message=full_response[:500],
            user_response=question,
            confidence=4,
            section="follow-up",
        )

        # Check if response contains a new revision
        try:
            parsed = json.loads(full_response)
            if isinstance(parsed, dict) and parsed.get("new_revision"):
                revision = self._normalize_issue(parsed)
                session.pending_revisions.append(revision)
                return [
                    SkillResponse(
                        type="info",
                        content=full_response if not parsed.get("new_revision") else f"Based on your question, I've identified an additional revision:\n\n**{revision.get('issue', '')}**",
                        confidence=2,
                        stage="qa_session",
                    ),
                    self._present_revision_specific(session, revision, len(session.pending_revisions)),
                ]
        except (json.JSONDecodeError, TypeError):
            pass

        return [SkillResponse(
            type="info",
            content=full_response,
            confidence=2,
            stage="qa_session",
        )]

    async def _handle_revisions(self, session: SkillSession) -> list[SkillResponse]:
        if not session.approved_revisions:
            self.advance_stage(session)  # skip to redline
            self.advance_stage(session)  # skip to summary
            return [
                SkillResponse(
                    type="info",
                    content="No revisions to apply. Proceeding to summary.",
                    confidence=1,
                    stage="revisions",
                ),
                await self.get_stage_prompt(session),
            ]

        original_path = session.files.get("original", "")
        filename = session.context.get("original_filename", "contract.docx")
        revised_name = filename.replace(".docx", "_revised.docx")
        revised_path = str(UPLOADS_DIR / session.id / revised_name)

        os.makedirs(os.path.dirname(revised_path), exist_ok=True)

        # Build revision list for apply_revisions
        revisions = []
        for rev in session.approved_revisions:
            revisions.append({
                "original_text": rev.get("clause_text", ""),
                "revised_text": rev.get("suggested_revision", ""),
                "section": rev.get("section", ""),
                "description": rev.get("issue", rev.get("description", "")),
            })

        apply_revisions(original_path, revisions, revised_path)
        session.files["revised"] = revised_path
        session.context["revised_filename"] = revised_name

        summary = generate_revision_summary(revisions)

        self.log_transcript(
            session,
            claude_message=f"Applied {len(revisions)} revisions to document",
            decision=f"Created {revised_name}",
            confidence=1,
        )

        self.advance_stage(session)
        return [
            SkillResponse(
                type="info",
                content=f"**{len(revisions)} revisions applied** to create `{revised_name}`.\n\n{summary}",
                confidence=1,
                stage="revisions",
                metadata={"download": revised_name, "file_key": "revised"},
            ),
            await self.get_stage_prompt(session),
        ]

    async def _handle_redline(self, session: SkillSession) -> list[SkillResponse]:
        original_path = session.files.get("original", "")
        revised_path = session.files.get("revised", "")

        if not revised_path:
            self.advance_stage(session)
            return [await self.get_stage_prompt(session)]

        filename = session.context.get("original_filename", "contract.docx")
        redline_name = filename.replace(".docx", "_redline.docx")
        redline_path = str(UPLOADS_DIR / session.id / redline_name)

        result = generate_redline(original_path, revised_path, redline_path)
        session.files["redline"] = result["path"]
        session.context["redline_filename"] = redline_name

        self.log_transcript(
            session,
            claude_message=f"Redline generated using {result['method']}",
            decision=f"Created {redline_name}",
            confidence=1,
        )

        self.advance_stage(session)
        return [
            SkillResponse(
                type="info",
                content=f"**Redline generated** using {result['method']}.\n\n"
                        f"Download: `{redline_name}`",
                confidence=1,
                stage="redline",
                metadata={"download": redline_name, "file_key": "redline"},
            ),
            await self.get_stage_prompt(session),
        ]

    async def _handle_summary(self, session: SkillSession) -> list[SkillResponse]:
        # Generate playbook from this session
        playbook = self._generate_playbook(session)
        playbook_path = self._save_playbook(session, playbook)
        session.files["playbook"] = playbook_path

        # Generate transcript document
        transcript_path = self._save_transcript(session)
        session.files["transcript"] = transcript_path

        # Build file download list
        files = []
        if session.files.get("revised"):
            files.append(f"• **{session.context.get('revised_filename', 'revised.docx')}** — Revised contract")
        if session.files.get("redline"):
            files.append(f"• **{session.context.get('redline_filename', 'redline.docx')}** — Redline comparison")
        files.append(f"• **playbook.json** — Reusable review playbook ({len(playbook.get('rules', []))} rules)")
        files.append(f"• **transcript.json** — Full review transcript ({len(session.transcript)} entries)")

        file_list = "\n".join(files)

        return [SkillResponse(
            type="complete",
            content=f"## Review Complete\n\n"
                    f"**Party:** {session.context.get('party', 'N/A')}\n"
                    f"**Scope:** {session.context.get('scope_description', 'N/A')}\n"
                    f"**Issues found:** {session.context.get('issue_count', 0)}\n"
                    f"**Revisions approved:** {len(session.approved_revisions)}\n\n"
                    f"### Files Ready for Download\n{file_list}\n\n"
                    f"The playbook has been saved for future reviews.",
            confidence=1,
            stage="summary",
            metadata={
                "downloads": {
                    k: v for k, v in session.files.items()
                    if k in ("revised", "redline", "playbook", "transcript")
                }
            },
        )]

    # ── Helpers ─────────────────────────────────────────────────

    def _present_revision(self, session: SkillSession) -> SkillResponse:
        """Present the next pending revision for user approval."""
        idx = session.revision_index
        pending = session.pending_revisions

        if idx >= len(pending):
            return SkillResponse(
                type="info",
                content=f"All {len(pending)} issues reviewed. **{len(session.approved_revisions)}** approved.\n\n"
                        f"Type **done** to apply revisions, or ask follow-up questions.",
                confidence=2,
                stage="qa_session",
            )

        issue = pending[idx]
        session.revision_index = idx + 1
        return self._present_revision_specific(session, issue, idx + 1)

    def _present_revision_specific(
        self, session: SkillSession, issue: dict, num: int
    ) -> SkillResponse:
        total = len(session.pending_revisions)
        conf = issue.get("confidence", 2)
        conf_labels = {1: "Minor", 2: "Moderate", 3: "Significant", 4: "Critical"}
        conf_label = conf_labels.get(conf, "Unknown")

        content = (
            f"### Issue {num}/{total} — {issue.get('section', 'Unknown Section')}\n"
            f"**Confidence:** {conf} ({conf_label})\n\n"
            f"**Issue:** {issue.get('issue', '')}\n\n"
            f"**Current clause:**\n> {issue.get('clause_text', 'N/A')}\n\n"
            f"**Suggested revision:**\n> {issue.get('suggested_revision', 'N/A')}\n\n"
        )

        if issue.get("reasoning"):
            content += f"**Reasoning:** {issue['reasoning']}\n\n"

        alts = issue.get("alternatives", [])
        if alts:
            alt_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(alts))
            content += f"**Alternatives:**\n{alt_text}\n\n"

        content += (
            "**Actions:** `approve` · `reject` · `modify: <your text>` "
        )
        if alts:
            content += "· `alt 1`, `alt 2`, etc."

        options = ["Approve", "Reject"]
        if alts:
            options.extend([f"Alt {i+1}" for i in range(len(alts))])

        return SkillResponse(
            type="revision_approval",
            content=content,
            confidence=conf,
            options=options,
            stage="qa_session",
            metadata={"revision_index": num - 1},
        )

    def _parse_issues(self, response: str) -> list[dict]:
        """Parse Claude's review response into structured issues."""
        # Try to extract JSON array from response
        try:
            # Look for JSON array in the response
            start = response.find("[")
            end = response.rfind("]") + 1
            if start >= 0 and end > start:
                issues = json.loads(response[start:end])
                if isinstance(issues, list):
                    return [self._normalize_issue(i) for i in issues]
        except json.JSONDecodeError:
            pass

        # Fallback: try to parse as single JSON object
        try:
            obj = json.loads(response)
            if isinstance(obj, dict):
                return [self._normalize_issue(obj)]
        except json.JSONDecodeError:
            pass

        # Last resort: return the raw response as a single issue
        return [{
            "section": "General",
            "clause_text": "",
            "issue": response[:500],
            "confidence": 3,
            "suggested_revision": "",
            "alternatives": [],
            "reasoning": "",
        }]

    def _normalize_issue(self, issue: dict) -> dict:
        return {
            "section": issue.get("section", "General"),
            "clause_text": issue.get("clause_text", ""),
            "issue": issue.get("issue", ""),
            "confidence": min(max(int(issue.get("confidence", 2)), 1), 4),
            "suggested_revision": issue.get("suggested_revision", ""),
            "alternatives": issue.get("alternatives", []),
            "reasoning": issue.get("reasoning", ""),
        }

    def _generate_playbook(self, session: SkillSession) -> dict:
        """Generate a reusable playbook from the review session."""
        rules = []
        for rev in session.approved_revisions:
            rules.append({
                "section": rev.get("section", ""),
                "issue": rev.get("issue", ""),
                "position": rev.get("suggested_revision", ""),
                "fallback": rev.get("alternatives", [""])[0] if rev.get("alternatives") else "",
                "priority": "high" if rev.get("confidence", 2) >= 3 else "medium" if rev.get("confidence", 2) == 2 else "low",
                "confidence_pattern": rev.get("confidence", 2),
            })

        party = session.context.get("party", "Unknown")
        filename = session.context.get("original_filename", "contract")

        return {
            "name": f"Review of {filename} as {party}",
            "created_from": f"session_{session.id}",
            "date": datetime.now().isoformat(),
            "party_role": party,
            "rules": rules,
        }

    def _save_playbook(self, session: SkillSession, playbook: dict) -> str:
        PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(PLAYBOOKS_DIR / f"playbook_{session.id[:8]}.json")
        with open(path, "w") as f:
            json.dump(playbook, f, indent=2)
        return path

    def _save_transcript(self, session: SkillSession) -> str:
        out_dir = UPLOADS_DIR / session.id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = str(out_dir / "transcript.json")
        with open(path, "w") as f:
            json.dump(
                [entry.model_dump() for entry in session.transcript],
                f,
                indent=2,
            )
        return path


# Register the skill
_skill = ContractReviewSkill()
register_skill(_skill)
