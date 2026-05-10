"""Workflow package.

This package will gradually host the modularized workflow implementation.
"""

from workflow.supabase_client import SupabaseDB, get_db
from workflow.topic_monitoring_pipeline import (
    TopicMonitoringPipeline,
    create_demo_topic,
    run_high_speed_rail_demo,
)

