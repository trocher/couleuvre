import re


def word_at_position(
    line: str,
    character: int,
    re_start_word=re.compile(r"[A-Za-z_0-9]+(?:\.[A-Za-z_0-9]+)*$"),
    re_end_word=re.compile(r"^[A-Za-z_0-9]*"),
) -> str:
    # Get the first half by searching backwards from `character` position
    start_part = re_start_word.search(line[:character])
    start_word = start_part.group() if start_part else ""

    # Get the second half by searching forward from `character` position
    end_part = re_end_word.search(line[character:])
    end_word = end_part.group() if end_part else ""

    # Combine both parts to form the full word
    return start_word + end_word


def test_basic():
    line1 = "hello.hallo.bot"
    line2 = "hello.bot"
    line3 = "hello(bot).world.hello"
    assert word_at_position(line1, 8) == "hello.hallo"
    assert word_at_position(line2, 7) == "hello.bot"
    assert word_at_position(line2, 2) == "hello"
    assert word_at_position(line3, 7) == "bot"
    assert word_at_position(line3, 14) == "world"
    assert word_at_position(line3, 20) == "world.hello"
