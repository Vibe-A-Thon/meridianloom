---
kind: skill
id: containers-and-kubernetes
name: Containers and Kubernetes
description: Image and workload practice for containerised services.
version: 1.0.0
tags: [docker, kubernetes, openshift, deployment]
---

# Containers and Kubernetes

## Images

- Pin base images by digest, not by a moving tag. `:latest` makes the build
  unreproducible and the rollback meaningless.
- Multi-stage: build tooling does not ship to production.
- Run as a non-root user, with a read-only root filesystem where the workload
  allows it.
- No secrets in layers. A deleted file in an earlier layer is still in the
  image.

## Workloads

- Set requests and limits. Without requests the scheduler is guessing; without
  limits one workload starves its neighbours.
- Liveness and readiness are different probes and must not be the same
  endpoint. A liveness probe that fails under load restarts a pod that was
  merely busy, which is how a slowdown becomes an outage.
- `terminationGracePeriodSeconds` long enough to drain, and the process must
  actually handle SIGTERM.
- `PodDisruptionBudget` for anything that needs a quorum.

## Config

- Config through env or mounted ConfigMaps; secrets through Secret objects,
  never baked in.
- A change to config is a change to the workload: version it and roll it the
  same way.
