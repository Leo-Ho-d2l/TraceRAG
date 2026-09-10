# AcmeCloud Operations and Observability

## Service metrics
The administration console exposes request volume, error rate, p50 latency, p95 latency, and background job backlog. Metrics are retained for 30 days on Business and 90 days on Enterprise.

## Application logs
Business stores application logs for 14 days. Enterprise stores application logs for 30 days. Logs can be exported continuously to supported external observability platforms on Enterprise.

## Tracing
Enterprise customers can enable distributed trace export using OpenTelemetry Protocol. Trace export includes request identifiers and service spans but excludes document content by default. Sampling is configurable between 1 percent and 100 percent.

## Availability targets
The Business service target is 99.9 percent monthly availability. Enterprise has a standard 99.95 percent monthly service-level objective. Dedicated Enterprise deployments may have a separately negotiated availability objective.

## Alerting
Business supports email alerts. Enterprise supports email, webhook, and pager integrations. Alert rules can use error rate, latency, or background queue thresholds.
