"""案例库自动生成（workflow.case_library_generator + wiki_cli cases 召回）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from workflow.case_library_generator import write_event_analysis_case_wiki
from workflow.wiki_cli import retrieve_wiki_sources


def test_case_write_and_wiki_retrieval_hits(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    wiki_root = root / "opinion_analysis_kb" / "references" / "wiki"
    wiki_root.mkdir(parents=True)
    (wiki_root / "index.md").write_text("# Wiki\n\n## 页面目录\n\n", encoding="utf-8")

    task_id = "abc-test-uuid-0001"
    proc = root / "sandbox" / task_id / "过程文件"
    res = root / "sandbox" / task_id / "结果文件"
    proc.mkdir(parents=True)
    res.mkdir(parents=True)

    (proc / "graph_rag_enrichment.json").write_text(
        json.dumps({"similar_cases": {"items": [{"title": "历史案例A", "summary": "反转路径"}]}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (proc / "wiki_qa_snapshot.json").write_text("{}", encoding="utf-8")
    (proc / "reference_insights.json").write_text(
        json.dumps({"items": [{"title": "智库条目", "snippet": "建议尽快披露权威信息"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    html_path = res / "report_demo.html"
    html_path.write_text("<html/>", encoding="utf-8")

    search_plan = {
        "version": "search_plan_v1",
        "eventIntroduction": "某市地铁乘客冲突引发短视频围观",
        "searchWords": ["地铁", "乘客", "冲突"],
        "timeRange": "2026-01-01 00:00:00;2026-01-07 23:59:59",
        "verificationChecklist": ["核对监控时间轴", "区分事实与传言"],
        "evidenceSnippets": ["现场视频片段传播极快"],
    }
    timeline_json = {"timeline": [{"time": "2026-01-02", "summary": "话题登上同城热搜"}]}
    sentiment_json = {"negative_summary": ["质疑运营方回应过慢"]}

    monkeypatch.setenv("SONA_WIKI_ROOT", str(wiki_root))

    meta = write_event_analysis_case_wiki(
        project_root=root,
        task_id=task_id,
        process_dir=proc,
        search_plan=search_plan,
        user_query="分析地铁乘客冲突舆情",
        html_report_path=str(html_path),
        timeline_json=timeline_json,
        sentiment_json=sentiment_json,
    )
    case_rel = str(meta.get("case_rel") or "")
    assert case_rel.startswith("cases/case_")
    case_fp = wiki_root / "cases" / Path(case_rel).name
    assert case_fp.is_file()
    text = case_fp.read_text(encoding="utf-8")
    assert text.startswith("---")
    for key in (
        "title:",
        "domain:",
        "actors:",
        "timeline:",
        "risk_patterns:",
        "response_tactics:",
        "evidence:",
        "report_path:",
    ):
        assert key in text
    idx = (wiki_root / "index.md").read_text(encoding="utf-8")
    assert case_rel in idx

    srcs = retrieve_wiki_sources("地铁乘客冲突 舆情", topk=8, project_root=root)
    paths = [s.path.replace("\\", "/") for s in srcs]
    assert any("/references/wiki/cases/" in p for p in paths), paths
