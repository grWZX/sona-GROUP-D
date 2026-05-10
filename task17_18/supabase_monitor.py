"""
Supabase 话题监控工具
Task 17+18: 提供话题创建、监控、告警等工具
"""
from typing import Any, Dict, List, Optional
from workflow.supabase_client import SupabaseDB, get_db
from workflow.topic_monitoring_pipeline import TopicMonitoringPipeline, create_demo_topic


def supabase_init(
    url: str,
    key: str,
    schema_sql: str = ""
) -> Dict[str, Any]:
    """
    初始化 Supabase 连接并创建表结构
    
    Args:
        url: Supabase 项目 URL
        key: Supabase anon public key
        schema_sql: 可选的建表 SQL（如果数据库已有表可留空）
    
    Returns:
        初始化结果
    """
    import os
    os.environ["SUPABASE_URL"] = url
    os.environ["SUPABASE_KEY"] = key
    
    # 如果提供了 schema_sql，可以在这里执行
    if schema_sql:
        # 实际需要在 Supabase dashboard 的 SQL editor 中执行
        pass
    
    return {
        "status": "ok",
        "message": "Supabase 连接已配置，请前往 SQL Editor 执行 supabase_schema.sql"
    }


def create_topic(
    name: str,
    domain: str,
    keywords: List[str],
    description: str = ""
) -> Dict[str, Any]:
    """
    创建监控话题
    
    Args:
        name: 话题名称
        domain: 领域
        keywords: 关键词列表
        description: 描述
    
    Returns:
        创建的话题信息
    """
    pipeline = TopicMonitoringPipeline()
    topic = pipeline.create_topic(name, domain, keywords, description)
    return topic


def list_topics(
    is_active: Optional[bool] = None,
    domain: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取监控话题列表
    
    Args:
        is_active: 是否活跃
        domain: 领域筛选
    
    Returns:
        话题列表
    """
    db = get_db()
    topics = db.list_monitor_topics(is_active=is_active, domain=domain)
    return {"topics": topics, "count": len(topics)}


def get_topic_status(topic_id: str) -> Dict[str, Any]:
    """
    获取话题状态
    
    Args:
        topic_id: 话题 ID
    
    Returns:
        话题状态信息
    """
    pipeline = TopicMonitoringPipeline()
    return pipeline.get_topic_status(topic_id)


def list_alerts(
    topic_id: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    severity: Optional[str] = None
) -> Dict[str, Any]:
    """
    获取告警列表
    
    Args:
        topic_id: 话题 ID
        is_resolved: 是否已解决
        severity: 严重级别
    
    Returns:
        告警列表
    """
    db = get_db()
    alerts = db.list_alerts(topic_id=topic_id, is_resolved=is_resolved, severity=severity)
    return {"alerts": alerts, "count": len(alerts)}


def resolve_alert(alert_id: str) -> Dict[str, Any]:
    """
    解决告警
    
    Args:
        alert_id: 告警 ID
    
    Returns:
        处理结果
    """
    db = get_db()
    result = db.resolve_alert(alert_id)
    return {"status": "resolved", "alert": result}


def collect_posts(
    topic_id: str,
    posts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    手动收集帖子
    
    Args:
        topic_id: 话题 ID
        posts: 帖子列表
    
    Returns:
        收集结果
    """
    db = get_db()
    result = db.bulk_collect_posts(topic_id, posts)
    return {"collected": len(result)}


def create_snapshot(topic_id: str) -> Dict[str, Any]:
    """
    创建话题快照
    
    Args:
        topic_id: 话题 ID
    
    Returns:
        快照结果
    """
    db = get_db()
    # 获取近期帖子生成快照
    pipeline = TopicMonitoringPipeline()
    snapshot = pipeline._generate_snapshot(topic_id)
    return snapshot


__all__ = [
    "supabase_init",
    "create_topic",
    "list_topics",
    "get_topic_status",
    "list_alerts",
    "resolve_alert",
    "collect_posts",
    "create_snapshot",
]