"""Jobs for the user, work progress and the attention page: the rules behind board.py's ask, answer, job-state,
progress, note and page steps (plan 0036 in the Taka499/claude repo). Pure functions only: no gh, no files.

- **The data block.** Each job or work issue carries its lines as JSON in an HTML comment at the end of its body,
  under a readable rendering of the same lines. The helper writes it and checks it against the schema on every write
  and every read; a block in a bad shape is reported as malformed, never shown as content (D7).
- **Lines.** Every line the page shows is one line of at most LINE_MAX characters, with no bare internal ID: an ID
  such as E193 must be followed by a plain explanation in parentheses (D19).
- **Answers.** A job closes only on a quote of the user's own typed words, naming the job by number and giving one of
  the answers it declares (D8).
- **The page.** Needs you, the project's own blocks, In progress, and Since you last looked (D3).
Tests: python3 -m unittest discover -s skills/task-board
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

JOB_KINDS = ("decide", "approve", "capture", "run")
WORK = "work"
KINDS = JOB_KINDS + (WORK,)
LINE_MAX = 120
MAX_OPTIONS = 3
JOBS_WARNING = 7  # more open jobs than this: the first line says the coordinator may be passing too much on
SINCE_MAX = 10
BLOCK_START, BLOCK_END = "<!-- task-board:data", "-->"
BLOCK = re.compile(re.escape(BLOCK_START) + r"\n(.*?)\n" + re.escape(BLOCK_END), re.S)
# An internal ID: letters then digits (E193, S54-4, Q3) or a raw record ID with an underscore and a digit
# (p_card-02-ido-3_073). A project may give its own pattern in .task-board.json ("id_pattern").
DEFAULT_ID_PATTERN = r"\b(?:[A-Z]{1,3}\d+(?:-\d+)*|[a-z]+_[A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)\b"
GLOSS = re.compile(r"\s*\([^()]{3,}\)")
ANSWER = re.compile(r"#(\d+)[\s:,]+([A-Za-z]+)\b")
ANSWERS = {"approve": ("approve", "decline"), "capture": ("done",), "run": ("done",)}


class Invalid(Exception):
    """Lines or a block that break the schema or a line rule."""


# ---- lines ----------------------------------------------------------------------------------------------------------

def bare_ids(text: str, pattern: str = DEFAULT_ID_PATTERN) -> list:
    """The internal IDs in `text` that no plain explanation in parentheses follows."""
    return [m.group(0) for m in re.finditer(pattern, text) if not GLOSS.match(text, m.end())]


def check_line(name: str, text, pattern: str = DEFAULT_ID_PATTERN, limit: int = LINE_MAX) -> str:
    """`text` if it is one non-empty line of at most `limit` characters with no bare ID; else Invalid."""
    if not isinstance(text, str) or not text.strip():
        raise Invalid(f"{name} is missing")
    if "\n" in text or "\r" in text:
        raise Invalid(f"{name} must be one line")
    if len(text) > limit:
        raise Invalid(f"{name} is {len(text)} characters, over the limit of {limit}: say it shorter")
    ids = bare_ids(text, pattern)
    if ids:
        raise Invalid(f"{name} uses {', '.join(ids)} with no plain explanation: write it as"
                      f" \"{ids[0]} (what it is, in plain words)\", or say it without the ID")
    return text


# ---- the data block -------------------------------------------------------------------------------------------------

def validate(data, pattern: str = DEFAULT_ID_PATTERN) -> dict:
    """`data` if it is a well-formed block for its kind; else Invalid. Strict: no missing and no unknown fields."""
    if not isinstance(data, dict) or data.get("kind") not in KINDS:
        raise Invalid(f"the block's kind must be one of {', '.join(KINDS)}")
    kind = data["kind"]
    wanted = {"decide": {"kind", "options", "recommend"}, WORK: {"kind", "goal", "step", "of", "now", "next"}}
    fields = wanted.get(kind, {"kind", "summary"})
    if set(data) != fields:
        extra, missing = sorted(set(data) - fields), sorted(fields - set(data))
        raise Invalid(f"a {kind} block takes {', '.join(sorted(fields))}"
                      + (f"; missing {', '.join(missing)}" if missing else "")
                      + (f"; unknown {', '.join(extra)}" if extra else ""))
    if kind == "decide":
        options = data["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= MAX_OPTIONS:
            raise Invalid(f"a decision takes 2 to {MAX_OPTIONS} options")
        keys = []
        for option in options:
            if not isinstance(option, dict) or set(option) != {"key", "text", "cost"}:
                raise Invalid("each option takes key, text and cost")
            if not isinstance(option["key"], str) or not re.fullmatch(r"[A-Z]", option["key"]):
                raise Invalid(f"an option's key must be one capital letter, not {option['key']!r}")
            keys.append(option["key"])
            check_line(f"option {option['key']}'s text", option["text"], pattern)
            check_line(f"option {option['key']}'s cost", option["cost"], pattern)
        if len(set(keys)) != len(keys):
            raise Invalid("two options share a key")
        recommend = data["recommend"]
        if not isinstance(recommend, dict) or set(recommend) != {"key", "why"} or recommend.get("key") not in keys:
            raise Invalid(f"the recommendation takes key (one of {', '.join(keys)}) and why")
        check_line("the recommendation's why", recommend["why"], pattern)
    elif kind == WORK:
        step, of = data["step"], data["of"]
        if not (isinstance(step, int) and isinstance(of, int) and not isinstance(step, bool)
                and not isinstance(of, bool) and 1 <= step <= of):
            raise Invalid("step and of must be whole numbers with 1 <= step <= of")
        for name in ("goal", "now", "next"):
            check_line(name, data[name], pattern)
    else:
        check_line("the summary", data["summary"], pattern)
    return data


def answers(data: dict) -> tuple:
    """The answers a job declares: a decision's option keys; approve or decline; done."""
    if data["kind"] == "decide":
        return tuple(option["key"] for option in data["options"])
    return ANSWERS[data["kind"]]


def render_lines(data: dict) -> list:
    """The readable lines of a block, as the issue body shows them above the block."""
    if data["kind"] == "decide":
        lines = [f"- **{o['key']}:** {o['text']}. Cost: {o['cost']}" for o in data["options"]]
        return lines + [f"- **Recommended: {data['recommend']['key']}.** {data['recommend']['why']}"]
    if data["kind"] == WORK:
        return [f"- **Goal:** {data['goal']}", f"- **Step {data['step']} of {data['of']}:** {data['now']}",
                f"- **Next:** {data['next']}"]
    return [f"- {data['summary']}"]


def block_text(data: dict) -> str:
    # ">" written as >: a "-->" inside a string would otherwise end the HTML comment early.
    return f"{BLOCK_START}\n{json.dumps(data, ensure_ascii=False).replace('>', chr(92) + 'u003e')}\n{BLOCK_END}"


def render_body(data: dict, note: str = "") -> str:
    """A new issue's body: the readable lines, an optional note, and the block."""
    parts = ["\n".join(render_lines(data))]
    if note.strip():
        parts.append(note.strip())
    parts.append("_Written by the task-board helper; change it with `board.py`, not by hand._")
    return "\n\n".join(parts + [block_text(data)]) + "\n"


def read_block(body: str, pattern: str = DEFAULT_ID_PATTERN):
    """(data, None) for a body with a valid block, (None, None) for one with none, (None, reason) when malformed."""
    found = BLOCK.findall(body or "")
    if not found:
        return None, ("a task-board block is opened but not closed" if BLOCK_START in (body or "") else None)
    if len(found) > 1:
        return None, "the body holds more than one task-board block"
    try:
        return validate(json.loads(found[0]), pattern), None
    except (ValueError, Invalid) as error:
        return None, f"the task-board block is malformed: {error}"


def replace_block(body: str, data: dict) -> str:
    """`body` with its block (and the readable lines the helper wrote above it) replaced by `data`'s."""
    return render_body(data) if BLOCK_START in (body or "") or not (body or "").strip() \
        else (body.rstrip() + "\n\n" + render_body(data))


# ---- answers --------------------------------------------------------------------------------------------------------

def parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def human_messages(records) -> list:
    """(time, text) of each message the user typed, from a Claude Code transcript's records (parsed JSON lines).
    A typed message is a `user` record, or a `queued_command` attachment (typed while a turn ran), whose origin kind
    is "human"; a message from another session has the kind "peer"."""
    found = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("timestamp"), str):
            continue
        text = None
        if record.get("type") == "user" and (record.get("origin") or {}).get("kind") == "human":
            content = (record.get("message") or {}).get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(part.get("text", "") for part in content
                                 if isinstance(part, dict) and part.get("type") == "text")
        elif record.get("type") == "attachment":
            attachment = record.get("attachment") or {}
            origin = attachment.get("origin") or record.get("origin") or {}
            if attachment.get("type") == "queued_command" and origin.get("kind") == "human":
                text = attachment.get("prompt") if isinstance(attachment.get("prompt"), str) else None
        if text:
            try:
                found.append((parse_time(record["timestamp"]), text))
            except ValueError:
                continue
    return found


def squash(text: str) -> str:
    return " ".join(text.split())


def match_answer(quote: str, number: int, declared: tuple, messages: list, since: datetime):
    """(the declared answer, the time of the message) when `quote` is the user's words for job `number`; else
    Invalid. The quote must appear in a message typed after `since` (the job's filing), name `#number` exactly once,
    and give it one of `declared`; so must the whole message, so a quote cut from "#312 A #312 B" cannot pick one.
    Other jobs the quote names are not this call's concern."""
    pairs = [(int(n), word) for n, word in ANSWER.findall(quote) if int(n) == number]
    if not pairs:
        raise Invalid(f"the quote does not name #{number} with an answer; the user answers as \"#{number} <answer>\"")
    if len(pairs) > 1:
        raise Invalid(f"the quote names #{number} more than once")
    word = pairs[0][1]
    chosen = next((answer for answer in declared if answer.lower() == word.lower()), None)
    if chosen is None:
        raise Invalid(f"\"{word}\" is not an answer #{number} declares ({', '.join(declared)})")
    wanted, unclear = squash(quote), None
    for at, text in messages:
        if at > since and wanted in squash(text):
            said = [word for n, word in ANSWER.findall(text) if int(n) == number]
            if len(said) == 1 and said[0].lower() == chosen.lower():
                return chosen, at
            unclear = len(said)
    if unclear is not None:
        raise Invalid(f"the user's message names #{number} {unclear} times; ask them to answer it once")
    raise Invalid("the quote is not in any message the user typed in this session since the job was filed;"
                  " ask the user to answer here, or quote their words exactly")


# ---- the page -------------------------------------------------------------------------------------------------------

def clock(at: datetime, now: datetime | None = None) -> str:
    """HH:MM, with the date in front when `at` is not on `now`'s day, so yesterday's 20:45 does not read as today's."""
    local = at.astimezone()
    if now is not None and local.date() != now.astimezone().date():
        return local.strftime("%m-%d %H:%M")
    return local.strftime("%H:%M")


def waited(created: datetime, now: datetime) -> str:
    minutes = max(0, int((now - created).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 48 * 60:
        return f"{minutes // 60} h"
    return f"{minutes // (24 * 60)} days"


def link(number: int, url: str) -> str:
    return f"[#{number}]({url})"


def job_lines(job: dict, now: datetime) -> list:
    """At most 1 + MAX_OPTIONS + 1 lines, so at most 5: what, the options or summary, how to answer."""
    head = f"- {link(job['number'], job['url'])} **{job['data']['kind'] if job['data'] else 'job'}:** {job['title']}"
    held = ", ".join(link(n, url) for n, url in job["holds_up"]) or "nothing"
    head += f" · holds up {held} · waiting {waited(job['created'], now)}"
    if job["data"] is None:
        return [head, f"  - Malformed, so not shown: {job['malformed']}. Fix it with the helper."]
    data = job["data"]
    if data["kind"] == "decide":
        body = [f"  - **{o['key']}:** {o['text']}. Cost: {o['cost']}" for o in data["options"]]
        how = f"  - Recommended: **{data['recommend']['key']}**, {data['recommend']['why']}. Answer `#{job['number']} " \
              f"{data['recommend']['key']}` or another option."
    else:
        body = [f"  - {data['summary']}"]
        choices = " or ".join(f"`#{job['number']} {answer}`" for answer in answers(data))
        how = f"  - Answer {choices}."
    return [head] + body + [how]


def work_line(work: dict) -> str:
    head = f"- {link(work['number'], work['url'])} {work['title']}"
    if work["data"] is None:
        why = work["malformed"] or "no progress written yet"
        return f"{head}: {why}."
    data = work["data"]
    turn = "yours" if work["waits_on_you"] else "the worker's"
    return f"{head}: {data['goal']}, step {data['step']} of {data['of']}: {data['now']}. Next: {data['next']}. " \
           f"Turn: {turn}."


def render_page(now: datetime, jobs: list, work: list, events: list, since: datetime, blocks: list,
                more_url: str, stale: str = "") -> str:
    """The attention page. `jobs`: open jobs, oldest first, each {number, title, url, created, holds_up: [(n, url)],
    data, malformed}. `work`: In Progress issues, each {number, title, url, data, malformed, waits_on_you}. `events`:
    (time, number, url, text), any order. `blocks`: lines a project adds (its Goals), inserted after Needs you."""
    lines = [stale or f"Updated {clock(now)}", ""]
    lines.append(f"## Needs you ({len(jobs)})")
    if len(jobs) > JOBS_WARNING:
        lines.append(f"_{len(jobs)} jobs are open, more than {JOBS_WARNING}: the coordinator may be passing on calls"
                     f" it could make._")
    for job in jobs:
        lines += job_lines(job, now)
    if not jobs:
        lines.append("Nothing waits on you.")
    if blocks:
        lines += [""] + blocks
    lines += ["", f"## In progress ({len(work)})"]
    lines += [work_line(entry) for entry in work] or ["Nothing in progress."]
    recent = sorted((e for e in events if e[0] > since), key=lambda e: e[0], reverse=True)
    lines += ["", f"## Since you last looked ({clock(since, now)})"]
    for at, number, url, text in recent[:SINCE_MAX]:
        lines.append(f"- {clock(at, now)} {link(number, url)} {text}")
    if len(recent) > SINCE_MAX:
        lines.append(f"- … {len(recent) - SINCE_MAX} more: [recently updated issues]({more_url})")
    if not recent:
        lines.append("Nothing new.")
    return "\n".join(lines) + "\n"


def mark_stale(page: str, now: datetime, reason: str) -> str:
    """A page whose redraw failed: its first line says since when it is out of date, and why."""
    first, _, rest = page.partition("\n")
    found = re.match(r"(?:Updated|Out of date since) (\d\d:\d\d)", first)
    return f"Out of date since {found.group(1) if found else '?'}: {reason} at {clock(now)}\n{rest}"


def utc(text: str) -> datetime:
    """A GitHub or transcript timestamp as an aware datetime."""
    at = parse_time(text)
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
