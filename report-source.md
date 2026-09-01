# 晚点名签到协议深度研究报告

日期：2026-09-01  
范围：本人已登录页面、实体 Android 设备、当前远程晚点名 H5 资源、项目 APK 静态分析  
目标：确认请求路径、请求方法、认证头、加密前字段和可行的合法自动化边界

## 结论摘要

当前最可靠的分析入口不是 Android Studio 的 Network Inspector 或普通 MITM，而是直接读取登录页面返回的 H5 JavaScript。当前页面资源返回 `200`，并明确包含以下接口：

```text
POST /livecloud/project/fzu/attn/init.action
GET  /livecloud/project/fzu/attn/currentTimestamp.action
GET  /livecloud/project/fzu/attn/check.action
GET  /livecloud/project/fzu/attn/clockIn.action
```

所有接口都使用页面 URL 中的 token 作为请求头 `token`。`check.action` 和 `clockIn.action` 的业务对象不会以明文 JSON 或 form body 发送，而是先经过客户端 AES-CBC 加密，再作为 URL query 的 `param` 发送。

## 已确认的请求结构

### 初始化

```text
POST https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/init.action
Header: token=<runtime page token>
Body: {}
```

响应外层字段：`success`、`code`、`msg`、`data`。`data` 当前实际返回这些对象：

```text
paramsData
schoolData
userData
mapData
statusData
```

### 服务端时间

```text
GET https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/currentTimestamp.action
Header: token=<runtime page token>
```

响应 `data` 字段：`date`、`userId`、`timestamp`。页面用 `timestamp` 校准本地时钟，并据此计算 `isLate`。

### 范围校验

```text
GET https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/check.action
Header: token=<runtime page token>
Query: param=<URL-encoded encrypted payload>
```

加密前对象字段：

```json
{
  "mapType": "amap",
  "longitude": "<actual longitude>",
  "latitude": "<actual latitude>",
  "range": "<JSON.stringify(schoolPosition)>"
}
```

页面将 `schoolData[*].FPosition` 中的范围 JSON 合并为 `schoolPosition`，再调用此接口。返回数组的第一个元素用于得到匹配校区。

### 最终签到

```text
GET https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/clockIn.action
Header: token=<runtime page token>
Query: param=<URL-encoded encrypted payload>
```

加密前对象字段已从当前 H5 调用点逐项确认：

```json
{
  "campus": "<matched campus ID>",
  "lon": "<actual longitude>",
  "lat": "<actual latitude>",
  "startTime": "<FStartTime>",
  "endTime": "<FEndTime>",
  "actualLocation": "<matched campus title + address>",
  "caIsNo": "<FCaIsNo query value or 0>",
  "collUnit": "<FCollUnit>",
  "way": "<FWay numeric value>",
  "isLate": "<server-time-derived 0 or 1>"
}
```

成功响应从 `data.attn` 读取，页面随后使用 `actualLocation`、`checkInTime` 和 `msg` 更新界面。

## 加密与传输

当前 H5 客户端使用 CryptoJS 的 AES：

```text
AES-128-CBC
PKCS7 padding
UTF-8 JSON.stringify(object)
Base64 ciphertext
encodeURIComponent(param)
```

客户端代码中存在固定的 AES key/IV 常量，但它们不写入本地 `data.json`；配置文件只保留占位符，避免把加密实现细节误当成账号凭证。脚本实现时必须保持 JavaScript 的对象字段顺序和 UTF-8 JSON 序列化行为一致。

## 页面与设备证据

- 当前登录页面 H5 资源：[`index-cb879b31.js`](https://yzsxg.fzu.edu.cn/plug-in/livecloud/project/fzu/attn/assets/index-cb879b31.js)
- 页面读取 token：优先读取 URL 查询参数 `token`，其次读取 `sessionStorage.token`。
- 页面 `contextPath` 为空时，请求路径直接位于 `/livecloud/project/fzu/attn/`。
- 实体设备运行包为 `1.17.3`，项目 APK 为 `1.17.0`；设备包 Java 层仍是 Flutter 壳，AOT 字符串与服务桥接链保持一致。
- 实体 App 通过定位桥提供 `lon`、`lat` 和地址；页面先完成范围校验，再允许最终签到按钮进入可点击状态。
- 当前设备页面已存在签到成功状态，本次没有点击最终签到。

## 为什么 Android Studio/MITM 没有直接拿到 body

Android 官方 Network Inspector 当前支持 `HttpsURLConnection` 和 `OkHttp`，不保证显示 WebView JavaScript 发出的请求。[Network Inspector 文档](https://developer.android.com/studio/debug/network-profiler)

当前 release App 未开启 WebView 调试 socket，页面经过用户 CA 代理时产生 `Trust anchor for certification path not found`。Android 官方文档说明，Android 7 及以上应用默认不信任用户新增 CA，除非应用网络安全配置显式允许。[网络安全配置文档](https://developer.android.com/privacy-and-security/security-config)

mitmproxy 官方也说明，Android 应用可能绕过系统代理，且应用可能不接受用户 CA；这正好解释了本次“电脑代理正常、设备没有可解密请求”的结果。[mitmproxy 代理模式文档](https://docs.mitmproxy.org/stable/concepts/modes/)

## 推荐的脚本边界

可以实现：

- 读取本地配置中的本人有效 token；
- 读取或获取本人当时的真实定位；
- 调用 `init.action` 和 `currentTimestamp.action`；
- 按页面逻辑构造范围校验和最终请求的加密参数；
- 默认 dry-run，打印 URL/字段结构而不发送最终签到。

不应实现：

- 修改成不在场的坐标；
- 绕过签到时间、范围、设备或服务端校验；
- 自动处理他人账号、验证码或短信二次认证；
- 把 token、Cookie、密码或精确坐标提交到 Git。

## 来源记录

| 来源 | 用途 | 结论 |
|------|------|------|
| 当前登录 H5 JS | 直接恢复接口与字段调用点 | 高置信；接口和字段来自实际页面代码 |
| `init.action` 只读探测 | 校验响应对象结构 | 高置信；返回 `200` 和真实字段类型 |
| 实体设备 ADB/Logcat | 校验 App 版本、定位桥和页面状态 | 高置信；设备包为 `1.17.3` |
| 项目 APK AOT/DEX | 解释服务目录和原生桥 | 高置信；最终 H5 业务不在 APK 内 |
| Android 官方文档 | 解释 Network Inspector、WebView 调试和用户 CA 行为 | 一手技术资料 |
| mitmproxy 官方文档 | 解释系统代理绕过和证书限制 | 一手工具资料 |
