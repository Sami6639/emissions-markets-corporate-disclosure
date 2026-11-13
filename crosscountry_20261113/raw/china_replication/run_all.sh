#!/usr/bin/env bash
# 一条命令复现论文全部表格。用法：bash run_all.sh
# 需先激活或存在 .venv；若无，按 requirements.txt 建环境。
set -euo pipefail
cd "$(dirname "$0")"
PY=./.venv/bin/python
[ -x "$PY" ] || PY=python3

echo "[1/4] 单元测试"
$PY -m pytest tests/ -q

echo "[2/4] 样本定义与面板"
$PY src/define_sample.py
$PY src/build_panel2.py

echo "[3/4] 论文表格"
$PY src/run_paper.py
$PY src/run_paper2.py
$PY src/run_valuation.py

echo "[4/4] 图"
for f in src/make_fig_main.py src/make_fig_event.py src/make_fig_events.py src/make_paper_figs.py; do
  [ -f "$f" ] && $PY "$f" || echo "  跳过 $f（不存在）"
done

echo
echo "完成。表见 out/tables/，图见 out/figures/。"
echo "说明：文本抽取步骤（src/parse_carbon_disclosure.py、src/parse_narrative.py、"
echo "src/rescan_restricted.py、src/rescan_namefilter.py）需要 raw/reports/ 下约 10GB"
echo "原始年报 PDF，未随包分发；其产出已归档为 out/carbon_*.csv，本脚本直接复用。"
