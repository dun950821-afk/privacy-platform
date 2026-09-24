# 检测引擎配置管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在检测引擎管理页为 Androguard、AppShark、MobSF 提供可持久化的全局配置、脱敏密钥、详细说明和可执行健康检查，并让 Worker 使用同一份配置。

**Architecture:** 新增 `engine_configs` 数据表和配置服务，普通配置与加密敏感配置分离。引擎注册表提供每个引擎的 schema、说明和默认值；列表、配置 CRUD、健康检查及 Worker 均通过配置服务解析配置并注入适配器。前端引擎卡片使用配置抽屉、动态字段 schema 和说明面板。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL JSONB、Pydantic、Vue 3、TypeScript、Element Plus、Pinia、pytest。

**Spec:** `docs/superpowers/specs/2026-09-23-engine-config-design.md`

## Global Constraints

- 仅覆盖当前注册的 `androguard`、`appshark`、`mobsf`；未实现的动态引擎不新增配置。
- 普通配置与敏感配置分开保存；API Key、Token、密码永不通过 API 返回明文。
- 空密钥字段表示保持原值；清除密钥必须通过显式操作。
- 配置保存后无需重启，列表、健康检查和 Worker 都读取数据库最新配置。
- 数据库迁移不得重复初始化已有业务数据，不修改既有任务配置结构。
- 所有路径、命名和用户界面文案遵循现有项目风格；错误必须区分不可达、认证失败和本地依赖缺失。

---

## 文件地图

- Create `backend/alembic/versions/<timestamp>_add_engine_configs.py`: `engine_configs` 表迁移。
- Modify `backend/app/models/__init__.py`: 添加 `EngineConfig` 模型。
- Create `backend/app/services/engine_config.py`: 默认值、schema、加密/脱敏、CRUD 和配置解析。
- Modify `backend/app/core/security.py`: 配置密钥加密与解密辅助函数。
- Modify `backend/app/core/security.py`: 新增 `engine:read/write/health-check` 权限映射。
- Modify `backend/app/engine/worker.py`: 注册表 schema/help metadata，加载配置并注入适配器。
- Modify `backend/app/engine/adapters/mobsf.py`: 使用配置 URL/API key，兼容当前 MobSF 路由并返回可诊断错误。
- Modify `backend/app/engine/adapters/appshark.py`: 接受数据库配置覆盖环境变量默认值。
- Modify `backend/app/engine/adapters/androguard.py`: 接受统一配置并使用解析超时。
- Modify `backend/app/api/v1/engines.py`: 配置 CRUD、重置、健康检查响应和说明字段。
- Modify `backend/app/api/v1/__init__.py` if router registration is needed.
- Create/modify `backend/tests/test_engine_config.py`: 配置模型、权限、脱敏、健康检查和适配器注入测试。
- Modify `frontend/src/api/engines.ts`: 配置 API 方法。
- Modify `frontend/src/views/Engines.vue`: 卡片配置按钮、动态配置抽屉、说明弹窗、状态消息。
- Modify `frontend/src/types` only if existing type organization requires engine interfaces.
- Modify `backend/requirements.txt` only if encryption dependency is absent; prefer existing `cryptography` transitively available through `python-jose` and document exact choice.

---

### Task 1: Add the persistent engine configuration model and migration

**Files:**
- Create: `backend/alembic/versions/<timestamp>_add_engine_configs.py`
- Modify: `backend/app/models/__init__.py` near `EngineExecution`
- Test: `backend/tests/test_engine_config.py`

**Interfaces:**
- Produces `EngineConfig` SQLAlchemy model with unique `engine_type`, `config_json`, `secret_json`, `enabled`, health fields, `updated_by`, and timestamps.
- Migration must be safe on an existing database and provide indexes/constraints for `engine_type` and health status.

- [ ] **Step 1: Write failing model/migration tests**

```python
def test_engine_config_has_unique_engine_type(db):
    first = EngineConfig(engine_type="mobsf", config_json={}, secret_json={})
    second = EngineConfig(engine_type="mobsf", config_json={}, secret_json={})
    db.add_all([first, second])
    with pytest.raises(IntegrityError):
        db.commit()


def test_engine_config_defaults_are_safe(db):
    row = EngineConfig(engine_type="androguard")
    db.add(row)
    db.commit()
    assert row.config_json == {}
    assert row.secret_json == {}
    assert row.enabled is True
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `cd backend && pytest tests/test_engine_config.py -q`
Expected: FAIL because `EngineConfig` and its table do not yet exist.

- [ ] **Step 3: Add the SQLAlchemy model**

Add a model matching the existing `Base`, `JSONB`, `utcnow`, BigInteger IDs, indexes, and naming conventions. Use `UniqueConstraint("engine_type")`; make `config_json` and `secret_json` non-null JSONB defaults of `{}`; make `enabled` default `True`; keep health message nullable.

- [ ] **Step 4: Add the Alembic migration**

Create the migration using the repository’s configured metadata/database URL. Add the table, unique constraint, health timestamp index, and a downgrade that drops the index/table. Do not insert seed data in the migration.

- [ ] **Step 5: Run model and migration tests**

Run: `cd backend && pytest tests/test_engine_config.py -q`
Expected: PASS for model constraints and defaults.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/__init__.py backend/alembic/versions backend/tests/test_engine_config.py
git commit -m "feat: add persistent engine config model"
```

---

### Task 2: Implement configuration service, secret protection, defaults, and permissions

**Files:**
- Create: `backend/app/services/engine_config.py`
- Modify: `backend/app/core/security.py`
- Modify: `backend/app/core/config.py` if an encryption key setting is needed
- Modify: `backend/app/core/security.py` role permissions
- Test: `backend/tests/test_engine_config.py`

**Interfaces:**
- `get_engine_definition(engine_type) -> dict`
- `get_or_create_engine_config(db, engine_type) -> EngineConfig`
- `public_engine_config(db, engine_type) -> dict`
- `save_engine_config(db, engine_type, ordinary: dict, secret_updates: dict, clear_secrets: list[str], user_id: int) -> EngineConfig`
- `resolved_engine_config(db, engine_type) -> dict`
- `redact_engine_config(config: dict) -> dict`
- `engine_secret_encrypt(value: str) -> str` and `engine_secret_decrypt(value: str) -> str`

- [ ] **Step 1: Write failing service tests**

```python
def test_secret_is_not_returned_in_public_config(db):
    save_engine_config(db, "mobsf", {"url": "http://127.0.0.1:8001"}, {"api_key": "real-key"}, [], 1)
    public = public_engine_config(db, "mobsf")
    assert public["secrets"]["api_key"]["configured"] is True
    assert "real-key" not in json.dumps(public)


def test_empty_secret_preserves_existing_secret(db):
    save_engine_config(db, "mobsf", {}, {"api_key": "old"}, [], 1)
    save_engine_config(db, "mobsf", {}, {"api_key": ""}, [], 1)
    assert resolved_engine_config(db, "mobsf")["api_key"] == "old"


def test_clear_secret_removes_it(db):
    save_engine_config(db, "mobsf", {}, {"api_key": "old"}, ["api_key"], 1)
    assert resolved_engine_config(db, "mobsf").get("api_key") in (None, "")
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `cd backend && pytest tests/test_engine_config.py -q`
Expected: FAIL because service and encryption functions are absent.

- [ ] **Step 3: Implement encryption and permissions**

Use a configured Fernet key from application settings; fail clearly at startup/configuration save if the key is missing rather than storing plaintext. Add `engine:read`, `engine:write`, and `engine:health-check` to the role permission map; keep `platform_admin` wildcard behavior.

- [ ] **Step 4: Implement registry-backed definitions and defaults**

Define field metadata for all three engines: field key, label, type, required, secret, default, placeholder, help text. Seed defaults on first read from current environment values (`MOBSF_URL`, AppShark paths/JVM options, Python executable and timeouts), without overwriting existing rows.

- [ ] **Step 5: Implement validation, save, resolve, public projection, and redaction**

Reject unknown fields, enforce URL scheme for MobSF, positive bounded timeouts, required AppShark paths, and secret update/clear semantics. Return ordinary values plus secret `{configured, masked}` metadata only.

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_engine_config.py -q`
Expected: PASS for encryption, defaults, validation, preservation, clearing, and redaction.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/engine_config.py backend/app/core/security.py backend/app/core/config.py backend/tests/test_engine_config.py
git commit -m "feat: add engine config service and secret protection"
```

---

### Task 3: Add engine configuration and health-check API endpoints

**Files:**
- Modify: `backend/app/api/v1/engines.py`
- Modify: `backend/app/schemas/__init__.py` if request/response schemas are colocated there
- Test: `backend/tests/test_engine_config_api.py`

**Interfaces:**
- `GET /api/v1/engines/{engine_type}/config`
- `PUT /api/v1/engines/{engine_type}/config`
- `POST /api/v1/engines/{engine_type}/config/reset`
- `POST /api/v1/engines/{engine_type}/health-check`

- [ ] **Step 1: Write failing API tests**

```python
def test_get_config_hides_secret(client, admin_headers):
    response = client.get("/api/v1/engines/mobsf/config", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["data"]["secrets"]["api_key"]["configured"] is False
    assert "value" not in response.json()["data"]["secrets"]["api_key"]


def test_put_config_and_health_check(client, admin_headers, monkeypatch):
    saved = client.put("/api/v1/engines/mobsf/config", headers=admin_headers, json={
        "config": {"url": "http://127.0.0.1:8001", "connect_timeout": 10, "scan_timeout": 300},
        "secrets": {"api_key": "secret"},
    })
    assert saved.status_code == 200
    assert "secret" not in saved.text


def test_config_write_requires_permission(client, tester_headers):
    assert client.put("/api/v1/engines/mobsf/config", headers=tester_headers, json={}).status_code == 403
```

- [ ] **Step 2: Run focused API tests to verify failure**

Run: `cd backend && pytest tests/test_engine_config_api.py -q`
Expected: FAIL because routes and permission dependencies are absent.

- [ ] **Step 3: Add request models and routes**

Validate engine type against the registry, inject current user, call service methods, and return the standard `{code, data, request_id}` response shape already used by the API. Add read/write/health permission dependencies separately. Reset should delete ordinary and secret values back to registered defaults, not drop the row.

- [ ] **Step 4: Refactor engine list and health check**

Include public config summary, field schema, help text, `last_health_*`, and detailed status/message in `GET /engines`. Health check must instantiate the adapter with resolved config, persist the result, and return `env_ready`, `status`, and `message`.

- [ ] **Step 5: Run tests and API smoke checks**

Run: `cd backend && pytest tests/test_engine_config_api.py -q`
Then: `curl -H 'Authorization: Bearer ...' http://127.0.0.1:8000/api/v1/engines/mobsf/config`
Expected: HTTP 200 with no secret plaintext.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/engines.py backend/app/schemas/__init__.py backend/tests/test_engine_config_api.py
git commit -m "feat: expose engine configuration APIs"
```

---

### Task 4: Make adapters and Worker consume resolved configuration

**Files:**
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/engine/adapters/mobsf.py`
- Modify: `backend/app/engine/adapters/appshark.py`
- Modify: `backend/app/engine/adapters/androguard.py`
- Test: `backend/tests/test_engine_adapters_config.py`

**Interfaces:**
- Each adapter constructor accepts `config: dict | None = None` while preserving no-argument compatibility for existing callers.
- `adapter.validate_environment() -> bool` remains compatible; add `last_error`/`last_message` for diagnostic output.
- Worker helper `build_engine_adapter(db, engine_type) -> EngineAdapter` resolves and injects current configuration.

- [ ] **Step 1: Write failing adapter injection tests**

```python
def test_mobsf_uses_configured_url_and_key(monkeypatch):
    adapter = MobSFAdapter({"url": "http://configured:8001", "api_key": "k"})
    assert adapter.mobsf_url == "http://configured:8001"
    assert adapter.api_key == "k"


def test_worker_builds_adapter_from_database(db):
    save_engine_config(db, "mobsf", {"url": "http://configured:8001"}, {"api_key": "k"}, [], 1)
    adapter = build_engine_adapter(db, "mobsf")
    assert adapter.mobsf_url == "http://configured:8001"
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `cd backend && pytest tests/test_engine_adapters_config.py -q`
Expected: FAIL because constructors and worker factory do not accept resolved configuration.

- [ ] **Step 3: Update constructors and environment checks**

MobSF must read `url`, `api_key`, and timeouts from the resolved config; check root/login reachability first, then authenticated API behavior, returning a diagnostic message for 401/403. AppShark must map configured paths/JVM/timeouts to existing command construction. Androguard must accept local Python/timeout fields without requiring an address.

- [ ] **Step 4: Update Worker paths**

Replace no-argument adapter construction in task processing, list, and health-check paths with the configuration-aware factory. Before execution, validate the resolved adapter; save a redacted config snapshot into `EngineExecution.config_json`; never log or persist secret plaintext.

- [ ] **Step 5: Run adapter and worker tests**

Run: `cd backend && pytest tests/test_engine_adapters_config.py -q`
Expected: PASS, including MobSF URL/key injection and redacted execution snapshot.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine backend/tests/test_engine_adapters_config.py
 git commit -m "feat: inject persisted config into detection engines"
```

---

### Task 5: Implement engine management card configuration UI

**Files:**
- Modify: `frontend/src/api/engines.ts`
- Modify: `frontend/src/views/Engines.vue`
- Test: existing frontend test setup or `frontend/src/views/Engines.spec.ts` if test tooling exists

**Interfaces:**
- API methods `getConfig(engineType)`, `saveConfig(engineType, payload)`, `resetConfig(engineType)`, and `healthCheck(engineType)`.
- UI consumes engine list `config_schema`, ordinary config values, secret status, `help`, and health message.

- [ ] **Step 1: Add API method tests or compile-time contract assertions**

```ts
expect(engineApi.getConfig('mobsf')).toBeDefined()
expect(engineApi.saveConfig('mobsf', { config: {}, secrets: {} })).toBeDefined()
expect(engineApi.resetConfig('mobsf')).toBeDefined()
```

- [ ] **Step 2: Run existing frontend checks before implementation**

Run: `cd frontend && npm run build`
Expected: current baseline passes; if no test script exists, use the build as the baseline contract.

- [ ] **Step 3: Add configuration API methods and state**

Add typed refs for `configDialogVisible`, selected engine, config form, secret status, schema, loading/saving/checking state, and help dialog. Load the selected engine configuration when opening the drawer.

- [ ] **Step 4: Add card actions and dynamic form**

Add `配置`, `环境检查`, and `说明` actions. Render fields by schema: URL/path/text/number/password; show required labels, placeholders, field help tooltips, and secret configured/masked status. Empty secret input preserves the stored value; expose an explicit clear control.

- [ ] **Step 5: Add save/reset/help/error interactions**

Save via API, show success message, refresh engine list and close drawer; reset with confirmation; health check displays returned diagnostic message; help dialog shows usage, dependencies, startup command, checks, common errors, and documentation link from backend metadata.

- [ ] **Step 6: Run frontend verification**

Run: `cd frontend && npm run build`
Expected: TypeScript/Vite build succeeds and the engine page contains the new actions without console errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/engines.ts frontend/src/views/Engines.vue
 git commit -m "feat: add engine configuration management UI"
```

---

### Task 6: End-to-end tests, migration run, and runtime verification

**Files:**
- Modify: `backend/tests/test_engine_config.py`, `backend/tests/test_engine_config_api.py`, `backend/tests/test_engine_adapters_config.py` only for discovered failures.
- Modify: `README.md` with exact configuration and startup notes.
- No production code changes unless a failing verification identifies a root cause.

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && pytest -q`
Expected: all existing and new tests pass.

- [ ] **Step 2: Apply migration against the current database**

Run the repository’s Alembic upgrade command from `backend` and inspect the resulting table/constraint. Do not run `init_db.py` or seed commands against the existing business database.

- [ ] **Step 3: Verify live API configuration flow**

Use the admin login, then:

```bash
curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/engines
curl -X PUT -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  http://127.0.0.1:8000/api/v1/engines/mobsf/config \
  -d '{"config":{"url":"http://127.0.0.1:8001","connect_timeout":10,"scan_timeout":300},"secrets":{}}'
curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/engines/mobsf/health-check
```

Expected: response contains the MobSF diagnostic status and never contains an API key value.

- [ ] **Step 4: Verify Worker and UI**

Restart only API/Worker if needed, submit or inspect a representative detection task, verify the Worker logs the registered engine and execution config is redacted, then open `http://172.16.105.2:5173/` and confirm all three cards show configuration/help actions and MobSF shows a specific readiness message.

- [ ] **Step 5: Run final checks and commit documentation**

Run: `git diff --check` and `cd frontend && npm run build`.

```bash
git add README.md backend/tests
 git commit -m "docs: document engine configuration and verification"
```

## Self-review coverage

- Database persistence and migration: Task 1.
- Secret encryption, redaction, defaults, validation: Task 2.
- CRUD/reset/health APIs and permissions: Task 3.
- Adapter, health-check, Worker and execution snapshot integration: Task 4.
- Card configuration, help button, field-specific forms and status refresh: Task 5.
- Tests, migration safety, live verification and documentation: Task 6.

No placeholders or undefined cross-task interfaces remain; Task 2 defines service names used by Tasks 3–4, and Task 4 defines the adapter factory consumed by Worker tests.
