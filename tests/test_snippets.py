"""Tests for client-side snippet generation helpers."""


from mcp_fess.server import _apply_highlight, _extract_query_terms, _generate_snippets

# --- _extract_query_terms ---


def test_extract_query_terms_simple():
    terms = _extract_query_terms("hello world")
    assert "hello" in terms
    assert "world" in terms


def test_extract_query_terms_strips_boolean_operators():
    terms = _extract_query_terms("foo AND bar OR baz NOT qux")
    assert "foo" in terms
    assert "bar" in terms
    assert "baz" in terms
    assert "qux" in terms
    assert "AND" not in terms
    assert "OR" not in terms
    assert "NOT" not in terms


def test_extract_query_terms_strips_punctuation():
    terms = _extract_query_terms('"quoted phrase", test.')
    assert "quoted" in terms
    assert "phrase" in terms
    assert "test" in terms


def test_extract_query_terms_drops_single_chars():
    terms = _extract_query_terms("a big test")
    assert "a" not in terms
    assert "big" in terms
    assert "test" in terms


def test_extract_query_terms_empty():
    assert _extract_query_terms("") == []


def test_extract_query_terms_only_operators():
    assert _extract_query_terms("AND OR NOT") == []


# --- _apply_highlight ---


def test_apply_highlight_single_term():
    result = _apply_highlight("hello world", ["hello"], "<em>", "</em>")
    assert result == "<em>hello</em> world"


def test_apply_highlight_multiple_terms():
    result = _apply_highlight("hello world", ["hello", "world"], "<em>", "</em>")
    assert "<em>hello</em>" in result
    assert "<em>world</em>" in result


def test_apply_highlight_case_insensitive():
    result = _apply_highlight("Hello World", ["hello"], "<em>", "</em>")
    assert "<em>Hello</em>" in result


def test_apply_highlight_no_match():
    result = _apply_highlight("hello world", ["xyz"], "<em>", "</em>")
    assert result == "hello world"


def test_apply_highlight_no_terms():
    result = _apply_highlight("hello world", [], "<em>", "</em>")
    assert result == "hello world"


def test_apply_highlight_custom_tags():
    result = _apply_highlight("hello world", ["hello"], "<b>", "</b>")
    assert result == "<b>hello</b> world"


def test_apply_highlight_longer_term_takes_priority():
    # "hello world" is longer than "hello" - longer matches take priority
    result = _apply_highlight("hello world test", ["hello world", "hello"], "<em>", "</em>")
    assert "<em>hello world</em>" in result
    # "hello" should NOT be separately highlighted since it's covered by "hello world"
    assert result.count("<em>") == 1


def test_apply_highlight_no_double_tagging():
    result = _apply_highlight("test test", ["test"], "<em>", "</em>")
    assert result == "<em>test</em> <em>test</em>"
    assert result.count("<em>") == 2


# --- _generate_snippets ---


def test_generate_snippets_basic():
    text = "The quick brown fox jumps over the lazy dog"
    snippets = _generate_snippets(text, ["fox"], 30, 1, "<em>", "</em>", 1000)
    assert len(snippets) == 1
    assert "<em>fox</em>" in snippets[0]


def test_generate_snippets_empty_text():
    snippets = _generate_snippets("", ["test"], 200, 2, "<em>", "</em>", 1000)
    assert snippets == []


def test_generate_snippets_no_terms_returns_start():
    text = "A" * 500
    snippets = _generate_snippets(text, [], 100, 2, "<em>", "</em>", 1000)
    assert len(snippets) == 1
    assert len(snippets[0]) <= 101  # 100 chars + possible ellipsis char


def test_generate_snippets_no_match_returns_start():
    text = "The quick brown fox"
    snippets = _generate_snippets(text, ["xyz"], 50, 2, "<em>", "</em>", 1000)
    assert len(snippets) == 1
    assert "xyz" not in snippets[0]


def test_generate_snippets_max_fragments_respected():
    text = "foo bar foo bar foo bar foo bar foo bar"
    snippets = _generate_snippets(text, ["foo"], 5, 2, "<em>", "</em>", 1000)
    assert len(snippets) <= 2


def test_generate_snippets_ellipsis_when_not_at_start():
    text = "A" * 100 + "target" + "A" * 100
    snippets = _generate_snippets(text, ["target"], 20, 1, "<em>", "</em>", 1000)
    assert len(snippets) == 1
    assert snippets[0].startswith("\u2026")


def test_generate_snippets_no_leading_ellipsis_at_start():
    text = "target " + "A" * 200
    snippets = _generate_snippets(text, ["target"], 20, 1, "<em>", "</em>", 1000)
    assert len(snippets) == 1
    assert not snippets[0].startswith("\u2026")


def test_generate_snippets_trailing_ellipsis_when_more_text():
    text = "target " + "A" * 200
    snippets = _generate_snippets(text, ["target"], 20, 1, "<em>", "</em>", 1000)
    assert snippets[0].endswith("\u2026")


def test_generate_snippets_no_trailing_ellipsis_at_end():
    text = "A" * 100 + " target"
    snippets = _generate_snippets(text, ["target"], 200, 1, "<em>", "</em>", 1000)
    assert not snippets[0].endswith("\u2026")


def test_generate_snippets_scan_max_chars_limits_search():
    # Term only appears beyond scan_max_chars
    text = "A" * 100 + "target"
    snippets = _generate_snippets(text, ["target"], 20, 1, "<em>", "</em>", 50)
    # Since scan only covers first 50 chars, "target" at pos 100 won't be found
    assert len(snippets) == 1
    # Should return fallback (start of text)
    assert "<em>target</em>" not in snippets[0]


def test_generate_snippets_size_chars_controls_window():
    text = "A" * 50 + "target" + "A" * 50
    snippets = _generate_snippets(text, ["target"], 10, 1, "<em>", "</em>", 1000)
    # Window should be ~10 chars wide (may include prefix/suffix ellipsis)
    content_len = len(snippets[0].replace("\u2026", "").replace("<em>", "").replace("</em>", ""))
    assert content_len <= 12  # 10 chars + some slack for word boundaries


def test_generate_snippets_multiple_terms():
    text = "The quick brown fox. The lazy dog sleeps."
    snippets = _generate_snippets(text, ["fox", "dog"], 20, 3, "<em>", "</em>", 1000)
    combined = " ".join(snippets)
    assert "<em>fox</em>" in combined or "<em>dog</em>" in combined
