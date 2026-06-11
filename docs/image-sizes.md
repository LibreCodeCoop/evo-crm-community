# Image Footprint

This repository is a Docker-based stack. The table below gives a **rough
compressed size estimate** for each image the stack uses today.

The goal is to provide a practical footprint for planning pulls, local
development, and disk usage. Exact numbers vary by tag, architecture, and
upstream rebuilds.

## Estimated Sizes

| Image | Role | Estimated size |
| --- | --- | --- |
| `pgvector/pgvector:pg16` | PostgreSQL + pgvector database | `400-600 MB` |
| `redis:alpine` | Cache / job queue backend | `10-20 MB` |
| `evoapicloud/evo-auth-service-community:latest` | Auth service | `500-800 MB` |
| `evoapicloud/evo-ai-crm-community:latest` | Main CRM API | `600-900 MB` |
| `evoapicloud/evo-ai-core-service-community:latest` | Core service | `30-80 MB` |
| `evoapicloud/evo-ai-processor-community:latest` | Processor service | `200-350 MB` |
| `evoapicloud/evo-bot-runtime:latest` | Bot runtime | `25-80 MB` |
| `evoapicloud/evo-ai-frontend-community:latest` | Frontend bundle + nginx | `80-180 MB` |
| `nginx:alpine` | Gateway base image | `10-20 MB` |
| `python:3.11-alpine` | Journeys / segments mock services | `60-120 MB` each |

## Approximate Total

If you pull or build the whole stack, the rough footprint is:

- **without counting shared layers:** about `1.9-3.1 GB`
- **with shared layers deduplicated:** usually lower than that, depending on
  what is already cached locally

## Notes

- These are estimates for the currently referenced tags in
  [docker-compose.yml](../docker-compose.yml) and the local Dockerfiles.
- Local images can change size with any change to their build context.
- If you need exact numbers in a specific environment, inspect the images
  locally with `docker image inspect` after pulling or building them.

## Local Build Images

These images are built from the repository itself:

- [nginx/Dockerfile](../nginx/Dockerfile)
- [journeys-mock/Dockerfile](../journeys-mock/Dockerfile)
- [segments-mock/Dockerfile](../segments-mock/Dockerfile)

