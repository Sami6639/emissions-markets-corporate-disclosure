"""Parsers for Shanghai Environment and Energy Exchange quote prose."""

from __future__ import annotations

import html
import re
from typing import Any


def _plain_text(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", "", html.unescape(value))


def _number(text: str, pattern: str, integer: bool = False) -> int | float | None:
    match = re.search(pattern, text)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    return int(float(raw)) if integer else float(raw)


def parse_quote_text(html_or_text: str, date: Any) -> dict[str, Any]:
    """Parse one national-carbon-market daily quote; missing fields remain ``None``."""
    text = _plain_text(html_or_text)
    result: dict[str, Any] = {"date": date}
    for key, label in (("open", "开盘价"), ("high", "最高价"),
                       ("low", "最低价"), ("close", "收盘价")):
        result[key] = _number(text, rf"{label}([\d,]+(?:\.\d+)?)元/吨")

    methods = {
        "listing": "挂牌协议交易",
        "block": "大宗协议交易",
        "auction": "单向竞价",
    }
    for key, label in methods.items():
        result[f"{key}_volume"] = _number(
            text, rf"{label}成交量([\d,]+(?:\.\d+)?)吨", integer=True
        )
        result[f"{key}_amount"] = _number(
            text, rf"{label}成交量[\d,]+(?:\.\d+)?吨[，,]成交额([\d,]+(?:\.\d+)?)元"
        )
    result["total_volume"] = _number(
        text, r"总成交量([\d,]+(?:\.\d+)?)吨", integer=True
    )
    result["total_amount"] = _number(
        text, r"总成交量[\d,]+(?:\.\d+)?吨[，,]总成交额([\d,]+(?:\.\d+)?)元"
    )
    return result
