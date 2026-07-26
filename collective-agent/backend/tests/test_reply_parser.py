from __future__ import annotations

from app.services.reply_parser import parse_reply


def test_parses_a_fenced_json_block():
    parsed = parse_reply(
        'Work done.\n```json\n{"summary": "s", "current_task": "t", '
        '"next_step": "n", "status": "done"}\n```'
    )
    assert parsed.structured is True
    assert (parsed.summary, parsed.current_task) == ("s", "t")
    assert (parsed.next_step, parsed.status) == ("n", "done")


def test_parses_an_unfenced_trailing_object():
    parsed = parse_reply('Prose first.\n{"summary": "s", "next_step": "n"}')
    assert parsed.structured is True
    assert parsed.summary == "s"
    assert parsed.current_task is None


def test_uses_the_last_block_when_the_reply_contains_examples():
    parsed = parse_reply(
        '```json\n{"summary": "an example in the docs"}\n```\n'
        'and the real one:\n```json\n{"summary": "the actual result"}\n```'
    )
    assert parsed.summary == "the actual result"


def test_rejects_an_unknown_status():
    assert parse_reply('```json\n{"summary": "s", "status": "vibing"}\n```').status is None


def test_ignores_malformed_json_and_falls_back_to_prose():
    parsed = parse_reply("I fixed the bug.\n```json\n{oops,}\n```")
    assert parsed.structured is False
    assert parsed.summary == "I fixed the bug."


def test_strips_code_blocks_from_the_prose_fallback():
    parsed = parse_reply("Added a helper.\n```python\nprint('x')\n```\nDone.")
    assert "print" not in parsed.summary
    assert parsed.summary == "Added a helper. Done."


def test_truncates_at_a_sentence_boundary():
    text = "First sentence is short. " + "Padding words " * 100
    parsed = parse_reply(text, summary_max_chars=60)
    assert parsed.summary == "First sentence is short."


def test_truncates_mid_word_only_when_there_is_no_boundary():
    parsed = parse_reply("word " * 100, summary_max_chars=20)
    assert parsed.summary.endswith("…")
    assert len(parsed.summary) <= 21


def test_handles_an_empty_reply():
    assert parse_reply("").summary == "(agent returned no text)"
