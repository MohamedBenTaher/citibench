# Citebench corpus manifest

Freeze date: **2026-09-05**

## Policy

Public Kubernetes concept documentation and public Microsoft Learn Azure
documentation only. No extra PDFs, no internal runbooks, no paywalled pages, no
customer data. C2 snapshots each pinned URL to `corpus/raw/<id>/` (HTML or PDF)
with a companion `sha256` file. Do not add documents that are not in this table.

## Re-freeze rule

A re-freeze requires all of: a new freeze date, a complete replacement of the
pinned URL list below, license re-check, and a `docs/decision-trail.tsv` row.
Do not silently swap a URL or version.

## Pinned documents (docs=14)

| id | title | source_url | version_or_snapshot | license | pages |
| --- | --- | --- | --- | --- | --- |
| k8s-deployments | Deployments | https://kubernetes.io/docs/concepts/workloads/controllers/deployment/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-pods | Pods | https://kubernetes.io/docs/concepts/workloads/pods/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-services | Service | https://kubernetes.io/docs/concepts/services-networking/service/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-configmaps | ConfigMaps | https://kubernetes.io/docs/concepts/configuration/configmap/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-secrets | Secrets | https://kubernetes.io/docs/concepts/configuration/secret/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-ingress | Ingress | https://kubernetes.io/docs/concepts/services-networking/ingress/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-scheduler | Kubernetes Scheduler | https://kubernetes.io/docs/concepts/scheduling-eviction/kube-scheduler/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| k8s-storage | Persistent Volumes | https://kubernetes.io/docs/concepts/storage/persistent-volumes/ | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-aks-intro | Introduction to Azure Kubernetes Service | https://learn.microsoft.com/en-us/azure/aks/intro-kubernetes | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-aks-concepts | AKS core concepts for clusters and workloads | https://learn.microsoft.com/en-us/azure/aks/concepts-clusters-workloads | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-aks-network | AKS networking concepts | https://learn.microsoft.com/en-us/azure/aks/concepts-network | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-blob-overview | Azure Blob Storage overview | https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blobs-overview | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-identity | Managed identities for Azure resources | https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview | snapshot-2026-09-05 | CC BY 4.0 | 1 |
| az-monitor | Azure Monitor overview | https://learn.microsoft.com/en-us/azure/azure-monitor/overview | snapshot-2026-09-05 | CC BY 4.0 | 1 |

Columns: `id`, `title`, `source_url`, `version_or_snapshot`, `license`, `pages`.
docs=14. pages=1 per HTML URL (`parse_doc`: one snapshot is one page).
