# -*- coding: utf-8 -*-
"""Unit tests for the restricted-dictionary classification rules.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from rescan_restricted import classify, parse_pages


def test_bare_quota_dropped():
    assert classify("本年度公司获得产能置换配额合计 120 万吨。") == "drop_quota"


def test_carbon_quota_kept():
    assert classify("公司本期碳排放配额期末余额为 35 万吨。") == "hit"


def test_export_quota_with_carbon_context_kept():
    assert classify("本年度出口配额有所收紧；公司参与碳排放权交易累计成交 12 万吨。") == "hit"


def test_cea_substring_dropped():
    assert classify("The company operates several CEAs and OCEAN routes.") == "drop_cea"


def test_cea_standalone_with_chinese_carbon_kept():
    assert classify("公司持有 CEA 头寸，碳排放数据已通过核查。") == "hit"


def test_cea_standalone_without_chinese_carbon_dropped():
    assert classify("Settlement of CEA contracts is pending.") == "drop_cea"


def test_no_keyword_none():
    assert classify("公司主营业务为平板玻璃制造。") == "none"


def test_parse_pages():
    assert parse_pages("15") == [15]
    assert parse_pages("12;45;78") == [12, 45, 78]
    assert parse_pages("") == [] and parse_pages(None) == [] and parse_pages("nan") == []
