# -*- coding: utf-8 -*-
"""Report where Chinese characters occur in this package.

Comments and docstrings should contain none. Keyword strings inside the code are
expected to remain in Chinese, because they are the patterns matched against the
source documents, and so are company and sector names inside the data files.
"""
from __future__ import annotations
import ast, glob, io, re, tokenize

CN = re.compile(r"[一-鿿]")


def main() -> int:
    docs = set()
    counts = {"comments": 0, "docstrings": 0, "string literals": 0}
    for f in sorted(glob.glob("src/*.py") + glob.glob("tests/*.py")):
        src = io.open(f, encoding="utf-8").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                 ast.AsyncFunctionDef)):
                d = ast.get_docstring(node, clean=False)
                if d:
                    docs.add(d)
        with io.open(f, "rb") as fh:
            for tok in tokenize.tokenize(fh.readline):
                n = len(CN.findall(tok.string))
                if not n:
                    continue
                if tok.type == tokenize.COMMENT:
                    counts["comments"] += n
                elif tok.type == tokenize.STRING:
                    inner = tok.string.strip("\"'")
                    key = ("docstrings" if any(inner.strip() == d.strip() for d in docs)
                           else "string literals")
                    counts[key] += n
    for k, v in counts.items():
        print(f"  {k:16s} {v:6d}")
    for k in ("comments", "docstrings"):
        if counts[k]:
            print(f"FAIL: {k} should contain no Chinese")
            return 1
    print("PASS: comments and docstrings are English throughout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
