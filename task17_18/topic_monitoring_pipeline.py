"""
话题监控流水线
Task 17+18: 实现基于 Supabase 的话题监控和告警系统
"""
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from workflow.supabase_client import SupabaseDB, get_db


@dataclass
class MonitorConfig:
    """监控配置"""
    scan_interval_minutes: int = 60        # 扫描间隔（分钟）
    min_posts_for_trend: int = 10          # 计算趋势所需最少帖子数
    viral_threshold: int = 1000            # 病毒式传播阈值
    alert_cooldown_hours: int = 24         # 告警冷却时间（小时）
    snapshot_interval_hours: int = 6        # 快照间隔（小时）


@dataclass
class TopicMonitor:
    """话题监控器"""
    topic_id: str
    name: str
    domain: str
    keywords: List[Dict[str, str]] = field(default_factory=list)
    config: MonitorConfig = field(default_factory=MonitorConfig)


class TopicMonitoringPipeline:
    """话题监控流水线"""
    
    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()
        self.config = MonitorConfig()
    
    def create_topic(
        self,
        name: str,
        domain: str,
        keywords: List[str],
        description: str = ""
    ) -> Dict[str, Any]:
        """创建监控话题"""
        # 1. 创建话题
        topic = self.db.create_monitor_topic(
            name=name,
            domain=domain,
            description=description
        )
        topic_id = topic["id"]
        
        # 2. 添加关键词
        keyword_records = [
            {"keyword": kw, "keyword_type": "include", "weight": 1.0}
            for kw in keywords
        ]
        self.db.add_topic_keywords(topic_id, keyword_records)
        
        # 3. 初始化快照
        self.db.create_snapshot(topic_id, {
            "post_count": 0,
            "engagement_sum": 0,
            "avg_sentiment": 0.0,
            "top_keywords": [],
            "volume_trend": "stable",
            "summary": "话题初始化"
        })
        
        return topic
    
    def scan_topic(
        self,
        topic_id: str,
        search_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """扫描话题并收集数据"""
        # 1. 批量收集帖子
        if search_results:
            posts = []
            for item in search_results:
                posts.append({
                    "post_id": item.get("id", ""),
                    "post_url": item.get("url", ""),
                    "platform": item.get("platform", "unknown"),
                    "author": item.get("author", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "likes": item.get("likes", 0),
                    "comments": item.get("comments", 0),
                    "shares": item.get("shares", 0),
                    "sentiment": item.get("sentiment", "neutral"),
                    "tags": item.get("tags", [])
                })
            self.db.bulk_collect_posts(topic_id, posts)
        
        # 2. 生成快照
        snapshot = self._generate_snapshot(topic_id)
        
        # 3. 检查告警
        self._check_alerts(topic_id, snapshot)
        
        return snapshot
    
    def _generate_snapshot(self, topic_id: str) -> Dict[str, Any]:
        """生成话题快照"""
        # 获取过去一段时间的帖子
        since = datetime.utcnow() - timedelta(hours=self.config.snapshot_interval_hours)
        posts = self.db.get_collected_posts(topic_id, limit=500, since=since)
        
        if not posts:
            return {"post_count": 0, "message": "无新数据"}
        
        # 计算统计数据
        post_count = len(posts)
        engagement_sum = sum(p.get("likes", 0) + p.get("comments", 0) + p.get("shares", 0) for p in posts)
        
        # 情感统计
        sentiments = [p.get("sentiment", "neutral") for p in posts]
        sentiment_scores = {"positive": 1, "neutral": 0, "negative": -1}
        avg_sentiment = sum(sentiment_scores.get(s, 0) for s in sentiments) / len(sentiments) if sentiments else 0
        
        # 获取前一次快照进行趋势比较
        last_snapshot = self.db.get_latest_snapshot(topic_id)
        if last_snapshot:
            last_count = last_snapshot.get("post_count", 0)
            if post_count > last_count * 1.5:
                volume_trend = "up"
            elif post_count < last_count * 0.5:
                volume_trend = "down"
            else:
                volume_trend = "stable"
        else:
            volume_trend = "stable"
        
        # 提取热词
        all_content = " ".join(p.get("title", "") + " " + p.get("content", "") for p in posts)
        top_keywords = self._extract_keywords(all_content, top_n=10)
        
        snapshot_data = {
            "post_count": post_count,
            "engagement_sum": engagement_sum,
            "avg_sentiment": avg_sentiment,
            "top_keywords": top_keywords,
            "volume_trend": volume_trend,
            "summary": f"共收集 {post_count} 条帖子，总互动 {engagement_sum}"
        }
        
        return self.db.create_snapshot(topic_id, snapshot_data)
    
    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """简单提取关键词（实际可用 jieba 等分词库）"""
        # 简单实现：按空格分词，统计频率
        words = text.split()
        word_freq = {}
        for word in words:
            if len(word) > 1:
                word_freq[word] = word_freq.get(word, 0) + 1
        
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [w[0] for w in sorted_words[:top_n]]
    
    def _check_alerts(self, topic_id: str, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """检查并生成告警"""
        alerts = []
        
        # 检查帖子数量激增
        if snapshot.get("volume_trend") == "up":
            alerts.append(self.db.create_alert(
                topic_id=topic_id,
                alert_type="volume_spike",
                title="话题热度上升",
                message=f"帖子数量显著增加，当前 {snapshot.get('post_count')} 条",
                severity="warning"
            ))
        
        # 检查高互动内容
        if snapshot.get("engagement_sum", 0) > self.config.viral_threshold:
            alerts.append(self.db.create_alert(
                topic_id=topic_id,
                alert_type="viral_content",
                title="发现高互动内容",
                message=f"总互动量达到 {snapshot.get('engagement_sum')}",
                severity="info"
            ))
        
        return alerts
    
    def get_topic_status(self, topic_id: str) -> Dict[str, Any]:
        """获取话题状态"""
        topic = self.db.client.table("monitor_topics").select("*").eq("id", topic_id).execute().data
        if not topic:
            return {"error": "话题不存在"}
        
        topic = topic[0]
        keywords = self.db.get_topic_keywords(topic_id)
        latest_snapshot = self.db.get_latest_snapshot(topic_id)
        alerts = self.db.list_alerts(topic_id, is_resolved=False)
        
        return {
            "topic": topic,
            "keywords": keywords,
            "snapshot": latest_snapshot,
            "active_alerts": alerts
        }
    
    def run_monitoring_cycle(
        self,
        topic_ids: List[str],
        search_func=None  # 用户提供搜索函数
    ) -> Dict[str, Any]:
        """运行监控周期"""
        results = []
        
        for topic_id in topic_ids:
            # 获取话题关键词
            keywords = self.db.get_topic_keywords(topic_id)
            keyword_list = [kw["keyword"] for kw in keywords]
            
            # 执行搜索（用户需要提供搜索实现）
            if search_func:
                search_results = search_func(keyword_list)
            else:
                search_results = []
            
            # 扫描话题
            snapshot = self.scan_topic(topic_id, search_results)
            results.append({
                "topic_id": topic_id,
                "snapshot": snapshot
            })
        
        return {"results": results}


def create_demo_topic():
    """创建演示话题"""
    pipeline = TopicMonitoringPipeline()
    
    return pipeline.create_topic(
        name="AI人工智能",
        domain="科技",
        keywords=["AI", "人工智能", "大模型", "ChatGPT", "Grok"],
        description="监控 AI 相关话题热度"
    )


if __name__ == "__main__":
    # 测试创建话题
    try:
        topic = create_demo_topic()
        print(f"创建成功: {topic['id']}")
    except Exception as e:
        print(f"需要先配置 Supabase: {e}")