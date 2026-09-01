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
