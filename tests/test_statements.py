"""Statement assembly: delimiters, continuation, braces."""

from __future__ import annotations

from do2screen.scanner import scan
from do2screen.statements import SEMICOLON, assemble


def test_cr_mode_one_statement_per_line():
    text = "gen x = 1\nreplace x = 2\n"
    stmts, _, mode, _, _ = assemble(scan(text))
    assert [s.code for s in stmts] == ["gen x = 1", "replace x = 2"]
    assert mode == "cr"


def test_comment_and_blank_lines_produce_no_statements():
    text = "* c\ngen x = 1\n\n/* c2 */\nreplace x = 2\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert [s.code for s in stmts] == ["gen x = 1", "replace x = 2"]


def test_continuation_joins_lines_and_strips_marker():
    text = "gen x = 1 + ///\n  2\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert len(stmts) == 1
    assert stmts[0].code == "gen x = 1 + 2"
    assert stmts[0].start_line == 1
    assert stmts[0].end_line == 2
    assert stmts[0].member_lines == [1, 2]


def test_semicolon_mode_splits_on_semicolon():
    text = "#delimit ;\ngen a = 1; replace b = 2;\n"
    stmts, _, mode, used, _ = assemble(scan(text))
    assert mode == SEMICOLON
    assert used is True
    codes_list = [s.code for s in stmts if s.band == "statement"]
    assert codes_list == ["gen a = 1", "replace b = 2"]


def test_semicolon_mode_multiline_statement():
    text = "#delimit ;\nreplace c = 1 +\n  2;\n"
    stmts, _, mode, _, _ = assemble(scan(text))
    assert mode == SEMICOLON
    bodies = [s for s in stmts if s.band == "statement"]
    assert len(bodies) == 1
    assert bodies[0].code == "replace c = 1 + 2"
    assert bodies[0].start_line == 2
    assert bodies[0].end_line == 3


def test_switch_back_to_cr():
    text = "#delimit ;\ngen a = 1;\n#delimit cr\ngen b = 2\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert stmts[-1].delimit == "cr"
    bodies = [s.code for s in stmts if s.band == "statement"]
    assert bodies == ["gen a = 1", "gen b = 2"]


def test_multiple_mode_switches():
    text = (
        "#delimit ;\n"
        "gen a = 1;\n"
        "#delimit cr\n"
        "gen b = 2\n"
        "#delimit ;\n"
        "gen c = 3; gen d = 4;\n"
    )
    stmts, _, _, _, _ = assemble(scan(text))
    bodies = [s.code for s in stmts if s.band == "statement"]
    assert bodies == ["gen a = 1", "gen b = 2", "gen c = 3", "gen d = 4"]


def test_used_delimit_flag():
    _, _, _, used, _ = assemble(scan("gen a = 1\n"))
    assert used is False
    _, _, _, used_semi, _ = assemble(scan("#delimit ;\ngen a = 1;\n"))
    assert used_semi is True


def test_string_semicolon_does_not_split():
    text = "#delimit ;\ngen x = \"a;b\";\n"
    stmts, _, _, _, _ = assemble(scan(text))
    bodies = [s.code for s in stmts if s.band == "statement"]
    # The string content (with its `;`) is non-code and removed; the statement
    # is terminated only by the code-level `;`, leaving the target intact.
    assert bodies == ["gen x ="]


def test_comment_range_before_statement():
    text = "* c1\n* c2\ngen x = 1\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert len(stmts) == 1
    assert stmts[0].comment_start_line == 1
    assert stmts[0].comment_end_line == 2
    assert stmts[0].start_line == 3


def test_no_comment_range_when_blank_line_between():
    text = "* c\n\ngen x = 1\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert stmts[0].comment_start_line is None


def test_brace_block_indexing():
    text = "foreach x in 1 2 {\nreplace v`x' = 1\n}\ngen after = 1\n"
    stmts, blocks, _, _, _ = assemble(scan(text))
    assert len(blocks) == 1
    assert blocks[0].start_line == 1
    assert blocks[0].end_line == 3
    # The statement inside the loop reports the enclosing block.
    inner = next(s for s in stmts if s.start_line == 2)
    assert inner.brace_stack
    assert inner.brace_stack[-1].start_line == 1


def test_unterminated_brace_block():
    text = "foreach x in 1 2 {\nreplace v`x' = 1\n"
    _, blocks, _, _, _ = assemble(scan(text))
    assert blocks and blocks[0].end_line is None


def test_directive_statements_are_band_directive():
    stmts, _, _, _, _ = assemble(scan("#delimit ;\ngen a = 1;\n"))
    directives = [s for s in stmts if s.band == "directive"]
    assert len(directives) == 1
    assert directives[0].directive == ";"


def test_eof_unterminated_cr_statement_emitted():
    text = "gen x = 1 ///\n"
    stmts, _, _, _, _ = assemble(scan(text))
    assert len(stmts) == 1
    assert stmts[0].code == "gen x = 1"


def test_directive_with_same_line_statements_in_semicolon_mode():
    text = "#delimit ;gen a = 1;replace b = 2;\n#delimit cr\ngen c = 3\n"
    stmts, _, last_mode, _, _ = assemble(scan(text))
    bodies = [s.code for s in stmts if s.band == "statement"]
    assert bodies == ["gen a = 1", "replace b = 2", "gen c = 3"]
    assert last_mode == "cr"
