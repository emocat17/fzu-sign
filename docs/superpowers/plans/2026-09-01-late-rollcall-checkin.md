# 晚点名签到配置脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在项目根目录提供 `late_rollcall_checkin.py` 和 `late_rollcall_config.json`，脚本读取 JSON 中的登录态、服务信息和签到请求模板，在 dry-run 下审阅请求，显式 `--send` 后才向用户有权限的服务发送签到请求。

**Architecture:** Python 标准库脚本负责加载/校验配置、递归替换 `${...}` 占位符、拼接 URL、打印脱敏请求和执行一次 HTTP 请求。JSON 分为已确认的 App 入口/服务深链、可选服务目录请求、登录态和签到请求四块；APK 未包含“晚点名签到”远程页面，因此真实提交 URL/body 不硬编码猜测，而由用户从自有账号的请求记录填入。

**Tech Stack:** Python 3.11+；标准库 `json`、`argparse`、`urllib.request`、`string.Template`、`datetime`；测试使用 `unittest`，不依赖第三方包。

**Spec:** 本轮聊天中用户批准的配置驱动方案；静态证据记录在 `findings.md`。

## Global Constraints

- 根目录交付文件固定为 `late_rollcall_checkin.py` 和 `late_rollcall_config.json`。
- 脚本默认 dry-run；只有显式 `--send` 才允许真实 HTTP 发送。
- JSON 中的 token、密码、Cookie 和个人字段使用空值/说明性值，不写入真实凭证。
- 不绕过服务端时间、定位、设备、签名或风控校验；未知校验必须让服务返回错误并打印可审计结果。
- 已确认 scheme 为 `kysk-fdxy-app`，公开 H5 入口为 `https://app.fzu.edu.cn/fd-app/m/index.html`；这些不是签到提交 URL。
- 已确认服务相关字段候选为 `serviceId`、`serviceName`、`serviceUrl`、`urlType`、`pageType`、`scheme`、`appId`、`userId`、`orgId`、`deviceId`、`latitude`、`longitude`、`timestamp`、`appToken`、`loginToken`、`accountToken`；脚本只发送 JSON 中实际配置的字段。

### Task 1: 配置模型、校验与请求渲染

**Files:**
- Create: `analysis/test_late_rollcall_checkin.py`
- Create: `late_rollcall_checkin.py`

**Interfaces:**
- `load_config(path: Path) -> dict`
- `render_value(value: Any, context: Mapping[str, Any]) -> Any`
- `build_request(config: Mapping[str, Any]) -> urllib.request.Request`
- `redact_config(config: Mapping[str, Any]) -> dict`

- [x] **Step 1: Write the failing test**

  Add `analysis/test_late_rollcall_checkin.py` with these concrete behaviors:

  ```python
  class ConfigAndRequestTests(unittest.TestCase):
      def test_renders_nested_body_and_headers_from_json_context(self):
          config = {
              "request": {
                  "url": "https://example.invalid/check/${service.service_id}",
                  "method": "POST",
                  "headers": {"token": "${auth.token}"},
                  "body": {"userId": "${identity.user_id}", "latitude": "${location.latitude}"},
              },
              "auth": {"token": "token-value"},
              "identity": {"user_id": "u-1"},
              "location": {"latitude": 26.06},
              "service": {"service_id": "svc-1"},
          }
          request = build_request(config)
          self.assertEqual(request.full_url, "https://example.invalid/check/svc-1")
          self.assertEqual(request.get_header("Token"), "token-value")
          self.assertEqual(json.loads(request.data), {"userId": "u-1", "latitude": 26.06})

      def test_dry_run_does_not_require_send_permission(self):
          config = {"request": {"url": "https://example.invalid", "method": "POST", "body": {}}}
          self.assertFalse(should_send(config, send_flag=False))

      def test_send_requires_explicit_flag_and_nonempty_endpoint(self):
          config = {"request": {"url": "https://example.invalid", "method": "POST", "body": {}}}
          self.assertTrue(should_send(config, send_flag=True))
          config["request"]["url"] = ""
          with self.assertRaises(ValueError):
              should_send(config, send_flag=True)
  ```

- [x] **Step 2: Run test to verify it fails**

  Run: `C:\ProgramData\chocolatey\bin\python3.11.exe -m unittest discover -s analysis -p "test_late_rollcall_checkin.py" -v`

  Expected: FAIL because `late_rollcall_checkin.py` and its request helpers do not exist.

- [x] **Step 3: Write minimal implementation**

  Implement only the loader, recursive renderer, request builder, redaction helper, `should_send`, CLI parser, and a `main()` that loads `late_rollcall_config.json`. Support string paths such as `${auth.token}` and preserve numeric JSON values unless a placeholder substitution necessarily produces text. Require `request.url`, allow only `GET`, `POST`, `PUT`, or `PATCH`, encode JSON bodies as UTF-8, and set `Content-Type: application/json` when a body exists.

- [x] **Step 4: Run test to verify it passes**

  Run the same unittest command. Expected: all tests PASS with no network call.

### Task 2: Root JSON with URL and field inventory

**Files:**
- Create: `late_rollcall_config.json`
- Modify: `late_rollcall_checkin.py`
- Test: `analysis/test_late_rollcall_checkin.py`

**Interfaces:**
- JSON sections consumed by the script: `app`, `service_discovery`, `auth`, `identity`, `location`, `service`, `request`.
- The `request` section is the only section allowed to cause a send; `service_discovery` is optional and defaults to disabled.

- [x] **Step 1: Write the failing test**

  Add tests that load the root JSON and assert it contains:

  ```python
  self.assertEqual(config["app"]["scheme"], "kysk-fdxy-app")
  self.assertEqual(config["app"]["public_h5_url"], "https://app.fzu.edu.cn/fd-app/m/index.html")
  self.assertIn("serviceId", config["service"]["known_field_candidates"])
  self.assertIn("latitude", config["location"]["known_field_candidates"])
  self.assertFalse(config["request"]["enabled"])
  ```

- [x] **Step 2: Run test to verify it fails**

  Run the focused unittest. Expected: FAIL because the root JSON does not exist.

- [x] **Step 3: Write minimal implementation/configuration**

  Add the root JSON with:

  - `app.public_h5_url = https://app.fzu.edu.cn/fd-app/m/index.html`.
  - `app.scheme = kysk-fdxy-app`.
  - `app.service_deep_link = kysk-fdxy-app://third_service?serviceId=${service.service_id}`.
  - `service_discovery` disabled and labeled as a candidate-only section for `/operation/service/app/v1/getMyHomeService`, `/operation/service/app/v1/getPageService`, `/operation/service/app/v1/getServiceListByGroupType`, and `/operation/service/app/v1/selectServiceByGroupId`; the JSON must not claim these are the check-in submit URL.
  - `auth`, `identity`, `location`, and `service` fields with empty values and comments-as-keys explaining the source/meaning.
  - `request.enabled = false`, an empty URL, method `POST`, empty headers/body, and a `field_inventory` list separating `confirmed_in_apk`, `service_metadata_candidates`, and `needs_capture_confirmation`.

  The script must refuse `--send` while `request.enabled` is false or the URL is empty, and show the exact reason.

- [x] **Step 4: Run test to verify it passes**

  Run the focused unittest and a dry-run:

  `C:\ProgramData\chocolatey\bin\python3.11.exe late_rollcall_checkin.py`

  Expected: tests PASS; dry-run prints the known URLs and a redacted message that the real check-in request is not configured, without network access.

### Task 3: Verification and handoff

**Files:**
- Modify: `late_rollcall_checkin.py`
- Modify: `late_rollcall_config.json`
- Modify: `analysis/test_late_rollcall_checkin.py`
- Modify: `findings.md`
- Modify: `progress.md`
- Modify: `task_plan.md`

**Interfaces:**
- CLI: `python late_rollcall_checkin.py` for dry-run; `python late_rollcall_checkin.py --send` for an explicitly enabled configured request; `--config PATH` for another JSON file.

- [x] **Step 1: Write the failing test**

  Add tests for redaction of keys containing `token`, `password`, `cookie`, or `authorization`, and for HTTP error bodies being reported without printing secret headers.

- [x] **Step 2: Run test to verify it fails**

  Run the full unittest command and confirm the new assertions fail before the implementation change.

- [x] **Step 3: Write minimal implementation**

  Add redaction and error handling; keep response output bounded, print status and parsed JSON when possible, and never print raw secret-bearing headers. Keep the config disabled until the actual self-owned service request is supplied.

- [x] **Step 4: Run test to verify it passes**

  Run:

  ```text
  C:\ProgramData\chocolatey\bin\python3.11.exe -m unittest discover -s analysis -p "test_late_rollcall_checkin.py" -v
  C:\ProgramData\chocolatey\bin\python3.11.exe late_rollcall_checkin.py
  C:\ProgramData\chocolatey\bin\python3.11.exe late_rollcall_checkin.py --send
  ```

  Expected: unit tests PASS; dry-run makes no request; `--send` exits with a clear configuration error because the root JSON intentionally has no verified check-in URL/body yet.

- [x] **Step 5: Update evidence and deliver**

  Updated `findings.md`, `progress.md`, and `task_plan.md` with the official
  entry URL, SSO flow, field status, and fresh verification results.

  Record the final script behavior and the exact distinction between known URLs and the capture-required URL/body in `findings.md`, mark completed phases in `task_plan.md`, and report the root file links plus the one missing input needed to activate real sending.
