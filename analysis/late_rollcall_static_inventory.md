# 晚点名签到静态清单

> 这份清单只记录当前 APK、官方同 scheme 客户端源码和无提交的页面观察结果。`confirmed` 只表示“观察到该入口/标识”，不表示它一定是最终签到 body 的必填字段。

## 1. 应用与来源

| 项目 | 结果 |
|------|------|
| 当前 APK | `base.apk.1` |
| APK SHA-256 | `77410AE27FA818423276DC8A6407A2616D330CF79E36D22DE7AFACB72EA2545B` |
| 包名 | `cn.edu.fzu.fdxypa` |
| 版本 | `1.17.0` / versionCode `25122401` |
| 框架 | Flutter AOT；业务在 `libapp.so`，DEX 主要是壳层 |
| 当前 APK 本地是否含晚点名中文/入口 | 否；服务地址由“我的服务”数据或远程配置下发 |
| 同 scheme 官方源码 | `west2-online/fzuhelper-app`；其工具箱给出晚点名 WebView 入口 |

## 2. URL 清单

| 状态 | URL/模板 | 用途 |
|------|----------|------|
| 高置信入口 | `https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action` | 晚点名 SSO 授权入口，官方源码标记为 WebView + SSO |
| 已观察重定向 | `https://sso.fzu.edu.cn/login?service=https%3A%2F%2Fyzsxg.fzu.edu.cn%2Flivecloud%2Fproject%2Ffzu%2Fattn%2Foauth2%2Fcallback.action` | 未登录时的统一身份认证入口 |
| SSO 回调 | `https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/callback.action` | SSO 成功后回调地址 |
| 当前页面模板 | `https://yzsxg.fzu.edu.cn/plug-in/livecloud/project/fzu/attn/index.action?token=<redacted>&contextPath=` | 用户登录后页面；token 不写入文件 |
| App scheme | `kysk-fdxy-app` | 智汇福大/同 scheme 客户端标识 |
| 定位协议模板 | `kysk-fdxy-app://native?type=location&function=<callback>` | 页面请求原生定位的协议线索 |
| 公开 H5 | `https://app.fzu.edu.cn/fd-app/m/index.html` | 通用 App/H5 入口，不是签到提交 URL |
| 开发测试 scheme 页 | `http://test.quingk.com/scheme/index.html?nativeScheme=` | 仅测试线索，不用于生产 |

## 3. 定位桥协议

官方同 scheme WebView 的可读实现表明：

1. 页面发起 `navigator.geolocation.getCurrentPosition`、`watchPosition` 或 `clearWatch`。
2. 原生 WebView 负责真实定位权限和设备定位。
3. 页面/协议回调成功对象：

```json
{
  "lon": "<经度>",
  "lat": "<纬度>",
  "address": {
    "city": "",
    "district": "",
    "street": "",
    "streetNumber": ""
  },
  "formattedAddress": ""
}
```

失败/拒绝时，回调可能是空 `lon`/`lat` 和空地址。普通 Chrome 没有 `window.ReactNativeWebView` 或智汇福大原生协议处理器，因此会出现“无法调用智汇福大APP的定位服务”。浏览器开发者工具的经纬度覆盖不能自动补上这个原生桥。

### 3.1 当前 APK 的 AOT 还原细节

完整 Blutter 分析确认当前 Flutter APK 的协议链如下：

```text
native/location
  -> KYAppVendorServiceSchemeLocationProcessor.process
  -> KYAbilityMapUtil.getLocation(option)
  -> AMapFlutterLocation.onLocationChanged
  -> 读取 latitude/longitude/address 等原生结果
  -> 组织 lat/lon/city 等 Map
  -> WebViewController.runJavaScript(function(JSON))
```

当前 APK 读取到的原生定位键包括：

```text
latitude, longitude, address, city, country, province,
district, street, streetNumber, cityCode, description
```

处理器把坐标解析后写入 `lat`、`lon`；定位失败时使用 `-2` 哨兵值。`native/userauth` 另有 `function`、`authType=2` 和 App token 回调链。它们都是 App/WebView 桥字段，不能据此推导晚点名服务的最终 HTTP body。

完整 AOT 输出没有发现 `attn`、`livecloud`、`oauth2` 或签到专属 Request 类；`trackSignIn` 只属于登录行为统计。因此最终签到请求仍必须在远程 H5 的有效页面状态下动态确认。

### 3.2 AOT 实现锚点与定位选项

以下地址是本次针对当前 APK `libapp.so` 的 AOT 输出地址，用于复核分析结果，不是运行时 HTTP URL：

| AOT 符号/方法 | 地址 | 已确认行为 |
|--------------|------|------------|
| `KYAbilityMapUtil::getLocation` | `0xb61884` | 创建定位配置、监听高德事件、整理结果 Map 并返回 Future |
| `KYAppVendorServiceSchemeLocationProcessor::process` | `0x110baa0` | 读取 `function`，调用定位能力，再用 `runJavaScript(function(JSON))` 回传页面 |
| `_setLocationOption` | `0x110c110` | 设置当前 APK 的高精度定位参数 |

当前 APK 的 `AMapLocationOption.getOptionsMap` 会序列化这些配置键：

```text
locationInterval
needAddress
locationMode
geoLanguage
onceLocation
pausesLocationUpdatesAutomatically
desiredAccuracy
distanceFilter
locationAccuracyAuthorizationMode
fullAccuracyPurposeKey
```

当前实现观察到的主要值是 `needAddress=true`、高精度/导航级精度、`locationInterval=2000`、完整精度授权；随后通过 Flutter MethodChannel 调用 `startLocation`，结果来自 `onLocationChanged` EventChannel。这里没有发现“把任意经纬度写入请求体即可绕过定位”的代码路径；坐标伪造、时间绕过或设备校验绕过不属于本分析脚本的实现范围。

### 3.3 通用服务目录请求（不是签到提交）

完整 AOT 还原出的目录请求仅用于找到服务项或其远程 URL：

```text
GET /operation/service/app/v1/getMyHomeService
GET /operation/service/app/v1/getServiceListByGroupType?groupType=<type>
GET <分类详情路径>?groupId=<id>
GET /auth/develop/app/v1/getAppUrlById?appId=<id>
```

分页列表还会使用 `pageNumber`、`numPerPage`。这些请求能解释“我的服务”如何打开远程页面，但没有恢复出晚点名的最终 POST/JSON/form body。

## 4. 字段状态

### 4.1 入口/认证流程中确认或高置信的字段

| 字段 | 状态/用途 |
|------|-----------|
| `service` | SSO 登录重定向中的 callback 参数，值指向 `oauth2/callback.action` |
| SSO Cookie | 入口加载前必须存在于 `sso.fzu.edu.cn` 域；只记录存在性，不记录原文 |
| `account`/`password` | SSO 获取 Cookie 的输入概念；登录页还有动态 flowkey/croypto/captcha，不能静态硬编码绕过 |
| `SESSION`/`SOURCEID_TGC` | 官方客户端正常 SSO 登录过程中使用的会话 Cookie 名称；只记录名称，不记录值 |
| `username`/`type`/`_eventId`/`execution`/`croypto`/`password` | 官方 SSO 用户名密码表单字段；密码会用动态 croypto 做 AES-ECB/PKCS7+Base64；不能复用静态值 |
| `businessNo`/`phone`/`token`/`delete`/`trustDevice` | 官方短信二次验证接口字段；脚本暂不自动触发短信 |
| `appId` | `cn.edu.fzu.fdxypa`，用于 App/UA 识别线索 |
| `appScheme` | `kysk-fdxy-app`，用于服务页识别 App |
| `function` | 定位协议回调函数名；不是签到业务字段 |
| `type=location` | 定位协议业务类型 |
| `lon`/`lat` | 定位回调坐标键；是否原样进入签到提交体，待动态请求确认 |
| `address`/`formattedAddress` | 定位回调地址键；是否进入签到提交体，待动态请求确认 |
| 当前 APK 原生结果 | `latitude`/`longitude`/`address`/`city` 等 | App 内部 AMap 结果；不是已确认签到 body |
| 当前 APK WebView 回调 | `lat`/`lon`/`city` 等 | `native/location` 处理器组织的回调 Map；不是已确认签到 body |
| `native/userauth` | `function`、`authType=2` | 服务页原生授权桥；不是签到提交字段 |

### 4.2 APK/服务目录观察到的字段名

这些字段来自 Flutter AOT getter、服务对象或定位相关字符串，只能作为动态采集时的比对清单：

```text
serviceId, serviceName, serviceUrl, serviceIds
groupId, groupIdx, urlType, pageType, scheme, appUrl, sourceUrl
appId, userId, orgId, deviceId
latitude, longitude, accuracy, timestamp
appToken, loginToken, accountToken, deviceToken
```

### 4.3 最终签到 HTTP 请求目前仍需动态确认

```text
最终提交 URL       CONFIRMED: /livecloud/project/fzu/attn/clockIn.action
HTTP 方法          CONFIRMED: GET
Content-Type       CONFIRMED: 业务数据不在 body，位于 query.param
实际业务键         CONFIRMED: campus, lon, lat, startTime, endTime, actualLocation, caIsNo, collUnit, way, isLate
token 头           CONFIRMED: Header token=<页面运行时 token>
签名/加密          CONFIRMED: AES-128-CBC/PKCS7 + Base64 + encodeURIComponent
服务端时间校验     部分确认：页面调用 currentTimestamp.action 并计算 isLate；服务端规则仍未知
服务端定位校验     部分确认：页面先调用 check.action；最终服务端规则仍未知
设备/UA 校验       未确认
```

这里的“CONFIRMED”来自当前登录 H5 JavaScript 调用点和只读 `init/currentTimestamp` 探测；没有调用最终 `clockIn.action`，因此未产生新的签到状态。

## 5. 晚间动态采集顺序

1. 在 21:30–23:59 从智汇福大 App 的“我的服务”进入，确认页面不再是普通 Chrome。
2. 记录页面最终 URL（查询参数中的 token 脱敏）。
3. 记录定位桥调用名称、回调键名和成功/失败状态；不记录 Cookie/token/精确坐标值。
4. 在最终提交前暂停，确认是否允许产生一次真实签到状态变更。
5. 采集最终请求的 URL、方法、Content-Type、body 键和字段类型；把凭证值替换为 `${auth.cookie}` 等占位符。
6. 将确认后的内容写入根目录 `late_rollcall_config.json` 的 `request` 部分，删除未出现的候选字段。

静态 AOT 结果只能补齐“定位桥和服务目录链”，不能替代第 4、5 步的 H5 请求确认；尤其不能把 `lat`/`lon`、`userId` 或 `appToken` 猜测成最终提交字段。

## 6. 根目录脚本配置位置

当前脚本已准备好：

- `app.late_rollcall_entry_url`：填写入口 URL，不是提交 URL。
- `auth.cookie`：本人有效 SSO Cookie，占位符位置，不要提交原文。
- `identity`/`location`/`service`：只填动态请求实际需要的字段。
- `request.url`、`request.method`、`request.headers`、`request.body`、`request.body_encoding`：只填最终采集确认的请求。
- `request.enabled` 默认 `false`；确认请求并完成审阅后才可改为 `true`，再用 `--send`。

## 7. 当前 H5 已确认的真实接口（2026-09-01）

直接读取当前登录页面返回的 H5 资源后，确认接口不在 APK 内，而在：

`https://yzsxg.fzu.edu.cn/plug-in/livecloud/project/fzu/attn/assets/index-cb879b31.js`

### 7.1 接口表

| 接口 | 方法 | 认证/参数 | 用途 |
|------|------|----------|------|
| `/livecloud/project/fzu/attn/init.action` | POST | Header `token`；body `{}` | 获取计划、校区范围、用户/组织字段和当前状态 |
| `/livecloud/project/fzu/attn/currentTimestamp.action` | GET | Header `token` | 获取服务端时间 |
| `/livecloud/project/fzu/attn/check.action` | GET | Header `token`；query `param` | 校验当前定位是否匹配签到范围 |
| `/livecloud/project/fzu/attn/clockIn.action` | GET | Header `token`；query `param` | 提交签到 |

`contextPath` 为空时，以上路径直接拼接到 `https://yzsxg.fzu.edu.cn`。

### 7.2 `check.action` 加密前字段

```json
{
  "mapType": "amap",
  "longitude": "<当前真实经度>",
  "latitude": "<当前真实纬度>",
  "range": "<JSON.stringify(schoolPosition)>"
}
```

其中 `schoolPosition` 由 `init.action` 返回的 `schoolData[*].FPosition` 解析并合并得到；返回数组首项用于确定匹配校区。

### 7.3 `clockIn.action` 加密前字段

```json
{
  "campus": "<匹配校区 ID>",
  "lon": "<当前真实经度>",
  "lat": "<当前真实纬度>",
  "startTime": "<paramsData.FStartTime>",
  "endTime": "<paramsData.FEndTime>",
  "actualLocation": "<匹配校区标题 + 地址>",
  "caIsNo": "<URL 参数 FCaIsNo，不存在时为 0>",
  "collUnit": "<userData.FCollUnit>",
  "way": "<userData.FWay>",
  "isLate": "<按服务端时间和 FLateTime 计算的 0/1>"
}
```

传输形式不是明文 body，而是：

```text
param = encodeURIComponent(Encrypt(JSON.stringify(object)))
```

当前 H5 代码使用 CryptoJS AES-128-CBC、PKCS7、UTF-8 和 Base64；`request.body` 因此保持为空，真正数据位于 GET query 的 `param`。

### 7.4 `init.action` 返回字段

真实只读探测返回的 `data` 对象包含：

```text
paramsData, schoolData, userData, mapData, statusData
```

页面映射出的关键字段为：

```text
FToday, FStartTime, FEndTime, FLateTime, FTips,
FErrorTips, FAppTips, FScopeTips, FListTips, FTimeTips, FNotInTips,
FClass, FCollUnit, FWay, FDefaultCampus, FName, FCheckInTime,
FCampusShow, FState, FActualLocation, FPlanID, UserId,
FPosition, ID, FName, mapType, mapKey, mapSecret,
status, attnData, resultData, errorMsg, createTime
```

这些字段中，`paramsData`/`userData`/`schoolData` 的值应从当前账号当前日期的 `init.action` 返回中动态读取，不能写死为示例值。

### 7.5 结果与下一步

- `init.action` 和 `currentTimestamp.action` 已使用当前会话做只读探测，均返回 HTTP 200；仅记录字段结构，不记录响应值。
- 当前账号当天已经显示签到成功，未调用 `check.action` 或 `clockIn.action`，没有重复提交。
- 真实脚本可以先实现 `init`、服务端时间、范围校验和加密参数的 dry-run；最终 `clockIn.action` 需要保持显式开关和真实定位约束。
