# Citebench corpus-v0 manifest

Freeze date: **2026-09-10**

This is the small, committed **smoke corpus**: the original 14 Kubernetes and
Azure pages, snapshotted offline under `corpus/v0/raw/`. It is selected with
`CITEBENCH_MANIFEST=corpus/v0/MANIFEST.md` and ingested with
`CITEBENCH_SNAPSHOT_ONLY=1` (no network). It is immutable: do not add or replace
rows to support new work. The growing freeze lives in `corpus/MANIFEST.md`.

## Policy

Public Kubernetes concept documentation and public Microsoft Learn Azure
documentation only. No extra PDFs, no internal runbooks, no paywalled pages, no
customer data. Each snapshot lives in `corpus/v0/raw/<id>/` (HTML) with a
companion `sha256` and `meta.json`.

## Re-freeze rule

Do not re-freeze this directory. corpus-v0 exists to keep the smoke loop fast
and stable while the big freeze grows.

## Pinned documents (docs=14)

| id | title | source_url | version_or_snapshot | license | pages |
| --- | --- | --- | --- | --- | --- |
| k8s-deployments | Deployments | https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-pods | Pods | https://kubernetes.io/docs/concepts/workloads/pods/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-services | Service | https://kubernetes.io/docs/concepts/services-networking/service/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-configmaps | ConfigMaps | https://kubernetes.io/docs/concepts/configuration/configmap/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-secrets | Secrets | https://kubernetes.io/docs/concepts/configuration/secret/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-ingress | Ingress | https://kubernetes.io/docs/concepts/services-networking/ingress/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-scheduler | Kubernetes Scheduler | https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| k8s-storage | Persistent Volumes | https://kubernetes.io/docs/concepts/storage/persistent-volumes/ | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-aks-intro | Introduction to Azure Kubernetes Service | https://learn.microsoft.com/en-us/azure/aks/intro-kubernetes | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-aks-concepts | AKS core concepts for clusters and workloads | https://learn.microsoft.com/en-us/azure/aks/concepts-clusters-workloads | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-aks-network | AKS networking concepts | https://learn.microsoft.com/en-us/azure/aks/concepts-network | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-blob-overview | Azure Blob Storage overview | https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-overview | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-identity | Managed identities for Azure resources | https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview | v0-2026-09-10 | CC BY 4.0 | 1 |
| az-monitor | Azure Monitor overview | https://learn.microsoft.com/en-us/azure/azure-monitor/overview | v0-2026-09-10 | CC BY 4.0 | 1 |

Columns: `id`, `title`, `source_url`, `version_or_snapshot`, `license`, `pages`.
docs=14. pages=1 per HTML snapshot.
