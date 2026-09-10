# AcmeCloud Backup and Disaster Recovery

## Backups
Production databases are backed up continuously using incremental snapshots. A full recovery snapshot is verified every 24 hours. Backup data is encrypted separately from the primary production dataset.

## Recovery objectives
Starter has a target recovery point objective of 24 hours and a target recovery time objective of 24 hours. Business has an RPO of 4 hours and an RTO of 8 hours. Enterprise has a standard RPO of 1 hour and RTO of 4 hours. More stringent Enterprise objectives may be negotiated for dedicated deployments.

## Regional resilience
Business and Enterprise production services replicate critical metadata across availability zones within the selected region. Enterprise customers with an approved multi-region addendum can configure warm standby in a second geographic region.

## Restore requests
Workspace-level restores are initiated through support. Business restore requests are normally started within four hours. Enterprise restore requests receive a one-hour response target. Restores create a new recovery workspace before data is merged back into production.
