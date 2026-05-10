"""话题监控流水线与周期报告生成。

支持基于 Supabase/Postgres 的专题监控、快照分析、风险告警和日报/周报输出。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import jieba

from workflow.supabase_client import SupabaseDB, get_db

SearchFunc = Callable[[List[str], str, int], List[Dict[str, Any]]]


@dataclass
class MonitorConfig:
    scan_interval_minutes: int = 60
    min_posts_for_trend: int = 10
    viral_threshold: int = 1000
    alert_cooldown_hours: int = 24
    snapshot_interval_hours: int = 6


@dataclass
class TopicMonitor:
    topic_id: str
    name: str
    domain: str
    keywords: List[Dict[str, Any]] = field(default_factory=list)
    config: MonitorConfig = field(default_factory=MonitorConfig)


class TopicMonitoringPipeline:
    """话题监控流水线"""

    def __init__(self, db: Optional[SupabaseDB] = None, config: Optional[MonitorConfig] = None):
        self.db = db or get_db()
        self.config = config or MonitorConfig()

    def create_topic(
        self,
        name: str,
        domain: str,
        keywords: List[str],
        description: str = "",
        owner: str = "system",
    ) -> Dict[str, Any]:
        topic = self.db.create_monitor_topic(
            name=name,
            domain=domain,
            description=description,
            owner=owner,
        )
        topic_id = topic["id"]

        if keywords:
            keyword_records = [
                {"keyword": kw, "keyword_type": "include", "weight": 1.0}
                for kw in keywords
                if str(kw).strip()
            ]
            if keyword_records:
                self.db.add_topic_keywords(topic_id, keyword_records)

        self.db.create_snapshot(topic_id, {
            "post_count": 0,
            "engagement_sum": 0,
            "avg_sentiment": 0.0,
            "top_keywords": [],
            "volume_trend": "stable",
            "summary": "话题初始化",
        })
        return topic

    def scan_topic(
        self,
        topic_id: str,
        search_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if search_results:
            posts = []
            for item in search_results:
                posts.append({
                    "post_id": str(item.get("id", "") or ""),
                    "post_url": str(item.get("url", "") or ""),
                    "platform": str(item.get("platform", "unknown") or "unknown"),
                    "author": str(item.get("author", "") or ""),
                    "title": str(item.get("title", "") or ""),
                    "content": str(item.get("content", "") or ""),
                    "likes": int(item.get("likes") or 0),
                    "comments": int(item.get("comments") or 0),
                    "shares": int(item.get("shares") or 0),
                    "sentiment": str(item.get("sentiment", "neutral") or "neutral"),
                    "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                    "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
                })
            self.db.bulk_collect_posts(topic_id, posts)

        snapshot = self._generate_snapshot(topic_id)
        alerts = self._check_alerts(topic_id, snapshot)
        return {"snapshot": snapshot, "alerts": alerts}

    def _generate_snapshot(
        self,
        topic_id: str,
        since: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        since = since or (datetime.utcnow() - timedelta(hours=self.config.snapshot_interval_hours))
        posts = self.db.get_collected_posts(topic_id, limit=500, since=since)

        if not posts:
            return self.db.create_snapshot(topic_id, {
                "post_count": 0,
                "engagement_sum": 0,
                "avg_sentiment": 0.0,
                "top_keywords": [],
                "volume_trend": "stable",
                "summary": "无新数据",
            })

        post_count = len(posts)
        engagement_sum = sum(
            int(p.get("likes") or 0) + int(p.get("comments") or 0) + int(p.get("shares") or 0)
            for p in posts
        )

        sentiment_scores = {"positive": 1, "neutral": 0, "negative": -1}
        avg_sentiment = (
            sum(sentiment_scores.get(str(p.get("sentiment") or "neutral").lower(), 0) for p in posts)
            / len(posts)
        )

        last_snapshot = self.db.get_latest_snapshot(topic_id)
        if last_snapshot:
            last_count = int(last_snapshot.get("post_count") or 0)
            if last_count <= 0:
                volume_trend = "up"
            elif post_count > last_count * 1.5:
                volume_trend = "up"
            elif post_count < last_count * 0.5:
                volume_trend = "down"
            else:
                volume_trend = "stable"
        else:
            volume_trend = "stable"

        all_content = " ".join(
            f"{p.get('title','')} {p.get('content','')}" for p in posts
        )
        top_keywords = self._extract_keywords(all_content, top_n=12)

        snapshot_data = {
            "post_count": post_count,
            "engagement_sum": engagement_sum,
            "avg_sentiment": round(avg_sentiment, 3),
            "top_keywords": top_keywords,
            "volume_trend": volume_trend,
            "summary": f"近 {len(posts)} 条帖子，总互动 {engagement_sum}，情感 {round(avg_sentiment,3)}",
        }
        return self.db.create_snapshot(topic_id, snapshot_data)

    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        if not text or not text.strip():
            return []
        raw = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
        words = [w.strip() for w in jieba.lcut(raw) if len(w.strip()) > 1]
        freq: Dict[str, int] = {}
        for word in words:
            if word.isdigit():
                continue
            freq[word] = freq.get(word, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda item: (-item[1], item[0]))
        return [word for word, _ in sorted_words[:top_n]]

    def _check_alerts(self, topic_id: str, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        existing = self.db.list_alerts(topic_id=topic_id, is_resolved=False, limit=50)

        def can_emit(alert_type: str) -> bool:
            if not existing:
                return True
            cutoff = datetime.utcnow() - timedelta(hours=self.config.alert_cooldown_hours)
            for alert in existing:
                if str(alert.get("alert_type") or "") != alert_type:
                    continue
                created_at = alert.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    except Exception:
                        created_at = None
                if isinstance(created_at, datetime) and created_at >= cutoff:
                    return False
            return True

        if snapshot.get("volume_trend") == "up" and can_emit("volume_spike"):
            alerts.append(self.db.create_alert(
                topic_id=topic_id,
                alert_type="volume_spike",
                title="话题热度上升",
                message=f"当前帖子数量显著增加：{snapshot.get('post_count')} 条，趋势：{snapshot.get('volume_trend')}",
                severity="warning",
            ))

        if int(snapshot.get("engagement_sum") or 0) >= self.config.viral_threshold and can_emit("viral_content"):
            alerts.append(self.db.create_alert(
                topic_id=topic_id,
                alert_type="viral_content",
                title="发现高互动内容",
                message=f"当前总互动量达到 {snapshot.get('engagement_sum')}，可能出现热点传播。",
                severity="info",
            ))

        if float(snapshot.get("avg_sentiment") or 0.0) < -0.4 and can_emit("negative_sentiment"):
            alerts.append(self.db.create_alert(
                topic_id=topic_id,
                alert_type="negative_sentiment",
                title="舆情负面情绪偏高",
                message=f"平均情感分数 {snapshot.get('avg_sentiment')}，建议关注传播节奏与响应策略。",
                severity="warning",
            ))

        return alerts

    def get_topic_status(self, topic_id: str) -> Dict[str, Any]:
        topic = self.db.get_topic_by_id(topic_id)
        if not topic:
            return {"error": "话题不存在"}
        keywords = self.db.get_topic_keywords(topic_id)
        latest_snapshot = self.db.get_latest_snapshot(topic_id)
        alerts = self.db.list_alerts(topic_id=topic_id, is_resolved=False)
        linked_cases = self.db.get_linked_cases(topic_id=topic_id, min_score=0.1)
        return {
            "topic": topic,
            "keywords": keywords,
            "latest_snapshot": latest_snapshot,
            "active_alerts": alerts,
            "linked_cases": linked_cases,
        }

    def run_monitoring_cycle(
        self,
        topic_ids: List[str],
        search_func: Optional[SearchFunc] = None,
    ) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        for topic_id in topic_ids:
            keyword_records = self.db.get_topic_keywords(topic_id)
            keyword_list = [str(k.get("keyword") or "") for k in keyword_records if str(k.get("keyword") or "").strip()]
            if search_func:
                search_results = search_func(keyword_list, topic_id, len(results))
            else:
                search_results = []
            result = self.scan_topic(topic_id, search_results)
            results.append({"topic_id": topic_id, "snapshot": result["snapshot"], "alerts": result["alerts"]})
        return {"results": results}

    def generate_periodic_report(
        self,
        topic_id: str,
        period: str = "daily",
        output_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        status = self.get_topic_status(topic_id)
        if status.get("error"):
            raise ValueError(status["error"])
        topic = status["topic"]
        snapshots = self.db.get_snapshots(topic_id, limit=20)
        alerts = self.db.list_alerts(topic_id=topic_id, limit=20)
        cases = self.db.get_linked_cases(topic_id=topic_id, min_score=0.1)

        period_label = "日报" if period.lower() in ("daily", "day") else "周报" if period.lower() in ("weekly", "week") else period
        output_dir = output_dir or (Path(__file__).resolve().parents[1] / "topic_monitoring_reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{self._safe_filename(topic.get('name','topic'))}_{period_label}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"

        content = self._build_report_markdown(topic, snapshots, alerts, cases, period_label)
        report_path.write_text(content, encoding="utf-8")
        return {
            "topic_id": topic_id,
            "topic_name": topic.get("name"),
            "period": period_label,
            "report_path": str(report_path),
            "generated_at": datetime.utcnow().isoformat(),
        }

    def _safe_filename(self, text: str) -> str:
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(text or "")).strip("_")
        return safe[:64] or "topic_report"

    def _build_report_markdown(
        self,
        topic: Dict[str, Any],
        snapshots: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        cases: List[Dict[str, Any]],
        period_label: str,
    ) -> str:
        title = topic.get("name", "专题")
        lines: List[str] = [f"# {title} {period_label}报告", "", f"生成时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", ""]
        lines.append(f"- 专题领域：{topic.get('domain', '')}")
        lines.append(f"- 话题描述：{topic.get('description', '')}")
        lines.append(f"- 关键词：{', '.join(str(k.get('keyword') or '') for k in self.db.get_topic_keywords(topic.get('id')) if str(k.get('keyword') or '').strip())}")
        lines.append("")

        if snapshots:
            latest = snapshots[0]
            lines.extend([
                "## 最新快照",
                "",
                f"- 采集时间：{latest.get('created_at', '')}",
                f"- 帖子数：{latest.get('post_count', 0)}",
                f"- 互动总量：{latest.get('engagement_sum', 0)}",
                f"- 平均情感：{latest.get('avg_sentiment', 0.0)}",
                f"- 趋势：{latest.get('volume_trend', 'stable')}",
                f"- 关键词：{', '.join(latest.get('top_keywords') or [])}",
                f"- 摘要：{latest.get('summary', '')}",
                "",
            ])
        else:
            lines.extend(["## 最新快照", "", "- 无快照数据", ""])

        if alerts:
            lines.extend(["## 活动告警", ""])
            for alert in alerts[:10]:
                lines.extend([
                    f"- [{alert.get('severity', '').upper()}] {alert.get('title', '')}",
                    f"  - 类型：{alert.get('alert_type', '')}",
                    f"  - 时间：{alert.get('created_at', '')}",
                    f"  - 内容：{alert.get('message', '')}",
                    "",
                ])
        else:
            lines.extend(["## 活动告警", "", "- 暂无未解决告警", ""])

        if cases:
            lines.extend(["## 关联案例", ""])
            for case in cases[:6]:
                lines.extend([
                    f"- {case.get('case_title', '')}",
                    f"  - 领域：{case.get('case_domain', '')}",
                    f"  - 相关度：{case.get('relevance_score', 0.0)}",
                    f"  - 链接：{case.get('case_url', '')}",
                    "",
                ])
        else:
            lines.extend(["## 关联案例", "", "- 暂无关联案例", ""])

        lines.extend([
            "## 近期趋势结构",
            "",
        ])
        for snapshot in snapshots[:6]:
            lines.append(f"- {snapshot.get('created_at', '')} | 帖子 {snapshot.get('post_count', 0)} | 互动 {snapshot.get('engagement_sum', 0)} | 情感 {snapshot.get('avg_sentiment', 0.0)} | 趋势 {snapshot.get('volume_trend', '')}")
        lines.append("")
        return "\n".join(lines)


def create_demo_topic() -> Dict[str, Any]:
    pipeline = TopicMonitoringPipeline()
    return pipeline.create_topic(
        name="高铁舆情",
        domain="交通",
        keywords=["高铁", "动车", "铁路服务", "乘客权益", "列车"] ,
        description="高铁舆情专题监测，覆盖客运服务、投诉与安全议题。",
    )


def _mock_high_speed_rail_search(keyword_list: List[str], topic_id: str, cycle: int = 0) -> List[Dict[str, Any]]:
    count = 4 + cycle * 3
    results: List[Dict[str, Any]] = []
    for idx in range(count):
        sentiment = "negative" if idx % 3 == 0 else "neutral"
        results.append({
            "id": f"{topic_id}-mock-{cycle}-{idx}",
            "url": f"https://example.com/highspeed/{cycle}/{idx}",
            "platform": "微博" if idx % 2 == 0 else "小红书",
            "author": f"用户{idx}",
            "title": f"高铁服务争议示例 {idx}",
            "content": f"高铁服务质量和候车环境收到大量讨论，关键词：{', '.join(keyword_list[:3])}",
            "likes": 18 + idx * 3,
            "comments": 5 + idx,
            "shares": 2 + idx,
            "sentiment": sentiment,
            "tags": ["投诉", "服务"],
            "metadata": {"cycle": cycle},
        })
    return results


def run_high_speed_rail_demo(
    search_func: Optional[SearchFunc] = None,
    cycles: int = 2,
    interval_minutes: int = 1,
) -> Dict[str, Any]:
    pipeline = TopicMonitoringPipeline()
    topic = create_demo_topic()
    search_func = search_func or _mock_high_speed_rail_search
    for cycle in range(cycles):
        _ = pipeline.scan_topic(topic["id"], search_func(["高铁", "动车"], topic["id"], cycle))
    report = pipeline.generate_periodic_report(topic["id"], period="daily")
    return {"topic": topic, "report": report}


if __name__ == "__main__":
    try:
        demo = run_high_speed_rail_demo()
        print("高铁舆情示例专题已部署，报告路径：", demo["report"]["report_path"])
    except Exception as exc:
        print("运行示例失败，请先配置 Supabase/Postgres：", exc)
