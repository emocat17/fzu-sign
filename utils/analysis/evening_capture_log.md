# 晚点名签到动态采集日志

## 使用范围

- 目标页面：`https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/index.action`
- 有效时段：页面显示的 `21:30–23:59`
- 账号范围：仅用户本人或明确授权的测试账号
- 记录规则：不写入密码、token、Cookie、完整 Authorization、精确坐标或可复用会话值；只记录字段名、类型、是否出现、脱敏后的 URL 和状态码。
- 提交规则：采集阶段不点击最终签到；若需要验证真实提交，必须在操作即将发生前由用户明确确认。

## 静态基线

- 晚点名入口：`https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action`
- SSO 回调：`https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/callback.action`
- SSO Cookie 域：`https://sso.fzu.edu.cn`
- App scheme：`kysk-fdxy-app`
- 官方定位协议线索：`kysk-fdxy-app://native?type=location&function=<callback>`
- 定位回调字段线索：`lon`、`lat`、`address`、`formattedAddress`
- WebView 定位消息线索：`getCurrentPosition`、`watchPosition`、`clearWatch`；回传事件为 `currentPosition`、`watchPosition` 及对应 Error。

## 动态采集记录

| 序号 | 时间 | 页面/组件 | 观察动作 | URL（脱敏） | 方法 | 请求头名称 | Body 字段/类型 | 响应状态 | 结论 |
|------|------|-----------|----------|-------------|------|------------|----------------|----------|------|
| 1 | 待晚间填写 | 页面加载 | 打开入口并等待任务出现 |  |  |  |  |  |  |
| 2 | 用户提供，时间待确认 | 来源未核实的辅助请求 | 观察用户提交的抓包文本 | `http://<redacted-ip>:8080/?tk=<redacted>&iv=<redacted>&encrypt=17` | POST | `Q-UA2`、`Q-GUID`、`QQ-S-ZIP`、`Accept`、`User-Agent`、`Content-Type`、`Host` 等 | Body 未提供；`Content-Length=224`；请求体疑似不透明/加密数据 | 待确认 | 排除为晚点名业务候选：目标不是福大域名，头部带 QQ SDK/设备标识，未出现签到或定位字段 |
| 3 | 2026-09-01 21:41 后 | 实体 App `1.17.3` | 从“业务/我的服务”打开晚点名 | `https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/...` | 页面导航 | App 日志出现 WebView 导航与定位权限桥；不记录值 | 页面显示已有“签到成功”，时间早于本次调试；未点击提交 | 已确认 | 设备实际版本与项目 APK `1.17.0` 不同；本次没有重复签到 |
| 4 | 2026-09-01 23:00 后 | 电脑代理验证 | 设备临时代理指向电脑 mitmproxy | `https://yzsxg.fzu.edu.cn/...` | HTTPS | 仅记录元数据 | WebView 日志：`Trust anchor for certification path not found`、SSL handshake failed；安全捕获日志无设备事件 | 排除当前代理路径 | release Flutter/WebView 不信任用户 CA，或存在证书固定；未继续绕过 |
| 5 | 2026-09-01 | 当前登录 H5 JS | 直接读取页面资源并分析调用点 | `https://yzsxg.fzu.edu.cn/plug-in/livecloud/project/fzu/attn/assets/index-cb879b31.js` | POST/GET | `token` header（不记录值） | `init` 返回对象结构已确认；`clockIn` 前置字段和 `param` 加密包装已确认 | 已确认 | 不调用 `clockIn.action`，不产生新的签到状态 |

## 定位桥记录

| 序号 | 事件/协议 | 页面是否调用 | App 是否回调 | 回调字段名/类型 | 是否含精确值 | 备注 |
|------|-----------|--------------|--------------|----------------|--------------|------|
| 1 | `getCurrentPosition` 或 `type=location` |  |  |  | 否 |  |

## 最终签到请求判定

- 最终提交 URL：`UNCONFIRMED`
- HTTP 方法：`UNCONFIRMED`
- Content-Type：`UNCONFIRMED`
- 必填字段：`UNCONFIRMED`
- 认证材料：`UNCONFIRMED`（只记录类型，不记录值）
- 是否需要签名/加密：`UNCONFIRMED`
- 是否需要服务端时间/定位/设备校验：`UNCONFIRMED`

## 每次动态采集后的结论

- 根因假设：普通 Chrome 缺少智汇福大原生定位桥；待在真实 App/WebView 中验证。
- 可安全脚本化的内容：入口 URL、SSO 会话复用、经确认的请求模板。
- 不脚本化的内容：伪造坐标、绕过时间/设备/风控校验、记录可复用凭证。

## 2026-09-01 浏览器复核记录

- 已在 Chrome 用户标签页中找到登录后的晚点名页面；URL 中的 token 仅用于当前会话定位，未写入本记录、配置或 Git。
- 浏览器连接在读取 DOM/可见控件时无响应；本次没有刷新、点击签到、输入敏感信息、接受定位权限或发送提交请求。
- 当前仍以官方同 scheme 客户端源码确认的原生定位桥为准：页面需要 App/WebView 提供真实设备定位回调；普通 Chrome 的页面上下文不能仅靠填写经纬度补上该桥。

## 2026-09-01 实体设备与电脑代理记录

- ADB 连接到一台实体 Android 15 / API 35、`arm64-v8a` 设备；智汇福大包已安装，设备包版本为 `1.17.3`。
- 通过 ADB 授予精确/粗略定位后，App 日志出现页面到 `native/permission` 定位权限桥的调用；页面随后显示已有签到成功状态。本次没有点击签到按钮。
- mitmproxy 在电脑端可独立捕获福大域名的只读请求，但设备 WebView 经过代理时出现证书信任链错误，未产生可用的页面流量记录。
- 设备代理已关闭并恢复为原状态；代理 CA 文件只保留在本地测试目录，后续应在不再需要时从设备用户证书中移除。

## 2026-09-01 H5 源码与只读接口探测

- 页面资源直接返回 `200`，当前 JS 资产包含 `init.action`、`currentTimestamp.action`、`check.action`、`clockIn.action` 四个接口调用。
- `init.action` 只读探测返回 `success/code/msg/data` 外层结构；`data` 含 `paramsData`、`schoolData`、`userData`、`mapData`、`statusData`。
- `currentTimestamp.action` 只读探测返回 `data.date`、`data.userId`、`data.timestamp`。
- `check.action` 的加密前对象键为 `mapType`、`longitude`、`latitude`、`range`；`clockIn.action` 的加密前对象键为 `campus`、`lon`、`lat`、`startTime`、`endTime`、`actualLocation`、`caIsNo`、`collUnit`、`way`、`isLate`。
- 两个业务对象都通过 GET query 的 `param` 发送，客户端先执行 AES-128-CBC/PKCS7/UTF-8 JSON/Base64/URL 编码。
- 本次没有向 `check.action` 或 `clockIn.action` 发送请求，没有使用或记录精确定位值。

## 2026-09-01 用户抓包排除项

- 用户提供的一条 `POST /?tk=...&iv=...&encrypt=17` 请求，目标为脱敏后的裸 IP `:8080`，不是 `yzsxg.fzu.edu.cn` 或 `sso.fzu.edu.cn`。
- 请求头含 `Q-UA2`、`Q-GUID`、`QQ-S-ZIP`，并出现 `com.tencent.mobileqq`、设备型号和系统信息；这更符合 QQ/Tencent SDK 的加密辅助请求、设备探测或上报流量。
- 当前文本没有提供 body 内容；即便 body 存在，也只能按加密载荷处理，不能据此推断晚点名字段。
- 该请求没有出现 `lat`、`lon`、`latitude`、`longitude`、签到活动 ID 或福大会话头，因此不写入 `data.json`，也不作为签到请求模板。
