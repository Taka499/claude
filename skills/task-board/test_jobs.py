"""Tests for jobs.py. Run: python3 -m unittest discover -s skills/task-board"""
from __future__ import annotations

import re
import unittest
from datetime import datetime, timedelta, timezone

import jobs

T0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
DECIDE = {"kind": "decide",
          "options": [{"key": "A", "text": "fix the two rules first", "cost": "about half a day"},
                      {"key": "B", "text": "predict now", "cost": "140 of 900 moves left out"}],
          "recommend": {"key": "A", "why": "the full logs exist to find such gaps"}}
WORK = {"kind": "work", "goal": "the simulator matches the game", "step": 3, "of": 5, "now": "fixing two rules",
        "next": "predictions"}


def human(text: str, minutes: int, kind: str = "human") -> dict:
    return {"type": "user", "timestamp": (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
            "origin": {"kind": kind}, "message": {"role": "user", "content": text}}


class Lines(unittest.TestCase):
    def test_a_plain_line_passes(self):
        self.assertEqual(jobs.check_line("x", "fix the two rules first"), "fix the two rules first")

    def test_missing_multiline_and_long_lines_are_refused(self):
        for text, why in ((None, "missing"), ("  ", "missing"), ("a\nb", "one line"), ("x" * 121, "over the limit")):
            with self.subTest(text=text), self.assertRaisesRegex(jobs.Invalid, why):
                jobs.check_line("x", text)

    def test_a_bare_id_is_refused_and_a_glossed_one_passes(self):
        for text in ("fix E193 first", "after S54-4", "card p_card-02-ido-3_073 is odd"):
            with self.subTest(text=text), self.assertRaisesRegex(jobs.Invalid, "no plain explanation"):
                jobs.check_line("x", text)
        self.assertTrue(jobs.check_line("x", "fix E193 (the Sense rounding rule) first"))

    def test_words_numbers_and_issue_references_are_not_ids(self):
        self.assertTrue(jobs.check_line("x", "merge #315 after 3 checks, option A, v0.150, 45 logs"))

    def test_a_project_pattern_replaces_the_default(self):
        self.assertTrue(jobs.check_line("x", "fix E193 first", pattern=r"\bZ\d+\b"))
        with self.assertRaises(jobs.Invalid):
            jobs.check_line("x", "fix Z9 first", pattern=r"\bZ\d+\b")


class Blocks(unittest.TestCase):
    def test_each_kind_validates(self):
        for data in (DECIDE, WORK, {"kind": "approve", "summary": "merge help-pages and push"},
                     {"kind": "capture", "summary": "five more log sets"}, {"kind": "run", "summary": "! git push"}):
            with self.subTest(kind=data["kind"]):
                self.assertEqual(jobs.validate(data), data)

    def test_a_decision_needs_two_or_three_distinct_options_and_a_recommendation_among_them(self):
        one = dict(DECIDE, options=DECIDE["options"][:1])
        four = dict(DECIDE, options=[dict(DECIDE["options"][0], key=k) for k in "ABCD"])
        twin = dict(DECIDE, options=[DECIDE["options"][0], DECIDE["options"][0]])
        elsewhere = dict(DECIDE, recommend={"key": "C", "why": "x y z"})
        lower = dict(DECIDE, options=[dict(DECIDE["options"][0], key="a"), DECIDE["options"][1]])
        for data, why in ((one, "2 to 3"), (four, "2 to 3"), (twin, "share a key"), (elsewhere, "one of A, B"),
                          (lower, "capital letter")):
            with self.subTest(why=why), self.assertRaisesRegex(jobs.Invalid, why):
                jobs.validate(data)

    def test_missing_and_unknown_fields_are_named(self):
        with self.assertRaisesRegex(jobs.Invalid, "missing recommend"):
            jobs.validate({k: v for k, v in DECIDE.items() if k != "recommend"})
        with self.assertRaisesRegex(jobs.Invalid, "unknown holds_up"):
            jobs.validate(dict(WORK, holds_up=[3]))
        with self.assertRaisesRegex(jobs.Invalid, "kind must be"):
            jobs.validate({"kind": "note"})

    def test_work_steps_must_be_whole_numbers_in_order(self):
        for step, of in ((0, 5), (6, 5), (True, 5), ("3", 5), (2.0, 5)):
            with self.subTest(step=step), self.assertRaisesRegex(jobs.Invalid, "whole numbers"):
                jobs.validate(dict(WORK, step=step, of=of))

    def test_every_line_of_a_block_is_checked(self):
        with self.assertRaisesRegex(jobs.Invalid, "option B's cost"):
            jobs.validate(dict(DECIDE, options=[DECIDE["options"][0], dict(DECIDE["options"][1], cost="see C290")]))
        with self.assertRaisesRegex(jobs.Invalid, "next"):
            jobs.validate(dict(WORK, next="x" * 200))

    def test_declared_answers(self):
        self.assertEqual(jobs.answers(DECIDE), ("A", "B"))
        self.assertEqual(jobs.answers({"kind": "approve", "summary": "s"}), ("approve", "decline"))
        self.assertEqual(jobs.answers({"kind": "run", "summary": "s"}), ("done",))

    def test_a_body_round_trips_its_block_even_with_a_comment_end_in_its_text(self):
        data = dict(DECIDE, recommend={"key": "A", "why": "then --> stays inside"})
        body = jobs.render_body(data, note="Found while working on #298.")
        self.assertEqual(jobs.block_text(data).count(jobs.BLOCK_END), 1)
        self.assertIn("Found while working on #298.", body)
        self.assertEqual(jobs.read_block(body), (data, None))

    def test_no_block_reads_as_none_and_a_bad_one_as_malformed(self):
        self.assertEqual(jobs.read_block("an ordinary issue"), (None, None))
        good = jobs.block_text(WORK)
        for body, why in ((jobs.BLOCK_START + "\n{", "not closed"), (good + "\n" + good, "more than one"),
                          (good.replace('"step": 3', '"step": 9'), "whole numbers"),
                          (jobs.BLOCK_START + "\nnot json\n" + jobs.BLOCK_END, "malformed")):
            with self.subTest(why=why):
                data, error = jobs.read_block(body)
                self.assertIsNone(data)
                self.assertIn(why, error)

    def test_replacing_a_block_keeps_one_block(self):
        old = jobs.render_body(WORK)
        new = jobs.replace_block(old, dict(WORK, step=4))
        self.assertEqual(jobs.read_block(new)[0]["step"], 4)
        self.assertEqual(new.count(jobs.BLOCK_START), 1)
        kept = jobs.replace_block("The plan: docs/plans/x.md", WORK)
        self.assertTrue(kept.startswith("The plan: docs/plans/x.md"))
        self.assertEqual(jobs.read_block(kept)[0], WORK)


class Answers(unittest.TestCase):
    def test_typed_messages_count_and_peer_messages_do_not(self):
        queued = {"type": "attachment", "timestamp": "2026-11-01T00:05:00Z",
                  "attachment": {"type": "queued_command", "prompt": "#315 approve", "origin": {"kind": "human"}}}
        queued_peer = {"type": "attachment", "timestamp": "2026-11-01T00:06:00Z",
                       "attachment": {"type": "queued_command", "prompt": "#315 approve", "origin": {"kind": "peer"}}}
        blocks = dict(human("", 7), message={"content": [{"type": "text", "text": "#316 done"}]})
        records = [human("#312 A", 1), human("#312 B", 2, kind="peer"), queued, queued_peer, blocks,
                   {"type": "user", "timestamp": "not a time", "origin": {"kind": "human"},
                    "message": {"content": "x"}}]
        self.assertEqual([text for _, text in jobs.human_messages(records)], ["#312 A", "#315 approve", "#316 done"])

    def test_a_typed_answer_after_filing_is_accepted(self):
        messages = jobs.human_messages([human("ok, #312 a, and #315 approve", 10)])
        self.assertEqual(jobs.match_answer("#312 a, and #315 approve", 312, ("A", "B"), messages, T0),
                         ("A", T0 + timedelta(minutes=10)))
        self.assertEqual(jobs.match_answer("#315   approve", 315, ("approve", "decline"),
                                           jobs.human_messages([human("#315 approve", 10)]), T0)[0], "approve")

    def test_each_way_a_quote_can_fail(self):
        messages = jobs.human_messages([human("#312 A", 10), human("#312 C", 11), human("#312 A #312 B", 12)])
        cases = (("#312 A", T0 + timedelta(minutes=30), "since the job was filed"),
                 ("#313 A", T0, "does not name #312"),
                 ("#312 A #312 B", T0, "more than once"),
                 ("#312 C", T0, "not an answer #312 declares"),
                 ("#312 B", T0, "names #312 2 times"),
                 ("#312 A, really", T0, "not in any message"))
        for quote, since, why in cases:
            with self.subTest(quote=quote), self.assertRaisesRegex(jobs.Invalid, why):
                jobs.match_answer(quote, 312, ("A", "B"), messages, since)

    def test_a_clear_later_answer_counts_after_an_unclear_one(self):
        messages = jobs.human_messages([human("#312 A #312 B", 10), human("sorry: #312 A", 11)])
        self.assertEqual(jobs.match_answer("#312 A", 312, ("A", "B"), messages, T0)[1], T0 + timedelta(minutes=11))

    def test_a_peer_message_is_never_a_source(self):
        messages = jobs.human_messages([human("#312 A", 10, kind="peer")])
        with self.assertRaisesRegex(jobs.Invalid, "not in any message"):
            jobs.match_answer("#312 A", 312, ("A", "B"), messages, T0)


class Page(unittest.TestCase):
    def job(self, number=312, data=DECIDE, created=T0, malformed=None):
        return {"number": number, "title": "fix two engine rules first?", "url": f"https://x/{number}",
                "created": created, "holds_up": [(298, "https://x/298")], "data": data, "malformed": malformed}

    def page(self, **given):
        values = {"now": T0 + timedelta(hours=3), "jobs": [], "work": [], "events": [], "since": T0, "blocks": [],
                  "more_url": "https://x/issues"}
        values.update(given)
        return jobs.render_page(**values)

    def cells(self, row: str) -> list:
        """A table row's cells, split at the "|"s that are not escaped."""
        self.assertTrue(row.startswith("| ") and row.endswith(" |"), row)
        return [part.strip() for part in re.split(r"(?<!\\)\|", row[1:-1])]

    def test_a_decision_is_one_row_with_its_options_recommendation_and_answers(self):
        three = dict(DECIDE, options=DECIDE["options"] + [{"key": "C", "text": "drop them", "cost": "none"}])
        row = self.cells(jobs.job_row(self.job(data=three), T0 + timedelta(hours=3)))
        self.assertEqual(len(row), len(self.cells(jobs.TABLE_HEAD[0])))
        number, kind, question, options, recommended, held, waiting, answer = row
        self.assertEqual((number, kind, question), ("[#312](https://x/312)", "decide", "fix two engine rules first?"))
        self.assertEqual(options.split("<br>"), ["**A** fix the two rules first. Cost: about half a day",
                                                 "**B** predict now. Cost: 140 of 900 moves left out",
                                                 "**C** drop them. Cost: none"])
        self.assertEqual(recommended, "**A**: the full logs exist to find such gaps")
        self.assertEqual((held, waiting), ("[#298](https://x/298)", "3 h"))
        self.assertEqual(answer, "`#312 A` / `#312 B` / `#312 C`")

    def test_an_approval_a_capture_and_a_run_fill_their_cells(self):
        approve = self.cells(jobs.job_row(self.job(data={"kind": "approve", "summary": "checks green"}), T0))
        self.assertEqual(approve[2:5], ["fix two engine rules first?<br>checks green", "approve / decline", "—"])
        self.assertEqual(approve[7], "`#312 approve` / `#312 decline`")
        for kind in ("capture", "run"):
            row = self.cells(jobs.job_row(self.job(data={"kind": kind, "summary": "five more log sets"}), T0))
            self.assertEqual(row[1:5], [kind, "fix two engine rules first?", "five more log sets", "—"])
            self.assertEqual(row[7], "`#312 done`")

    def test_a_cell_keeps_its_row_whole(self):
        job = dict(self.job(data={"kind": "approve", "summary": "a | b"}), title="one |\ntwo", holds_up=[])
        row = jobs.job_row(job, T0)
        self.assertNotIn("\n", row)
        cells = self.cells(row)
        self.assertEqual(len(cells), 8)
        self.assertEqual(cells[2], "one &#124; two<br>a &#124; b")
        self.assertEqual(cells[5], "nothing")

    def test_a_cell_encodes_what_could_break_the_table_or_render_as_html(self):
        for raw, shown in (("x\\|y", "x\\\\&#124;y"), ("a <br> b", "a &lt;br&gt; b"), ("R&D", "R&amp;D"),
                           ("<script>", "&lt;script&gt;"), ("plain", "plain")):
            with self.subTest(raw=raw):
                self.assertEqual(jobs.cell(raw), shown)
        row = jobs.job_row(dict(self.job(data=None, malformed='bad: {"a": "|x\\|"}'), holds_up=[]), T0)
        self.assertEqual(len(self.cells(row)), 8)
        self.assertNotIn("|x", row)

    def test_a_link_with_a_character_that_could_end_it_shows_as_a_plain_number(self):
        self.assertEqual(jobs.link(5, "https://github.com/o/r/issues/5"), "[#5](https://github.com/o/r/issues/5)")
        for url in ("https://x/5|y", "https://x/(5)", "https://x/5 y", "https://x/<5>", "javascript:alert(1)", ""):
            with self.subTest(url=url):
                self.assertEqual(jobs.link(5, url), "#5")

    def test_a_malformed_job_is_shown_as_malformed_not_as_content(self):
        row = self.cells(jobs.job_row(self.job(data=None, malformed="the block is malformed: x"), T0))
        self.assertEqual(row[1], "job")
        self.assertEqual(row[3], "malformed: the block is malformed: x")
        self.assertEqual(row[7], "fix it with the helper")

    def test_needs_you_is_a_table_oldest_first_under_its_warning(self):
        page = self.page(jobs=[self.job(number=n) for n in (3, 1, 2)] + [self.job(number=n) for n in range(4, 9)])
        lines = page.splitlines()
        start = lines.index("## Needs you (8)")
        self.assertTrue(lines[start + 1].startswith("_8 jobs are open, more than 7"))
        self.assertEqual(lines[start + 2], "")
        self.assertEqual(tuple(lines[start + 3:start + 5]), jobs.TABLE_HEAD)
        rows = lines[start + 5:start + 13]
        self.assertEqual([self.cells(r)[0].split("]")[0] for r in rows[:3]], ["[#3", "[#1", "[#2"])
        self.assertEqual(lines[start + 13], "")

    def test_no_jobs_means_no_table(self):
        page = self.page()
        self.assertIn("## Needs you (0)\nNothing waits on you.", page)
        self.assertNotIn(jobs.TABLE_HEAD[0], page)

    def test_more_than_seven_jobs_warns_first(self):
        page = self.page(jobs=[self.job(number=n) for n in range(8)])
        self.assertIn("8 jobs are open, more than 7", page)
        self.assertNotIn("more than 7", self.page(jobs=[self.job(number=n) for n in range(7)]))

    def test_work_lines_say_whose_turn_it_is(self):
        entry = {"number": 298, "title": "S54-4", "url": "https://x/298", "data": WORK, "malformed": None,
                 "waits_on_you": True}
        self.assertIn("step 3 of 5: fixing two rules. Next: predictions. Turn: yours.", jobs.work_line(entry))
        self.assertIn("Turn: the worker's.", jobs.work_line(dict(entry, waits_on_you=False)))
        self.assertIn("no progress written yet", jobs.work_line(dict(entry, data=None)))

    def test_since_keeps_newer_events_newest_first_and_caps_them(self):
        events = [(T0 + timedelta(minutes=m), m, f"https://x/{m}", f"event {m}") for m in range(-5, 15)]
        page = self.page(events=events)
        shown = [line for line in page.splitlines() if line.startswith("- ") and "event" in line]
        self.assertEqual(len(shown), 10)
        self.assertIn("event 14", shown[0])
        self.assertIn("4 more: [recently updated issues](https://x/issues)", page)
        self.assertNotIn("event -1", page)

    def test_project_blocks_go_after_needs_you(self):
        page = self.page(blocks=["## Goals", "- the simulator: 7 rule differences found, 0 fixed"])
        self.assertLess(page.index("## Needs you"), page.index("## Goals"))
        self.assertLess(page.index("## Goals"), page.index("## In progress"))

    def test_a_stale_page_says_since_when(self):
        page = self.page()
        stale = jobs.mark_stale(page, T0 + timedelta(hours=5), "GitHub unreachable")
        first = stale.splitlines()[0]
        self.assertTrue(first.startswith(f"Out of date since {jobs.clock(T0 + timedelta(hours=3))}: GitHub unreachable"))
        again = jobs.mark_stale(stale, T0 + timedelta(hours=6), "GitHub unreachable")
        self.assertTrue(again.startswith(f"Out of date since {jobs.clock(T0 + timedelta(hours=3))}:"))
        self.assertEqual(stale.splitlines()[1:], page.splitlines()[1:])

    def test_a_time_from_another_day_carries_its_date(self):
        now = T0 + timedelta(hours=12)
        self.assertEqual(jobs.clock(now - timedelta(minutes=5), now), jobs.clock(now - timedelta(minutes=5)))
        yesterday = now - timedelta(days=1)
        self.assertEqual(jobs.clock(yesterday, now), yesterday.astimezone().strftime("%m-%d %H:%M"))
        page = self.page(now=now, since=yesterday)
        self.assertIn(f"## Since you last looked ({yesterday.astimezone().strftime('%m-%d %H:%M')})", page)

    def test_waiting_times(self):
        self.assertEqual(jobs.waited(T0, T0 + timedelta(minutes=20)), "20 min")
        self.assertEqual(jobs.waited(T0, T0 + timedelta(hours=30)), "30 h")
        self.assertEqual(jobs.waited(T0, T0 + timedelta(days=3)), "3 days")


if __name__ == "__main__":
    unittest.main()
