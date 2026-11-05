"""Python 3.10 / 3.11 也能 import（2026-10-16 再发防止）：Mac 用 3.12，但云端例行任务 / 云端后备是 3.11 ——
2026-10-16 早上云端后备的 sim-day 因 live_ops / panel 里 3 处「f-string 的表达式里用了同种引号」（PEP 701，3.12 才允许）
import 就 SyntaxError、中途崩溃（c2c5cc9 修好），执行器为等日报晚了 10 分钟。Mac 上没有 3.10 / 3.11 可跑，
所以用 3.12 的分词器找 3.12 才允许的 f-string 写法：
  - 表达式里的字符串 / 嵌套 f-string 用了外层同种引号（外层单引号；外层三引号时内层也是同种三引号）
  - 表达式里有反斜杠、注释；单引号 f-string 的表达式跨行"""
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]                  # quant_breakout/
SKIP = {"var", ".venv", "venv", "__pycache__", "node_modules"}


def pep701_issues(src: str) -> list[tuple[int, str]]:
    """源码里 3.12 才允许的 f-string 写法 → [(行, 哪一种)]。"""
    out, stack = [], []                                     # stack：[(引号字符, 是否三引号)]（嵌套的 f-string）

    def clash(q: str, triple: bool) -> bool:
        return any(oq == q and (not ot or triple) for oq, ot in stack)

    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.FSTRING_START:
            body = tok.string.lstrip("rRfFbBuU")
            q, tr = body[0], len(body) == 3
            if stack and clash(q, tr):
                out.append((tok.start[0], "f-string 里又用了同种引号的 f-string"))
            stack.append((q, tr))
        elif tok.type == tokenize.FSTRING_END:
            stack.pop()
        elif stack:                                         # f-string 的表达式部分（字面部分是 FSTRING_MIDDLE）
            if tok.type == tokenize.STRING:
                body = tok.string.lstrip("rRbBuU")
                if clash(body[0], body[:3] in ('"""', "'''")):
                    out.append((tok.start[0], "f-string 的表达式里用了同种引号的字符串"))
                if "\\" in tok.string:
                    out.append((tok.start[0], "f-string 的表达式里有反斜杠"))
            elif tok.type == tokenize.COMMENT:
                out.append((tok.start[0], "f-string 的表达式里有注释"))
            elif tok.type == tokenize.NL and not stack[-1][1]:
                out.append((tok.start[0], "单引号 f-string 的表达式跨行"))
    return out


def _py_files():
    for p in sorted(ROOT.rglob("*.py")):
        if not SKIP.intersection(p.relative_to(ROOT).parts):
            yield p


def test_checker_finds_312_only_fstrings():
    bad = {
        'x = f"{"、".join(a)}"\n': "同种引号的字符串",
        "x = f'{d['k']}'\n": "同种引号的字符串",
        'x = f"{f"{a}"}"\n': "同种引号的 f-string",
        'x = f"{chr(10) + "\\n"}"\n': "同种引号的字符串",
        "x = f\"{'\\n'.join(a)}\"\n": "反斜杠",
        'x = f"{a  # 注释\n}"\n': "注释",
        'x = f"{a +\n b}"\n': "跨行",
        'x = f"""{"""a"""}"""\n': "同种引号的字符串",
    }
    for src, why in bad.items():
        got = pep701_issues(src)
        assert got and any(why in w for _, w in got), (src, got)
    ok = ['x = f"{\'、\'.join(a)}"\n', "x = f'{d[\"k\"]}'\n", 'x = f"{f\'{a}\'}"\n', 'x = f"""{"a"}"""\n',
          'x = f"""{a +\n b}"""\n', 'x = f"a\\n{b}"\n', 'x = f"{a!r:>{w}}"\n', 'x = "{}".format(f"{a}")\n']
    for src in ok:
        assert pep701_issues(src) == [], src


def test_all_sources_import_on_python_310_311():
    """仓库里所有 .py（qbreak/、scripts/、run.py、tests/）都不用 3.12 才允许的 f-string 写法（云端是 3.11）。"""
    found = [f"{p.relative_to(ROOT)}:{ln}: {why}" for p in _py_files() for ln, why in pep701_issues(p.read_text(encoding="utf-8"))]
    assert not found, "Python 3.10 / 3.11 上会 SyntaxError（云端例行任务 import 就崩）：\n" + "\n".join(found)
