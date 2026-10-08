"""The assistant's turn: the model picks tools, the tools read the desk, the model answers.

run_turn yields plain dict events that the route sends as server-sent events:

  step       a tool call started (id, tool, label, args)
  step_done  it finished (id, ok, summary)
  block      a table or card for the browser
  token      a piece of the answer
  reset      throw away the text streamed so far; the model went on to call tools
  final      the full answer after checks, which replaces the streamed text
  done       usage, elapsed time, model, tools used
  error      a message the recruiter can act on

When the model is unreachable the turn falls back to the rule parser, the same
one the Find page uses, so the recruiter still gets rows.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime
import json
import logging
import re
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.assistant.tools import TOOL_BY_NAME, TOOLS, ToolContext, ToolError, ToolResult, run_tool
from app.admin.find import rule_filters
from app.config import get_settings
from app.core.llm import LLMError
from app.models import AuditLog, Candidate, Job, Submission

logger = logging.getLogger(__name__)

HISTORY_TURNS = 12
MESSAGE_CHARS = 4000
TOOL_RESULT_CHARS = 7000
GROUNDING_TURNS = 3
_CODE = re.compile(r"\b[A-Z][0-9]{3,5}\b")
TOOL_NAMES = set(TOOL_BY_NAME)

SYSTEM = """You are the recruiting desk assistant for {company}. You help one recruiter, signed in to the admin site.
Today is {today} ({weekday}). The recruiter's timezone is {tz}.
{page}
How to work:
- Any question about jobs, candidates, submissions, counts, salaries, or dates needs a tool call first. Never answer those from memory.
- Call several tools at once when the question has several parts.
- Put only what the recruiter said into filters. Do not add related skills, nearby states, or roles they did not name.
- "This job", "this candidate", and "this submission" mean the ones on the page described above.
- For relative dates such as "this week" or "last month", work out the YYYY-MM-DD range from today's date.
- If a name matches more than one person, ask which one.
- You can only read. If the recruiter asks you to change something, call reply_directly and say which page does it (Pipeline board, job page, candidate page).
- For questions that have nothing to do with the desk, call reply_directly.

How to answer:
- The full results appear as a table or card under your answer. Do not repeat the table. Give the total, then the few rows or facts that answer the question.
- Name at most five people or jobs. Use requisition codes exactly as the tools return them.
- Every number, name, and code must come from tool results in this conversation. If a tool found nothing, say so and suggest a broader search.
- If the tool reports ignored_filters, tell the recruiter those words were not used.
- Be brief: at most 80 words. Plain markdown only: **bold**, bullets. No tables, no headings.
"""


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def describe_page(session: Session, page: dict | None) -> tuple[str, set[str]]:
    """Turn the browser's page context into a sentence for the model, checked against the database."""
    page = page or {}
    lines: list[str] = []
    codes: set[str] = set()
    label = str(page.get("label") or page.get("path") or "").strip()[:80]
    if label:
        lines.append(f"The recruiter is on the {label} page.")
    code = str(page.get("code") or "").strip().upper()
    if code:
        job = session.scalar(select(Job).where(Job.requisition_code == code))
        if job is not None:
            codes.add(job.requisition_code)
            lines.append(f"On screen: job {job.requisition_code}, {job.title}, {job.location or 'location not listed'}, status {job.status}.")
    candidate_id = _uuid(page.get("candidate_id"))
    if candidate_id:
        candidate = session.get(Candidate, candidate_id)
        if candidate is not None:
            name = candidate.full_name or candidate.original_filename or "this candidate"
            lines.append(f"On screen: candidate {name} (candidate_id {candidate.id}).")
    submission_id = _uuid(page.get("submission_id"))
    if submission_id:
        row = session.get(Submission, submission_id)
        if row is not None and row.candidate is not None and row.job is not None:
            codes.add(row.job.requisition_code)
            lines.append(
                f"On screen: submission {row.id} of {row.candidate.full_name or row.candidate.original_filename} "
                f"for {row.job.requisition_code} {row.job.title}, stage {row.stage}."
            )
    view = str(page.get("view") or "").strip()[:300]
    if view:
        lines.append(f"Page filters: {view}")
    return ("\n".join(lines) + "\n") if lines else "", codes


def clean_history(messages: list[dict]) -> list[dict]:
    """Keep recent user and assistant turns. An assistant turn carries a note of the tool calls behind it.

    The note lets a follow-up such as "only the ones in Maryland" repeat the earlier call with
    one more filter, instead of the model answering from the old reply's text.
    """
    out: list[dict] = []
    for turn, message in enumerate(messages[-HISTORY_TURNS:]):
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        if not out and role != "user":
            continue
        steps = message.get("tools") if role == "assistant" else None
        calls = []
        for index, step in enumerate(steps[:6] if isinstance(steps, list) else []):
            if isinstance(step, dict) and step.get("tool") in TOOL_NAMES and isinstance(step.get("args") or {}, dict):
                memo = step.get("memo") if isinstance(step.get("memo"), dict) else {}
                if len(json.dumps(memo, default=str)) > 1500:
                    memo = {"total": memo.get("total"), "note": "earlier rows too long to keep"}
                calls.append(
                    {
                        "id": f"h{turn}_{index}",
                        "name": step["tool"],
                        "arguments": step.get("args") or {},
                        "summary": str(step.get("summary") or "")[:160],
                        "memo": memo,
                    }
                )
        if calls:
            out.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{key: call[key] for key in ("id", "name", "arguments")} for call in calls],
                }
            )
            for call in calls:
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": json.dumps(
                            {
                                "earlier_result": call["summary"],
                                "top_rows": call["memo"],
                                "note": "Only the top rows were kept. Call again for anything else.",
                            },
                            default=str,
                        ),
                    }
                )
        out.append({"role": role, "content": content.strip()[:MESSAGE_CHARS]})
    return out


_SMALL_TALK = re.compile(
    r"(?i)^\s*(hi|hello|hey|thanks?|thank you|thx|ok(ay)?|cool|great|good (morning|afternoon|evening)|"
    r"what can you do|help|who are you|how do i use (this|you))[\s!.?]*$"
)

REPLY_TOOL = {
    "name": "reply_directly",
    "description": "Answer without desk data. Only for: a question outside jobs, candidates, submissions, and reports; "
    "a request to change records (say which page does it); or a clarifying question. Never put names, numbers, "
    "or job codes in the message.",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "enum": ["out_of_scope", "change_request", "clarify"]},
            "message": {"type": "string"},
        },
        "required": ["reason", "message"],
    },
}
_DATA_LIKE = re.compile(r"\d|\b[A-Z][0-9]{3,5}\b")

NUDGE = (
    "Answer my last question by calling the right tool first. Do not answer from memory or from earlier replies; "
    "names, counts, and codes must come from a tool result."
)


def keep_known_codes(text: str, allowed: set[str]) -> str:
    """Drop requisition codes that are not on file. Unlike the public helper this keeps line breaks."""

    def replace(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0) in allowed else "(unknown code)"

    return _CODE.sub(replace, text or "")


_MEMO_KEYS = ("id", "candidate_id", "name", "candidate", "code", "title", "mandatory_pct", "stage")
MEMO_ROWS = 8


def memo_of(data: dict) -> dict:
    """The few ids, names, and codes in a result, kept so a later turn can say "the first one"."""
    memo: dict = {}
    for key in ("candidates", "jobs", "submissions"):
        rows = data.get(key)
        if isinstance(rows, list) and rows:
            memo[key] = [
                {field: row[field] for field in _MEMO_KEYS if isinstance(row, dict) and row.get(field) is not None}
                for row in rows[:MEMO_ROWS]
            ]
    for field in _MEMO_KEYS:
        value = data.get(field)
        if isinstance(value, (str, int, float)) and value != "":
            memo[field] = value
    if isinstance(data.get("total"), int):
        memo["total"] = data["total"]
    return memo


def _tool_message(result: ToolResult) -> str:
    data = result.data
    total = data.get("total", data.get("total_ranked"))
    for key in ("candidates", "jobs", "submissions"):
        rows = data.get(key)
        if isinstance(total, int) and isinstance(rows, list) and len(rows) < total:
            # Small models count the rows they see. Say plainly that the total is larger.
            data = {"count_note": f"The total is {total}. Only the first {len(rows)} {key} are listed here.", **data}
            break
    text = json.dumps(data, default=str, ensure_ascii=False)
    if len(text) > TOOL_RESULT_CHARS:
        text = text[:TOOL_RESULT_CHARS] + ' …(truncated; the recruiter sees the full table)"}'
    return text


def _fallback(ctx: ToolContext, question: str, page_codes: set[str], reason: str = "model_down") -> Iterator[dict]:
    """No usable model turn: read the question with the Find page's rule parser and show rows."""
    lead = (
        "The language model is not reachable right now"
        if reason == "model_down"
        else "The model did not look this up, so I did not trust its answer"
    )
    ctx = replace(ctx, grounding=question)
    codes = set(_CODE.findall(question.upper())) | ({next(iter(page_codes))} if page_codes and "this job" in question.lower() else set())
    calls: list[tuple[str, dict]] = []
    if codes:
        code = sorted(codes)[0]
        calls.append(("job_details", {"code": code}))
        if re.search(r"(?i)\b(fit|match|candidate|who|people|best)", question):
            calls.append(("job_candidates", {"code": code}))
    else:
        filters = rule_filters(question)
        if not filters.empty():
            calls.append(
                (
                    "find_candidates",
                    {"skills": filters.skills, "states": filters.states, "roles": filters.categories},
                )
            )
        if re.search(r"(?i)\b(jobs?|roles?|positions?|openings?|requisitions?)\b", question):
            calls.append(("find_jobs", {"query": question}))
    if not calls:
        text = (
            f"{lead}, and no skill, state, or job code was found in that question to search directly. "
            "Try rephrasing, or name a skill, state, or code such as A1001."
            if reason == "model_down"
            else "I can only look up this desk's data: candidates, jobs, fit, the pipeline, and reports. "
            "Try something like \"Java developers in Virginia\" or \"Who fits A1001?\"."
        )
        yield {"type": "final", "text": text}
        return
    found: list[str] = []
    for name, args in calls:
        step = uuid.uuid4().hex[:8]
        tool = next(t for t in TOOLS if t.name == name)
        yield {"type": "step", "id": step, "tool": name, "label": tool.label, "args": args}
        try:
            result = run_tool(ctx, name, args)
        except ToolError as exc:
            yield {"type": "step_done", "id": step, "ok": False, "summary": str(exc)}
            continue
        yield {"type": "step_done", "id": step, "ok": True, "summary": result.summary}
        if result.block:
            yield {"type": "block", "block": result.block}
        found.append(result.summary)
    text = f"{lead}, so this is a direct search of your words"
    yield {"type": "final", "text": text + (": " + "; ".join(found) + "." if found else ".")}


def run_turn(
    *,
    session: Session,
    llm,
    embedder,
    messages: list[dict],
    page: dict | None,
    timezone_name: str | None,
    max_steps: int = 5,
    model_name: str = "",
) -> Iterator[dict]:
    started = time.monotonic()
    history = clean_history(messages)
    if not history or history[-1]["role"] != "user":
        yield {"type": "error", "message": "Type a question first."}
        return
    zone = _zone(timezone_name)
    today = datetime.now(zone).date()
    users = [m["content"] for m in history if m["role"] == "user"][-GROUNDING_TURNS:]
    ctx = ToolContext(session=session, llm=llm, embedder=embedder, grounding="\n".join(users), zone=zone, today=today)
    page_text, page_codes = describe_page(session, page)
    allowed = set(session.scalars(select(Job.requisition_code)).all())
    system = SYSTEM.format(
        company=get_settings().company_name,
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        tz=zone.key,
        page=page_text,
    )
    convo: list[dict] = [{"role": "system", "content": system}, *history]
    specs = [tool.spec() for tool in TOOLS] + [REPLY_TOOL]
    used: list[str] = []
    cache: dict[str, ToolResult] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    answer = ""

    question = history[-1]["content"]
    needs_data = not _SMALL_TALK.match(question)
    nudged = False
    tools_ran = False
    max_steps = max(2, max_steps)

    for step in range(max_steps):
        last = step == max_steps - 1
        # Until a tool has run, a data question's text is held back: it would be a guess.
        hold = needs_data and not tools_ran
        text_parts: list[str] = []
        calls = []
        try:
            for event in llm.stream_chat(
                convo,
                [] if last else specs,
                temperature=0.1,
                max_tokens=700,
                require_tool=hold and not last,
            ):
                if event.kind == "text":
                    text_parts.append(event.text)
                    if not hold:
                        yield {"type": "token", "text": event.text}
                elif event.kind == "tool_call" and event.call is not None:
                    calls.append(event.call)
                elif event.kind == "done":
                    for key in usage:
                        usage[key] += int(event.usage.get(key) or 0)
        except LLMError as exc:
            logger.warning("assistant model call failed: %s", exc)
            if not tools_ran:
                yield from _fallback(ctx, question, page_codes)
                used.append("fallback")
                answer = ""
                break
            yield {"type": "error", "message": "The language model stopped answering. The results above are still valid."}
            break
        if not calls and hold:
            if not nudged and not last:
                nudged = True
                convo.append({"role": "user", "content": NUDGE})
                continue
            yield from _fallback(ctx, question, page_codes, reason="model_skipped_tools")
            used.append("fallback")
            answer = ""
            break
        if not calls:
            answer = "".join(text_parts).strip()
            break
        direct = [c for c in calls if c.name == REPLY_TOOL["name"]]
        if direct and len(direct) == len(calls):
            message = str(direct[0].arguments.get("message") or "").strip()
            # After real lookups the reply may cite their numbers; before any, only the recruiter's own.
            echoed = message
            for token in re.findall(r"\b[A-Z]?[0-9][0-9,.$k]*\b", question):
                echoed = echoed.replace(token, "")
            if message and (tools_ran or not _DATA_LIKE.search(echoed)):
                answer = message
                used.append(REPLY_TOOL["name"])
                break
            # A direct reply with numbers or codes in it is a guess at data.
            if not nudged and not last:
                nudged = True
                convo.append({"role": "user", "content": NUDGE})
                continue
            yield from _fallback(ctx, question, page_codes, reason="model_skipped_tools")
            used.append("fallback")
            answer = ""
            break
        calls = [c for c in calls if c.name != REPLY_TOOL["name"]] or calls
        tools_ran = True
        if text_parts and not hold:
            yield {"type": "reset"}
        convo.append(
            {
                "role": "assistant",
                "content": "".join(text_parts),
                "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
            }
        )
        for call in calls:
            tool = next((t for t in TOOLS if t.name == call.name), None)
            label = tool.label if tool else call.name
            yield {"type": "step", "id": call.id, "tool": call.name, "label": label, "args": call.arguments}
            key = call.name + json.dumps(call.arguments, sort_keys=True, default=str)
            try:
                if key in cache:
                    result = cache[key]
                    content = json.dumps({"note": "Same call as before; results unchanged.", **result.data}, default=str)[:TOOL_RESULT_CHARS]
                else:
                    result = run_tool(ctx, call.name, call.arguments)
                    cache[key] = result
                    content = _tool_message(result)
                    if result.block:
                        yield {"type": "block", "block": result.block}
                used.append(call.name)
                yield {"type": "step_done", "id": call.id, "ok": True, "summary": result.summary, "memo": memo_of(result.data)}
            except ToolError as exc:
                content = json.dumps({"error": str(exc)})
                yield {"type": "step_done", "id": call.id, "ok": False, "summary": str(exc)}
            except Exception:
                logger.exception("assistant tool %s failed", call.name)
                session.rollback()
                content = json.dumps({"error": "That lookup failed on the server."})
                yield {"type": "step_done", "id": call.id, "ok": False, "summary": "Lookup failed"}
            convo.append({"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content})

    if answer:
        yield {"type": "final", "text": keep_known_codes(answer, allowed)}
    elif "fallback" not in used:
        yield {"type": "final", "text": "I could not finish that answer. Try asking in fewer parts."}

    try:
        session.add(AuditLog(actor="admin", action="assistant", outcome=(",".join(used) or "answer")[:200]))
        session.commit()
    except Exception:
        session.rollback()
    yield {
        "type": "done",
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "usage": usage,
        "tools": used,
        "model": model_name,
    }
