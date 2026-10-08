"""Recruiter assistant: tools, the tool loop, grounding, fallbacks, streaming, and both LLM wire formats."""

from contextlib import contextmanager
import json

from fastapi.testclient import TestClient

from app.admin.assistant.engine import clean_history, keep_known_codes, memo_of, run_turn
from app.admin.assistant.tools import TOOLS, ToolContext, find_candidates
from app.core.llm import BedrockClient, ChatEvent, OpenAICompatClient, _ThinkFilter, bedrock_messages
from app.main import create_app
from app.models import AuditLog, Candidate, Job, Submission
from tests.fakes import RecordingEmbedder, ScriptedChatLLM, call, say


def _seed(db):
    a1001 = Job(
        requisition_code="A1001",
        title="UI/UX Developer",
        location="Chantilly, VA",
        status="open",
        description_text="Build interfaces in JavaScript.",
        description_source="careers_page",
        must_have_skills=["JavaScript"],
        nice_to_have_skills=[],
        source_url="https://janus-soft.com/jobs/1001",
        clearance_required="TS/SCI",
    )
    b2002 = Job(
        requisition_code="B2002",
        title="Java Developer",
        location="Columbia, MD",
        status="open",
        description_text="Java and AWS services.",
        description_source="careers_page",
        must_have_skills=["Java", "AWS"],
        nice_to_have_skills=[],
    )
    alex = Candidate(
        file_sha256="alex-assistant",
        full_name="Alex Rivera",
        email="alex@example.com",
        location="Baltimore, MD",
        clearance="secret",
        status="confirmed",
        skills=[{"name": "Java"}, {"name": "AWS"}],
        titles=["Software Developer"],
        redacted_text="Alex Rivera\nSoftware Developer\nJava, AWS, Spring Boot.",
    )
    sam = Candidate(
        file_sha256="sam-assistant",
        full_name="Sam Roe",
        email="sam@example.com",
        location="Reston, VA",
        status="confirmed",
        skills=[{"name": "Java"}],
        titles=["Developer"],
        redacted_text="Sam Roe\nDeveloper\nJava services.",
    )
    pat = Candidate(
        file_sha256="pat-assistant",
        full_name="Pat Lee",
        email="pat@example.com",
        location="Rockville, MD",
        status="confirmed",
        skills=[{"name": "Python"}],
        titles=["Data Analyst"],
        redacted_text="Pat Lee\nData Analyst\nPython.",
    )
    db.add_all([a1001, b2002, alex, sam, pat])
    db.flush()
    db.add(Submission(candidate_id=alex.id, job_id=a1001.id, stage="interviewed", salary_usd=165000))
    db.commit()
    return {"alex": alex, "sam": sam, "pat": pat}


def _turn(db, llm, question, page=None, history=None):
    messages = list(history or []) + [{"role": "user", "content": question}]
    return list(
        run_turn(
            session=db,
            llm=llm,
            embedder=None,
            messages=messages,
            page=page,
            timezone_name="America/New_York",
            max_steps=5,
        )
    )


def _kinds(events):
    return [event["type"] for event in events]


def _final(events) -> str:
    return next(event["text"] for event in events if event["type"] == "final")


def test_tool_call_runs_on_the_desk_and_the_answer_streams(db):
    _seed(db)
    llm = ScriptedChatLLM(
        [
            call("find_candidates", {"skills": ["Java"], "states": ["MD"]}),
            say("One Java developer lives in Maryland: **Alex Rivera**."),
        ]
    )
    events = _turn(db, llm, "Java developers in Maryland")
    kinds = _kinds(events)
    assert kinds.index("step") < kinds.index("block") < kinds.index("token") < kinds.index("final") < kinds.index("done")
    block = next(event["block"] for event in events if event["type"] == "block")
    assert block["type"] == "candidates"
    assert [row["name"] for row in block["rows"]] == ["Alex Rivera"]
    assert _final(events) == "One Java developer lives in Maryland: **Alex Rivera**."
    tool_message = next(m for m in llm.chats[1]["messages"] if m["role"] == "tool")
    assert "Alex Rivera" in tool_message["content"]
    assert "Sam Roe" not in tool_message["content"]
    done = events[-1]
    assert done["tools"] == ["find_candidates"]
    assert done["usage"]["prompt_tokens"] == 20
    assert db.query(AuditLog).filter(AuditLog.action == "assistant").count() == 1


def test_untooled_answer_to_a_data_question_is_held_back_and_retried(db):
    _seed(db)
    llm = ScriptedChatLLM(
        [
            say("There are 3 Java developers: John Smith, Jane Doe, and Bob."),
            call("find_candidates", {"skills": ["Java"], "states": ["MD"]}),
            say("Alex Rivera is the only one."),
        ]
    )
    events = _turn(db, llm, "Java developers in Maryland")
    streamed = "".join(event["text"] for event in events if event["type"] == "token")
    assert "John Smith" not in streamed
    assert llm.chats[0]["require_tool"] is True
    assert llm.chats[1]["messages"][-1]["role"] == "user"
    assert "calling the right tool" in llm.chats[1]["messages"][-1]["content"]
    assert _final(events) == "Alex Rivera is the only one."


def test_model_that_never_calls_a_tool_gets_a_direct_search_instead(db):
    _seed(db)
    llm = ScriptedChatLLM([say("John Smith."), say("Still John Smith.")])
    events = _turn(db, llm, "Java developers in Maryland")
    assert "John Smith" not in json.dumps(events)
    block = next(event["block"] for event in events if event["type"] == "block")
    assert [row["name"] for row in block["rows"]] == ["Alex Rivera"]
    assert "did not look this up" in _final(events)
    assert events[-1]["tools"] == ["fallback"]


def test_model_down_falls_back_to_the_rule_parser(db):
    _seed(db)
    llm = ScriptedChatLLM([None])
    events = _turn(db, llm, "Java developers in Maryland")
    block = next(event["block"] for event in events if event["type"] == "block")
    assert [row["name"] for row in block["rows"]] == ["Alex Rivera"]
    assert "not reachable" in _final(events)


def test_model_down_with_a_job_code_shows_the_job_and_its_fits(db):
    _seed(db)
    events = _turn(db, ScriptedChatLLM([None]), "who fits B2002?")
    blocks = [event["block"]["type"] for event in events if event["type"] == "block"]
    assert blocks == ["job", "ranked"]


def test_small_talk_streams_without_forcing_a_tool(db):
    llm = ScriptedChatLLM([say("Hello. Ask me about jobs, candidates, or the pipeline.")])
    events = _turn(db, llm, "hello")
    assert "token" in _kinds(events)
    assert llm.chats[0]["require_tool"] is False
    assert _final(events).startswith("Hello.")


def test_off_topic_and_change_requests_get_a_direct_reply(db):
    _seed(db)
    llm = ScriptedChatLLM(
        [call("reply_directly", {"reason": "change_request", "message": "I can only read. Close A1001 from its job page."})]
    )
    events = _turn(db, llm, "close job A1001 please")
    assert _final(events) == "I can only read. Close A1001 from its job page."
    assert "reply_directly" in llm.chats[0]["tools"]
    assert events[-1]["tools"] == ["reply_directly"]


def test_a_direct_reply_with_data_in_it_is_not_trusted(db):
    _seed(db)
    llm = ScriptedChatLLM(
        [
            call("reply_directly", {"reason": "clarify", "message": "There are 4 Java developers."}),
            call("reply_directly", {"reason": "clarify", "message": "Still 4."}),
        ]
    )
    events = _turn(db, llm, "Java developers in Maryland")
    assert "4 Java" not in json.dumps(events)
    assert events[-1]["tools"] == ["fallback"]


def test_filters_the_recruiter_did_not_say_are_dropped(db):
    _seed(db)
    ctx = ToolContext(session=db, grounding="Java developers in Maryland")
    result = find_candidates(ctx, {"skills": ["Java", "Kubernetes"], "states": ["MD", "VA"], "clearance": "ts_sci"})
    assert [row["name"] for row in result.data["candidates"]] == ["Alex Rivera"]
    assert set(result.data["ignored_filters"]) == {"Kubernetes", "VA", "clearance ts_sci"}


def test_earlier_messages_ground_a_follow_up_but_do_not_add_filters(db):
    _seed(db)
    ctx = ToolContext(session=db, grounding="Java developers in Maryland\nonly the ones with a secret clearance")
    narrowed = find_candidates(ctx, {"skills": ["Java"], "states": ["MD"], "clearance": "secret"})
    assert [row["name"] for row in narrowed.data["candidates"]] == ["Alex Rivera"]
    assert narrowed.data["filters_applied"]["clearance"] == ["at least Secret"]
    broad = find_candidates(ctx, {"skills": ["Java"]})
    assert sorted(row["name"] for row in broad.data["candidates"]) == ["Alex Rivera", "Sam Roe"]


def test_a_role_phrase_still_filters_on_its_skill(db):
    _seed(db)
    ctx = ToolContext(session=db, grounding="Java developers in Virginia")
    result = find_candidates(ctx, {"roles": ["Java developer"], "states": ["VA"]})
    assert [row["name"] for row in result.data["candidates"]] == ["Sam Roe"]
    assert result.data["ignored_filters"] == []


def test_page_context_names_the_job_on_screen(db):
    _seed(db)
    llm = ScriptedChatLLM([call("job_candidates", {"code": "B2002"}), say("Alex Rivera fits B2002 best.")])
    events = _turn(db, llm, "who fits this job?", page={"label": "Job B2002", "code": "B2002"})
    system = llm.chats[0]["messages"][0]["content"]
    assert "job B2002, Java Developer" in system
    block = next(event["block"] for event in events if event["type"] == "block")
    assert block["type"] == "ranked" and block["rows"][0]["name"] == "Alex Rivera"


def test_unknown_codes_in_the_answer_are_removed(db):
    _seed(db)
    llm = ScriptedChatLLM([call("find_jobs", {"query": "Java"}), say("B2002 and Z9999 need Java.")])
    events = _turn(db, llm, "which jobs need Java?")
    assert _final(events) == "B2002 and (unknown code) need Java."
    assert keep_known_codes("A1001\nZ1\nQ1234", {"A1001"}) == "A1001\nZ1\n(unknown code)"


def test_tool_errors_go_back_to_the_model(db):
    _seed(db)
    llm = ScriptedChatLLM([call("job_details", {"code": "Q4040"}), say("Q4040 is not on file.")])
    events = _turn(db, llm, "show me Q4040")
    done = next(event for event in events if event["type"] == "step_done")
    assert done["ok"] is False and "No job with code Q4040" in done["summary"]
    tool_message = next(m for m in llm.chats[1]["messages"] if m["role"] == "tool")
    assert "No job with code Q4040" in tool_message["content"]


def test_every_tool_runs_against_the_desk(db):
    people = _seed(db)
    ctx = ToolContext(session=db, grounding="Java in Maryland with secret clearance")
    args = {
        "find_candidates": {"skills": ["Java"]},
        "candidate_profile": {"candidate_name": "Alex Rivera"},
        "find_jobs": {},
        "job_details": {"code": "A1001"},
        "job_candidates": {"code": "B2002"},
        "check_fit": {"code": "B2002", "candidate_id": str(people["alex"].id)},
        "pipeline": {},
        "submission_details": {"submission_id": str(db.query(Submission).one().id)},
        "desk_stats": {},
        "report": {"start_date": "2020-01-01", "end_date": "2020-12-31", "salary_above": 100000},
    }
    assert set(args) == {tool.name for tool in TOOLS}
    for tool in TOOLS:
        result = tool.handler(ctx, args[tool.name])
        assert result.summary, tool.name
        json.dumps(result.data, default=str)
    profile = TOOLS[1].handler(ctx, args["candidate_profile"])
    assert profile.data["submissions"][0]["code"] == "A1001"
    fit = TOOLS[5].handler(ctx, args["check_fit"])
    assert fit.data["meets_bar"] is True


def test_history_replays_earlier_tool_calls_with_their_top_rows():
    memo = memo_of({"total": 2, "candidates": [{"id": "c1", "name": "Alex", "email": "a@x"}, {"id": "c2", "name": "Sam"}]})
    assert memo == {"candidates": [{"id": "c1", "name": "Alex"}, {"id": "c2", "name": "Sam"}], "total": 2}
    history = clean_history(
        [
            {"role": "assistant", "content": "Hi, how can I help?"},
            {"role": "user", "content": "Java in MD"},
            {
                "role": "assistant",
                "content": "Two people.",
                "tools": [{"tool": "find_candidates", "args": {"skills": ["Java"]}, "summary": "2 candidates", "memo": memo}],
            },
            {"role": "user", "content": "the first one's profile"},
        ]
    )
    assert [m["role"] for m in history] == ["user", "assistant", "tool", "assistant", "user"]
    assert history[1]["tool_calls"][0]["name"] == "find_candidates"
    assert '"c1"' in history[2]["content"]


def test_quick_search_and_streaming_route(db):
    _seed(db)
    app = create_app()
    client = TestClient(app)
    client.__enter__()
    app.state.embedder = RecordingEmbedder()
    app.state.llm = ScriptedChatLLM([call("pipeline", {}), say("One active submission: Alex Rivera for A1001.")])
    body = {"messages": [{"role": "user", "content": "what is in the pipeline?"}], "page": {"label": "Pipeline"}}
    assert client.post("/admin/assistant", json=body).status_code == 401
    assert client.get("/admin/search", params={"q": "alex"}).status_code == 401
    assert client.post("/admin/login", json={"password": "correct-horse"}).status_code == 200

    found = client.get("/admin/search", params={"q": "java md"}).json()
    assert [job["code"] for job in found["jobs"]] == ["B2002"]
    assert [person["name"] for person in found["candidates"]] == ["Alex Rivera"]
    by_code = client.get("/admin/search", params={"q": "A1001"}).json()
    assert by_code["submissions"][0]["candidate"] == "Alex Rivera"

    with client.stream("POST", "/admin/assistant", json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert "no-transform" in response.headers["cache-control"]
        events = [json.loads(line[5:]) for line in response.iter_lines() if line.startswith("data:")]
    assert _kinds(events)[0] == "step"
    assert _final(events) == "One active submission: Alex Rivera for A1001."
    assert client.get("/admin/assistant/info").json()["model"]
    client.__exit__(None, None, None)


class _FakeStream:
    def __init__(self, lines):
        self.lines = lines
        self.status_code = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        yield from self.lines


@contextmanager
def _patched_stream(monkeypatch, lines, seen):
    def fake_stream(method, url, json=None, headers=None, timeout=None):
        seen.append(json)
        return _FakeStream(lines)

    monkeypatch.setattr("app.core.llm.httpx.stream", fake_stream)
    yield


def test_openai_compat_stream_assembles_text_and_split_tool_calls(monkeypatch):
    chunks = [
        {"choices": [{"delta": {"content": "<think>plan</think>Look"}}]},
        {"choices": [{"delta": {"content": "ing."}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "find_jobs", "arguments": '{"que'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'ry": "Java"}'}}]}}]},
        {"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}},
    ]
    lines = [f"data: {json.dumps(chunk)}" for chunk in chunks] + ["", "data: [DONE]"]
    seen: list = []
    with _patched_stream(monkeypatch, lines, seen):
        client = OpenAICompatClient("http://llm/v1", "qwen", reasoning_effort="none")
        tools = [{"name": "find_jobs", "description": "d", "parameters": {"type": "object", "properties": {}}}]
        events = list(client.stream_chat([{"role": "user", "content": "hi"}], tools, require_tool=True))
    assert "".join(e.text for e in events if e.kind == "text") == "Looking."
    calls = [e.call for e in events if e.kind == "tool_call"]
    assert calls[0].name == "find_jobs" and calls[0].arguments == {"query": "Java"}
    assert events[-1].usage["prompt_tokens"] == 7
    assert seen[0]["reasoning_effort"] == "none"
    assert seen[0]["tool_choice"] == "required"
    assert seen[0]["tools"][0]["function"]["name"] == "find_jobs"


def test_reasoning_effort_can_be_turned_off_for_servers_that_reject_it(monkeypatch):
    seen: list = []
    with _patched_stream(monkeypatch, ["data: [DONE]"], seen):
        list(OpenAICompatClient("http://llm/v1", "m", reasoning_effort="").stream_chat([{"role": "user", "content": "x"}], []))
    assert "reasoning_effort" not in seen[0]
    assert "tools" not in seen[0]


def test_think_filter_handles_tags_split_across_pieces():
    think = _ThinkFilter()
    text = "".join(think.feed(piece) for piece in ["a<thi", "nk>hidden</th", "ink>b <", "x"]) + think.flush()
    assert text == "ab <x"


def test_bedrock_messages_map_tools_and_alternate_roles():
    messages = [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Java jobs?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "name": "find_jobs", "arguments": {"query": "Java"}}]},
        {"role": "tool", "tool_call_id": "t1", "name": "find_jobs", "content": '{"total": 1}'},
    ]
    system, converse = bedrock_messages(messages)
    assert system == "Be brief."
    assert [m["role"] for m in converse] == ["user", "assistant", "user"]
    assert converse[1]["content"][0]["toolUse"] == {"toolUseId": "t1", "name": "find_jobs", "input": {"query": "Java"}}
    assert converse[2]["content"][0]["toolResult"]["toolUseId"] == "t1"
    _system, flat = bedrock_messages(messages, flatten_tools=True)
    assert "toolUse" not in json.dumps(flat) and "toolResult" not in json.dumps(flat)


class _FakeBedrock:
    def __init__(self):
        self.calls = []

    def converse_stream(self, **payload):
        self.calls.append(payload)
        return {
            "stream": [
                {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Checking."}}},
                {"contentBlockStart": {"contentBlockIndex": 1, "start": {"toolUse": {"toolUseId": "tu1", "name": "find_jobs"}}}},
                {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": '{"query":'}}}},
                {"contentBlockDelta": {"contentBlockIndex": 1, "delta": {"toolUse": {"input": ' "AWS"}'}}}},
                {"contentBlockStop": {"contentBlockIndex": 1}},
                {"messageStop": {"stopReason": "tool_use"}},
                {"metadata": {"usage": {"inputTokens": 11, "outputTokens": 4, "totalTokens": 15}}},
            ]
        }


def test_bedrock_stream_yields_the_same_events():
    fake = _FakeBedrock()
    client = BedrockClient("amazon.nova-pro-v1:0", client=fake)
    tools = [{"name": "find_jobs", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    events = list(client.stream_chat([{"role": "system", "content": "s"}, {"role": "user", "content": "AWS jobs"}], tools, require_tool=True))
    assert [e.kind for e in events] == ["text", "tool_call", "done"]
    assert events[1].call.arguments == {"query": "AWS"}
    assert events[2].usage == {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}
    payload = fake.calls[0]
    assert payload["toolConfig"]["toolChoice"] == {"any": {}}
    assert payload["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"] == {"type": "object", "properties": {}}
    assert payload["system"] == [{"text": "s"}]


def test_chat_event_defaults():
    assert ChatEvent("text", text="x").call is None
