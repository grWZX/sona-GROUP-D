"""Task 17+18: 话题监控流水线兼示例演示"""

from workflow.topic_monitoring_pipeline import TopicMonitoringPipeline, create_demo_topic, run_high_speed_rail_demo


if __name__ == "__main__":
    try:
        demo = run_high_speed_rail_demo()
        print(f"高铁舆情专题连续监测示例已运行，报告路径：{demo['report']['report_path']}")
    except Exception as e:
        print(f"需要先配置 Supabase/Postgres: {e}")
