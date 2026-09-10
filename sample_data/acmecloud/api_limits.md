# AcmeCloud API Reliability Guide

## Authentication
API clients authenticate with bearer tokens. Tokens should be scoped to the minimum required permissions. A token can be revoked immediately from the administration console or through the token management API.

## Default rate limits
Starter workspaces allow 60 requests per minute per workspace. Business workspaces allow 300 requests per minute. Enterprise limits are negotiated in the customer contract. The API returns HTTP 429 when a rate limit is exceeded.

## Retry policy
Clients should retry HTTP 429 and transient 5xx responses with exponential backoff and jitter. The Retry-After header should be honored when present. AcmeCloud recommends a maximum of five retries for interactive workloads.

## Idempotency
Create and mutation endpoints accept the Idempotency-Key header. The same key is retained for 24 hours. Repeating a request with the same key and body returns the original successful result. Reusing a key with a different request body returns HTTP 409.

## Timeouts
Interactive API clients should use a connection timeout of 5 seconds and an overall request timeout of 30 seconds. Bulk export jobs are asynchronous and are not subject to the 30-second interactive request timeout.
