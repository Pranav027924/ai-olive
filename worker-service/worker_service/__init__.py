"""worker-service — consumes inference_logs Redis Stream → Postgres (PRD §6.4).

Pipeline (PRD §6.4):

    XREADGROUP → parse LogEvent →
      IdempotencyChecker.exists(event_id)? → skip
      RedactionPipeline.redact(previews)
      CostCalculator.compute(event)
      Postgres tx: insert log → insert error if any
      XACK

ClickHouse buffered metrics writer lands in Phase 7.5.

Hexagonal layering (PRD §5.2):
- ``domain``         pure logic: ProcessedLog, RedactionPipeline,
                     IdempotencyChecker, CostCalculator.
- ``application``    ProcessLogEvent use case + LogRepository,
                     StreamConsumer, MetricsWriter ports.
- ``infrastructure`` PostgresLogRepository, RedisStreamConsumer,
                     regex / NER redactors.
- ``interfaces``     run_worker CLI entry point.
"""
