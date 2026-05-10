"""专题监控流水线测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from workflow.topic_monitoring_pipeline import TopicMonitoringPipeline


class DummyDB:
    def __init__(self):
        self.topics = {
            "topic-1": {
                "id": "topic-1",
                "name": "高铁舆情",
                "domain": "交通",
                "description": "示例高铁舆情专题",
                "is_active": True,
            }
        }
        self.snapshots = [
            {
                "id": "snap-1",
                "topic_id": "topic-1",
                "created_at": "2026-05-10T10:00:00Z",
                "post_count": 12,
                "engagement_sum": 320,
                "avg_sentiment": -0.1,
                "top_keywords": ["高铁", "服务", "投诉"],
                "volume_trend": "up",
                "summary": "热度上升",
            }
        ]
        self.alerts = [
            {
                "id": "alert-1",
                "topic_id": "topic-1",
                "alert_type": "volume_spike",
                "title": "话题热度上升",
                "message": "当前帖子数量显著增加",
                "severity": "warning",
                "metadata": {},
                "is_resolved": False,
                "created_at": "2026-05-10T10:05:00Z",
            }
        ]
        self.cases = [
            {
                "id": "case-1",
                "topic_id": "topic-1",
                "case_title": "高铁服务争议案例",
                "case_domain": "交通",
                "case_url": "opinion_analysis_kb/references/wiki/cases/case_example.md",
                "relevance_score": 0.92,
                "evidence": "匹配服务争议",
            }
        ]

    def create_monitor_topic(self, name: str, domain: str, description: str = "", owner: str = "system") -> Dict[str, Any]:
        topic_id = "topic-1"
        return self.topics[topic_id]

    def add_topic_keywords(self, topic_id: str, keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return keywords

    def create_snapshot(self, topic_id: str, snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = {"id": "snap-new", "topic_id": topic_id, **snapshot_data, "created_at": "2026-05-10T10:10:00Z"}
        self.snapshots.insert(0, snapshot)
        return snapshot

    def bulk_collect_posts(self, topic_id: str, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return posts

    def get_collected_posts(self, topic_id: str, limit: int = 100, since: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            {
                "id": "p1",
                "topic_id": topic_id,
                "likes": 10,
                "comments": 2,
                "shares": 1,
                "sentiment": "negative",
                "title": "高铁服务投诉",
                "content": "乘客对高铁服务质量存在质疑",
            }
        ]

    def get_latest_snapshot(self, topic_id: str) -> Optional[Dict[str, Any]]:
        return self.snapshots[0] if self.snapshots else None

    def list_alerts(self, topic_id: Optional[str] = None, is_resolved: Optional[bool] = None, severity: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return [a for a in self.alerts if (topic_id is None or a["topic_id"] == topic_id)]

    def create_alert(self, topic_id: str, alert_type: str, title: str, message: str, severity: str = "info", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        alert = {
            "id": "alert-new",
            "topic_id": topic_id,
            "alert_type": alert_type,
            "title": title,
            "message": message,
            "severity": severity,
            "metadata": metadata or {},
            "is_resolved": False,
            "created_at": "2026-05-10T10:15:00Z",
        }
        self.alerts.append(alert)
        return alert

    def get_topic_by_id(self, topic_id: str) -> Optional[Dict[str, Any]]:
        return self.topics.get(topic_id)

    def get_topic_keywords(self, topic_id: str) -> List[Dict[str, Any]]:
        return [{"keyword": "高铁"}, {"keyword": "服务争议"}]

    def get_snapshots(self, topic_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.snapshots[:limit]

    def get_linked_cases(self, topic_id: str, min_score: float = 0.5) -> List[Dict[str, Any]]:
        return [c for c in self.cases if c["topic_id"] == topic_id and c["relevance_score"] >= min_score]


def test_generate_periodic_report_writes_markdown(tmp_path: Path) -> None:
    db = DummyDB()
    pipeline = TopicMonitoringPipeline(db=db)

    result = pipeline.generate_periodic_report("topic-1", period="weekly", output_dir=tmp_path)

    report_path = Path(result["report_path"])
    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "# 高铁舆情 周报报告" in content
    assert "## 活动告警" in content
    assert "## 关联案例" in content


def test_supabase_config_requires_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)

    from workflow.supabase_client import SupabaseConfig

    with pytest.raises(ValueError, match="SUPABASE_URL/SUPABASE_KEY 或 DATABASE_URL/POSTGRES_URL"):
        SupabaseConfig.from_env()
