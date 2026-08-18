"""Scanner: code masks for all comment/string forms and edge cases."""

from __future__ import annotations

from do2screen.scanner import CODE, NON, read_source, scan


def code_only(_text: str, mask: str) -> str:
    return "".join(c for c, m in zip(_text, mask) if m == CODE)


def test_all_code_line():
    result = scan("gen x = 1\n")
    assert list(result.lines[0].code_mask) == ["C"] * len("gen x = 1")
    assert result.lines[0].has_code() is True


def test_star_comment_only_line_is_non_code():
    result = scan("* a full line comment\n")
    assert all(c == NON for c in result.lines[0].code_mask)
    assert result.lines[0].has_code() is False


def test_star_comment_with_leading_space():
    result = scan("   * indented comment\n")
    line = result.lines[0]
    for i, ch in enumerate(line.code_mask):
        m = line.text[i]
        if m == "*" or i > line.text.index("*"):
            assert ch == NON
        elif m.isspace():
            assert ch == CODE


def test_double_slash_line_comment():
    result = scan("gen x = 1 // trailing note\n")
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    assert code.strip() == "gen x = 1"
    assert not code.strip().endswith("//")


def test_forward_slash_slash_slash_is_continuation_not_comment():
    result = scan("replace x = 2 ///\n")
    line = result.lines[0]
    # The three slashes are code (continuation marker).
    idx = line.text.index("///")
    assert line.code_mask[idx : idx + 3] == "CCC"
    # Nothing after the marker exists on this line.


def test_continuation_ignores_tail():
    result = scan("gen x = 1 /// ignore this text\n")
    line = result.lines[0]
    code = code_only(line.text, line.code_mask)
    assert code.strip() == "gen x = 1 ///"
    # Everything after ``///`` is non-code (ignored by Stata).
    marker = line.text.index("///")
    for i in range(marker + 3, len(line.code_mask)):
        assert line.code_mask[i] == NON


def test_inline_block_comment():
    result = scan("gen x = 1 /* note */ + y\n")
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    assert "note" not in code
    assert "y" in code


def test_multiline_block_comment():
    text = "gen a = 1\n/* start\nbody\nend */\ngen b = 2\n"
    result = scan(text)
    assert result.lines[0].has_code() is True
    assert result.lines[1].has_code() is False
    assert result.lines[2].has_code() is False
    assert result.lines[3].has_code() is False
    assert result.lines[4].has_code() is True
    assert result.unterminated_block_comment_start is None


def test_standard_string_content_is_non_code():
    result = scan('label variable x "a b c"\n')
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    assert "a b c" not in code
    assert "x" in code


def test_compound_string_with_embedded_delimiters():
    text = 'gen x = `"a "qui" b c"\' + y\n'
    result = scan(text)
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    # The compound string content is non-code; only x and y remain as code.
    assert "a" not in code
    assert "y" in code


def test_compound_string_with_embedded_comment_markers():
    text = "gen x = `\"has // and /* and `\"' + y\n"
    result = scan(text)
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    assert "y" in code


def test_macro_references_are_code():
    result = scan("foreach x in 1 2 {}\n")
    line = result.lines[0]
    assert line.has_code() is True
    assert "`" not in line.code_mask  # no literal backtick in this fixture
    result2 = scan("gen v`x' = 1\n")
    code = code_only(result2.lines[0].text, result2.lines[0].code_mask)
    assert "`" in code  # macro backtick remains code (detected structurally)


def test_bom_is_stripped(tmp_path):
    path = tmp_path / "bom.do"
    path.write_bytes(b"\xef\xbb\xbfgen x = 1\n")
    text = read_source(path)
    assert text == "gen x = 1\n"
    result = scan(text)
    assert result.lines[0].has_code() is True


def test_undecodable_bytes_replaced_with_diagnostic(tmp_path, capsys):
    path = tmp_path / "bad.do"
    path.write_bytes(b"gen x = 1\n\xff\xfe bad\n")
    text = read_source(path)
    assert "\ufffd" in text
    assert "warning" in capsys.readouterr().err
    # The file still parses line by line deterministically.
    result = scan(text)
    assert len(result.lines) == 2


def test_mixed_line_comment_and_code():
    text = "gen x = 1 /* a */ + 2 // tail\n"
    result = scan(text)
    code = code_only(result.lines[0].text, result.lines[0].code_mask)
    assert "a" not in code
    assert "tail" not in code
    assert code.startswith("gen x = 1")


def test_executable_line_numbers():
    result = scan("* c\ngen x = 1\n\n/* c2 */\nreplace x = 2\n")
    assert result.executable_line_numbers() == [2, 5]
