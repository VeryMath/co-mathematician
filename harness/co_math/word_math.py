"""Read Word's native equations as LaTeX, preserving unsupported equations as text."""
from xml.etree.ElementTree import Element

M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class UnsupportedEquation(ValueError):
    pass


def _property(node: Element, name: str, default: str = "") -> str:
    kind = node.tag.removeprefix(M)
    value = node.find(f"{M}{kind}Pr/{M}{name}")
    return value.get(M + "val", "true" if name in {"nor", "degHide", "subHide", "supHide"} else default) if value is not None else default


def _latex(node: Element | None) -> str:
    if node is None:
        return ""
    kind = node.tag.removeprefix(M)
    child = lambda name: _latex(node.find(M + name))
    if node.tag in {W + "ins", W + "moveTo"}:
        return "".join(_latex(item) for item in node)
    if node.tag.startswith(W) or kind.endswith("Pr"):
        return ""
    if kind == "t":
        # Word math runs are literal symbols, not TeX commands.
        escapes = {"\\": r"\backslash ", "{": r"\{", "}": r"\}", "_": r"\_", "^": r"\char94 ", "%": r"\%", "$": r"\$", "#": r"\#", "&": r"\&", "~": r"\sim ", "∑": r"\sum ", "∏": r"\prod ", "∫": r"\int ", "∬": r"\iint ", "∭": r"\iiint ", "∮": r"\oint ", "▒": ""}
        return "".join(escapes.get(char, char) for char in node.text or "")
    if kind == "r":
        text = "".join(_latex(item) for item in node if item.tag == M + "t")
        if _property(node, "nor") in {"1", "true", "on"}:
            return r"\text{" + text + "}"
        style = _property(node, "sty", "i")
        script = _property(node, "scr", "roman")
        fonts = {"script": r"\mathcal", "fraktur": r"\mathfrak", "double-struck": r"\mathbb", "sans-serif": r"\mathsf", "monospace": r"\mathtt"}
        if script != "roman":
            if script not in fonts or style not in {"p", "b", "i", "bi"}:
                raise UnsupportedEquation("math font")
            text = fonts[script] + "{" + text + "}"
            return r"\boldsymbol{" + text + "}" if style in {"b", "bi"} else text
        if style not in {"p", "b", "i", "bi"}:
            raise UnsupportedEquation("math style")
        return {"p": r"\mathrm{", "b": r"\mathbf{", "bi": r"\boldsymbol{"}.get(style, "") + text + ("}" if style in {"p", "b", "bi"} else "")
    if kind in {"oMath", "e", "num", "den", "sub", "sup", "deg", "fName", "lim", "box"}:
        return "".join(_latex(item) for item in node)
    if kind == "f":
        fraction = _property(node, "type", "bar")
        if fraction not in {"bar", "lin", "skw", "noBar"}:
            raise UnsupportedEquation("fraction")
        command = r"\genfrac{}{}{0pt}{}" if fraction == "noBar" else r"\frac"
        return command + "{" + child("num") + "}{" + child("den") + "}"
    if kind in {"sSub", "sSup", "sSubSup", "sPre"}:
        sub = "_{" + child("sub") + "}" if node.find(M + "sub") is not None else ""
        sup = "^{" + child("sup") + "}" if node.find(M + "sup") is not None else ""
        base = "{" + child("e") + "}"
        return "{}" + sub + sup + base if kind == "sPre" else base + sub + sup
    if kind == "rad":
        degree = child("deg") if _property(node, "degHide") not in {"1", "true", "on"} else ""
        return r"\sqrt" + ("[" + degree + "]" if degree else "") + "{" + child("e") + "}"
    if kind == "d":
        delimiters = {"(": "(", ")": ")", "[": "[", "]": "]", "{": r"\{", "}": r"\}", "|": "|", "‖": r"\Vert", "⟨": r"\langle", "⟩": r"\rangle", "⌊": r"\lfloor", "⌋": r"\rfloor", "⌈": r"\lceil", "⌉": r"\rceil", "": "."}
        left, right = _property(node, "begChr", "("), _property(node, "endChr", ")")
        separator = _property(node, "sepChr", "|")
        if left not in delimiters or right not in delimiters or separator not in delimiters:
            raise UnsupportedEquation("delimiter")
        middle = (r"\middle" + delimiters[separator] + " ") if separator else ""
        return r"\left" + delimiters[left] + " " + middle.join(_latex(item) for item in node.findall(M + "e")) + r"\right" + delimiters[right] + " "
    if kind == "nary":
        operators = {"∑": r"\sum", "∏": r"\prod", "∐": r"\coprod", "∫": r"\int", "∬": r"\iint", "∭": r"\iiint", "∮": r"\oint", "⋃": r"\bigcup", "⋂": r"\bigcap"}
        operator = operators.get(_property(node, "chr", "∫"))
        if operator is None:
            raise UnsupportedEquation("operator")
        for name, symbol in (("sub", "_"), ("sup", "^")):
            value = child(name)
            if value and _property(node, name + "Hide") not in {"1", "true", "on"}:
                operator += symbol + "{" + value + "}"
        return operator + " " + child("e")
    if kind == "m":
        rows = [" & ".join(_latex(item) for item in row.findall(M + "e")) for row in node.findall(M + "mr")]
        return r"\begin{matrix}" + r" \\ ".join(rows) + r"\end{matrix}"
    if kind == "eqArr":
        return r"\begin{gathered}" + r" \\ ".join(_latex(item) for item in node.findall(M + "e")) + r"\end{gathered}"
    if kind == "func":
        return child("fName") + r"\," + child("e")
    if kind in {"limLow", "limUpp"}:
        return (r"\underset" if kind == "limLow" else r"\overset") + "{" + child("lim") + "}{" + child("e") + "}"
    if kind == "acc":
        commands = {"̂": r"\hat", "^": r"\hat", "̄": r"\bar", "¯": r"\bar", "⃗": r"\vec", "→": r"\vec", "̃": r"\tilde", "~": r"\tilde", "̇": r"\dot", "̈": r"\ddot", "̌": r"\check", "̆": r"\breve"}
        command = commands.get(_property(node, "chr", "̂"))
        if not command:
            raise UnsupportedEquation("accent")
        return command + "{" + child("e") + "}"
    if kind == "bar":
        return (r"\underline" if _property(node, "pos", "bot") == "bot" else r"\overline") + "{" + child("e") + "}"
    raise UnsupportedEquation(kind)


def read_word_paragraph(node: Element, warnings: set[str]) -> str:
    if node.tag == M + "oMathPara":
        return "".join(read_word_paragraph(item, warnings) if item.tag != M + "oMath" else _equation(item, warnings, True) for item in node if not item.tag.endswith("Pr"))
    if node.tag == M + "oMath":
        return _equation(node, warnings, False)
    if node.tag == W + "t":
        return node.text or ""
    if node.tag in {W + "br", W + "cr"}:
        return "\n"
    if node.tag == W + "tab":
        return "\t"
    if node.tag in {W + "drawing", W + "pict", W + "object"}:
        warnings.add("图片和旧式公式对象请查看原文件。")
        return "［图片或嵌入对象，请查看原文件］"
    return "".join(read_word_paragraph(item, warnings) for item in node)


def _equation(node: Element, warnings: set[str], display: bool) -> str:
    try:
        value = _latex(node)
        return "\n\\[" + value + "\\]\n" if display else "\\(" + value + "\\)"
    except UnsupportedEquation:
        warnings.add("部分公式结构暂不支持，已标出原始文字，请对照原文件。")
        text = "".join(item.text or "" for item in node.iter(M + "t"))
        return "［公式待对照原文：" + text + "］"
