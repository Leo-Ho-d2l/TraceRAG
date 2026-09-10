# AcmeCloud Security Handbook

## Identity and access
AcmeCloud supports SAML 2.0 single sign-on on Business and Enterprise plans. Enterprise workspaces can also enforce SCIM-based user provisioning. Multi-factor authentication can be required for all workspace members on Business and Enterprise plans. Service accounts use scoped API tokens and cannot log in to the web console.

## Encryption
Customer data is encrypted in transit with TLS 1.2 or later and encrypted at rest with AES-256. Encryption keys are rotated at least once every 90 days. Enterprise customers may request customer-managed keys in supported regions.

## Audit logs
Business workspaces retain audit logs for 90 days. Enterprise workspaces retain audit logs for 365 days by default. Enterprise administrators can export audit events to an external SIEM using the audit log streaming integration.

## Data residency
Enterprise customers can select the primary data region when creating a workspace. Supported production regions are United States, European Union, Singapore, and Japan. Changing the primary region after workspace creation requires a migration coordinated with support.

## Incident response
Security incidents are triaged continuously. For confirmed incidents that materially affect customer data, AcmeCloud targets customer notification within 24 hours after confirmation. The incident response team maintains forensic evidence and a post-incident review for severe incidents.
