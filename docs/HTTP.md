# 接口

- `GET /`：工作台。
- `GET /api/catalog`：阶段、字段和样例。
- `POST /api/stages/{stage}`：按阶段返回处理结果。
- `POST /api/runs`：执行完整批次并保存草稿。
- `GET /api/runs/{id}`：读取批次。
- `POST /api/runs/{id}/review`：签发或暂缓，提交 `decision`、`comment`、`expected_revision`。
- `GET /api/runs/{id}/evidence`：下载已签发证据。
- `GET /api/runs/{id}/specimens`：批次内各标本的复核状态、版本与凭据标记。
- `POST /api/runs/{id}/specimens/{specimen_id}/review`：单条复核，提交 `expected_revision`、`comment`。
- `POST /api/runs/{id}/specimens/{specimen_id}/correct`：更正单条标本，提交 `expected_revision` 与完整 `corrected` 记录；读数或判定变化时原复核失效。
- `POST /api/runs/{id}/specimens/{specimen_id}/credential`：签发确认凭据（幂等，重试原样返回）。
- `GET /api/runs/{id}/specimens/{specimen_id}/credential`：读取已留存的确认凭据。
- `GET /api/examples/{profile}`：下载样例。
- `GET /healthz`：健康检查。

## 确认流程状态

- 标本状态为 `PENDING`（待复核）或 `REVIEWED`（已复核），每条标本独立维护 `revision`。
- 更正与签发都带 `expected_revision`；版本过时返回 `STALE_REVIEW(409)`，复核已失效返回 `NOT_REVIEWED(409)`。
- 更正后换算读数与危急判定都不变时保留 `REVIEWED`；任一项变化回到 `PENDING`，须重新复核。
- 凭据签发后原样留存，重复签发返回同一凭据；已签发标本的更正与复核返回 `CREDENTIAL_SEALED(409)`。
