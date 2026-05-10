"""
Supabase 数据库客户端模块
用于话题监控数据的存储和管理
"""
import os
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SupabaseConfig:
    """Supabase 配置"""
    url: str
    key: str
    
    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("请在 .env 中配置 SUPABASE_URL 和 SUPABASE_KEY")
        return cls(url=url, key=key)


class SupabaseDB:
    """Supabase 数据库操作类"""
    
    def __init__(self, config: Optional[SupabaseConfig] = None):
        self.config = config or SupabaseConfig.from_env()
        self.client: Client = create_client(self.config.url, self.config.key)
    
    # ============ Monitor Topics 表 ============
    
    def create_monitor_topic(
        self,
        name: str,
        domain: str,
        description: str = "",
        owner: str = "system"
    ) -> Dict[str, Any]:
        """创建监控话题"""
        data = {
            "name": name,
            "domain": domain,
            "description": description,
            "owner": owner,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        return self.client.table("monitor_topics").insert(data).execute().data[0]
    
    def list_monitor_topics(
        self,
        is_active: Optional[bool] = None,
        domain: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """获取监控话题列表"""
        query = self.client.table("monitor_topics").select("*")
        if is_active is not None:
            query = query.eq("is_active", is_active)
        if domain:
            query = query.eq("domain", domain)
        return query.execute().data
    
    def update_monitor_topic(
        self,
        topic_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """更新监控话题"""
        updates["updated_at"] = datetime.utcnow().isoformat()
        return self.client.table("monitor_topics").update(updates).eq("id", topic_id).execute().data[0]
    
    # ============ Topic Keywords 表 ============
    
    def add_topic_keywords(
        self,
        topic_id: str,
        keywords: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """添加话题关键词"""
        now = datetime.utcnow().isoformat()
        for kw in keywords:
            kw["topic_id"] = topic_id
            kw["created_at"] = now
        return self.client.table("topic_keywords").insert(keywords).execute().data
    
    def get_topic_keywords(self, topic_id: str) -> List[Dict[str, Any]]:
        """获取话题的关键词列表"""
        return self.client.table("topic_keywords").select("*").eq("topic_id", topic_id).execute().data
    
    def delete_topic_keyword(self, keyword_id: str) -> None:
        """删除关键词"""
        self.client.table("topic_keywords").delete().eq("id", keyword_id).execute()
    
    # ============ Collected Posts 表 ============
    
    def collect_post(
        self,
        topic_id: str,
        post_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """收集帖子"""
        data = {
            "topic_id": topic_id,
            **post_data,
            "collected_at": datetime.utcnow().isoformat()
        }
        return self.client.table("collected_posts").insert(data).execute().data[0]
    
    def bulk_collect_posts(
        self,
        topic_id: str,
        posts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """批量收集帖子"""
        now = datetime.utcnow().isoformat()
        for post in posts:
            post["topic_id"] = topic_id
            post["collected_at"] = now
        return self.client.table("collected_posts").insert(posts).execute().data
    
    def get_collected_posts(
        self,
        topic_id: str,
        limit: int = 100,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """获取收集的帖子"""
        query = self.client.table("collected_posts").select("*").eq("topic_id", topic_id)
        if since:
            query = query.gte("collected_at", since.isoformat())
        return query.order("collected_at", desc=True).limit(limit).execute().data
    
    # ============ Topic Snapshots 表 ============
    
    def create_snapshot(
        self,
        topic_id: str,
        snapshot_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建话题快照"""
        data = {
            "topic_id": topic_id,
            **snapshot_data,
            "created_at": datetime.utcnow().isoformat()
        }
        return self.client.table("topic_snapshots").insert(data).execute().data[0]
    
    def get_latest_snapshot(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """获取最新快照"""
        result = self.client.table("topic_snapshots").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(1).execute()
        return result.data[0] if result.data else None
    
    def get_snapshots(
        self,
        topic_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """获取历史快照"""
        return self.client.table("topic_snapshots").select("*").eq("topic_id", topic_id).order("created_at", desc=True).limit(limit).execute().data
    
    # ============ Alerts 表 ============
    
    def create_alert(
        self,
        topic_id: str,
        alert_type: str,
        title: str,
        message: str,
        severity: str = "info",  # info, warning, critical
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """创建告警"""
        data = {
            "topic_id": topic_id,
            "alert_type": alert_type,
            "title": title,
            "message": message,
            "severity": severity,
            "metadata": metadata or {},
            "is_resolved": False,
            "created_at": datetime.utcnow().isoformat()
        }
        return self.client.table("alerts").insert(data).execute().data[0]
    
    def list_alerts(
        self,
        topic_id: Optional[str] = None,
        is_resolved: Optional[bool] = None,
        severity: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取告警列表"""
        query = self.client.table("alerts").select("*")
        if topic_id:
            query = query.eq("topic_id", topic_id)
        if is_resolved is not None:
            query = query.eq("is_resolved", is_resolved)
        if severity:
            query = query.eq("severity", severity)
        return query.order("created_at", desc=True).limit(limit).execute().data
    
    def resolve_alert(self, alert_id: str) -> Dict[str, Any]:
        """解决告警"""
        return self.client.table("alerts").update({
            "is_resolved": True,
            "resolved_at": datetime.utcnow().isoformat()
        }).eq("id", alert_id).execute().data[0]
    
    # ============ Case Links 表 ============
    
    def link_case(
        self,
        topic_id: str,
        case_title: str,
        case_domain: str,
        case_url: str,
        relevance_score: float = 1.0,
        evidence: str = ""
    ) -> Dict[str, Any]:
        """关联案例"""
        data = {
            "topic_id": topic_id,
            "case_title": case_title,
            "case_domain": case_domain,
            "case_url": case_url,
            "relevance_score": relevance_score,
            "evidence": evidence,
            "linked_at": datetime.utcnow().isoformat()
        }
        return self.client.table("case_links").insert(data).execute().data[0]
    
    def get_linked_cases(
        self,
        topic_id: str,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """获取关联案例"""
        return self.client.table("case_links").select("*").eq("topic_id", topic_id).gte("relevance_score", min_score).order("relevance_score", desc=True).execute().data


def get_db() -> SupabaseDB:
    """获取数据库实例"""
    return SupabaseDB()