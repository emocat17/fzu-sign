# Findings & Decisions

## Requirements
- 分析当前项目目录的手机 APK。
- 定位“我的服务”下“晚点名签到”模块。
- 找出发送签到请求所需字段及模拟发送方式。
- 目标是深入学习；复现示例应脱敏，并限定在用户有权限的账号/测试环境。
- 希望最终形成一个配置好账号和所需字段后可一键运行的 Python 脚本。

## Research Findings
- 工作目录中发现 `base.apk.1`，大小 105,656,864 字节。
- `tar -tf` 可以读取其 ZIP 目录，确认它是 APK/ZIP 容器；目录包含 `AndroidManifest.xml`、AndroidX/Kotlin 元数据、`assets/`、高德地图资源等。
- SHA-256：`77410AE27FA818423276DC8A6407A2616D330CF79E36D22DE7AFACB72EA2545B`；ZIP 条目 2,105 个；包含 1 个 `classes.dex`（约 7.8 MiB）。
- 包含 Flutter 特征：`assets/flutter_assets/`、`lib/*/libapp.so`、`libflutter.so`；业务 Dart 代码大概率位于 `libapp.so` 的 AOT 快照，而不是普通 Java/Kotlin DEX。
- 同时包含高德地图 SDK 与多架构 native 库，签到请求可能带有定位/设备信息，需单独确认而不能只看 UI 字段。
- `libapp.so` 的字符串保留了 Dart 包名和类名，说明可沿着业务模块追踪：`ky_app_vendor_service`（我的服务）、`ky_app_account`（账号）以及 `ky_flutter_map`/`amap_flutter_location`（定位）。
- 已命中的业务请求路径包括 `/operation/service/app/v1/getServiceListByGroupType`、`/operation/service/app/v1/getMyHomeService`、`/article/kyy/app/v1/saveBatchMyService`、`/auth/account/app/v1` 和 `/quingno/auth/app/v1`；这些目前只是候选/上下文接口，不应误认作签到提交接口。
- 命中 `signIn`、`trackSignIn`、`getSigned`、`Location.fromJson`、`latitude`、`longitude`、`deviceId` 等字符串；需要继续定位它们附近的请求类/路径和 JSON 序列化字段。
- 在 arm64 `libapp.so` 中，`trackSignIn` 位于偏移 `0x60bff`，`signIn` 位于 `0xc9a91`，`getSigned` 位于 `0xc879a`；字段名命中包括 `latitude`、`longitude`、`deviceId`、`orgId`、`serviceId`、`serviceIds`、`userId`、`timestamp`、`appToken`、`loginToken`、`deviceToken`。
- 当前从 APK 内能确认的版本化路径主要是通用服务/账号接口；没有发现带有明显 `signIn`/`attendance` 的提交路径。这提高了“晚点名签到”是远程服务/H5 或由服务配置动态下发的可能性，需继续分析服务打开链路和 URL 配置。
- AXML 清单解析结果：包名 `cn.edu.fzu.fdxypa`，版本 `1.17.0`（versionCode `25122401`），Flutter embedding 2，入口 `cn.edu.fzu.fdxy_app.MainActivity`。
- 清单声明了 `INTERNET`、精确/粗略定位、后台定位、网络/Wi-Fi 状态、设备电话状态等权限；`usesCleartextTraffic=true`，且存在自定义 network security config 资源引用。定位相关字段和传输安全策略需要纳入后续请求复现判断。
- 清单还声明了自定义 scheme（资源 ID 待从 `resources.arsc` 解码）和 WebView/URL launcher 组件，进一步支持“服务项可能打开远程 H5/自定义 scheme”的判断。
- `resources.arsc` 中发现基础地址 `https://app.fzu.edu.cn/fdxy` 与 `https://app.fzu.edu.cn/zhfd/`；它们是当前 APK 的高置信环境/入口线索，仍需结合 AOT 中的 base URL 拼接逻辑确认具体用途。
- 资源全局字符串池的精确索引显示 `app.fzu.edu.cn`、`https://app.fzu.edu.cn/fd-app/m/index.html`、环境值 `pro`、包/应用标识及 `kysk-fdxy-app`；未见 API host 配置键值。
- `resource_strings.py` 首次导入 `parse_arsc.py` 时触发其顶层解析循环并遇到 GBK 输出错误；已加主程序保护和 UTF-8/backslashreplace 输出。
- 资源字符串池还包含 `**https://app.fzu.edu.cn/fd-app/m/index.html`、`fdxypa_dev`、`fdxypa_dis`、`pro` 等环境/入口标识；`**` 可能是构建配置前缀或占位符，不能直接当作可请求 URL。
- `AndroidManifest.xml` 的 `usesCleartextTraffic=true`、网络安全配置引用和自定义 scheme 资源值需要结合 `resources.arsc`/`res` 文件解码，不能仅凭清单资源 ID 下结论。
- 搜索脚本的模块导入副作用已定位：`inspect_hits.py` 顶层循环会把调用方参数当输入；已改为 `if __name__ == "__main__"` 保护。
- `resources.arsc` 类型块初版遍历未验证 entry 数量，触发缓冲区越界；解析器已加入 chunk/header/entry 数量边界校验。
- `libapp.so` 精确搜索没有命中中文“晚点名签到/晚点/签到/点名”，只命中英文 `trackSignIn`、`signIn`、`getSigned`；当前更像通用/远程服务链路，而非 APK 内硬编码的该模块页面。
- DEX 精确字符串表只有 521 个条目，除包名、定位类和 native 库名外未包含业务 API/中文功能名；业务逻辑确实主要在 Flutter AOT `libapp.so`。
- `res/4u.xml` 是 network security config，内容为 `base-config cleartextTrafficPermitted=true`，与 manifest 的 cleartext 设置一致。
- claude-mem CLI 已按用户要求完成卸载（worker、注册项、Codex 集成、临时 marketplace 均已移除）；CLI 保留的 `C:\Users\Administrator\.claude-mem` 数据目录和旧 cache 目录的手动递归删除被执行策略拦截，未删除，且不参与本任务。
- AOT 清单确认“我的服务”是通用 vendor-service 框架，包含 `KYAppVendorServiceMineListRequest`、`KYAppVendorServiceCategoryDetailRequest`、`KYAppVendorServiceInfoRequest`、`KYOrgVendorServiceRequest`、`KYVendorServiceOperatorRequest` 等请求/详情类，以及 WebView scheme processor；没有“晚点名签到”专属类。
- 高置信业务字段候选：`groupId`/`groupIdx`、`serviceId`/`serviceIds`、`serviceName`、`serviceUrl`、`urlType`、`pageType`、`url`、`scheme`、`appId`、`orgId`、`userId`、`deviceId`、`latitude`、`longitude`、`timestamp`、`appToken`、`loginToken`、`accountToken`；其中前半部分更像服务目录/打开参数，后半部分更像登录/定位上下文，尚未证明都属于签到提交体。
- AOT 中还有 `&appId=`、`&userId=`、`http://test.quingk.com/scheme/index.html?nativeScheme=` 和 `http://192.168.31.233:8000/index.html?nativeScheme=`，说明服务打开可能把 `appId/userId` 拼入 URL 或 scheme；后两个是测试/开发入口，不应在生产脚本中使用。
- 对公开 `/fd-app/m/` Vue H5 的只读检查：主应用只有 `/demo`、`/privacyFd`、`/share`、`/userFd` 等通用路由；请求封装为 JSON，axios 请求拦截器把 cookie 中的 `token` 写入请求头 `token`。未发现“晚点名签到”业务代码或提交路径。
- H5 `share` 页面把 `serviceId` 放入 `kysk-fdxy-app://third_service?serviceId=...`，其作用是唤起原生 App 的服务项，不是签到 API。
- AOT 访问器显示服务数据对象至少有 `groupId`、`serviceId`、`serviceName`、`serviceUrl`、`urlType`、`pageType`、`scheme`、`appUrl`、`sourceUrl`、`userId`、`orgId` 等访问器；这能支持目录/打开链路的脚本化，但不等于签到体字段。
- `KYOrgVendorServiceRequest` 附近可见 `get:serviceId` 与 `appToken`；`KYAppVendorServiceCategoryDetailRequest` 和 `KYAppVendorServiceMineListRequest` 均存在，但从字符串池仍不能恢复其 HTTP 方法和完整 body。
- APK `assets/` 中没有签到 H5/JS；仅有 Flutter 资源、地图数据、加固库和 `ae/res.zip`（内部为 `global.db`，与签到业务无明显关联）。这意味着具体签到页面不会随 APK 离线提供。
- AOT 中未出现生产 API host 字符串；资源表有 app.fzu.edu.cn 入口，公开 H5 使用 api.quingk.com，但两者的直接目录请求未命中，需依赖 App 登录后的服务元数据或抓包确认。
- ELF 解析显示 `libapp.so` 的 `.rodata` 为 Dart isolate snapshot data（约 6.9 MiB），`.text` 为 Dart AOT instructions（约 11.5 MiB），动态符号只保留 snapshot 边界；若要恢复请求构造，需要 AOT snapshot-aware 工具或运行时抓包，普通字符串搜索无法得到方法体。
- 已下载 Blutter（commit `4a60ac6`）作为 Flutter AOT 解析候选；README 要求 Windows Visual Studio C++、CMake/Ninja、Capstone/ICU。当前 PATH 未发现 CMake/Ninja/Clang/G++，仓库也没有预编译 exe，暂时不能直接运行。
- Visual Studio 18 BuildTools 实际存在 MSVC 14.51（含 `cl.exe`/`link.exe`），但未发现 CMake/Ninja；Blutter 的 Dart 版本探测脚本还依赖未安装的 Python `requests`/`pyelftools`，目前不适合直接构建。
- 从 `libapp.so`/`libflutter.so` 读取到 Dart snapshot hash `adb4292f3ec25074ca70abcd2d5c7251`、Dart `2.19.6 (stable)`；这与 Blutter 的 Android arm64 支持范围匹配，理论上可以进一步恢复 AOT 对象/汇编。
- Blutter 的 Windows 初始化脚本会从 ICU/Capstone 官方发布包下载依赖；当前尚未安装这些额外依赖或构建工具。
- 已在 `analysis/.venv` 安装 `requests` 2.34.2 与 `pyelftools` 0.33，Blutter 的 Dart 探测成功返回 `2.19.6`、compressed-pointers、null-safety 等 flags。
- Chocolatey 的 CMake MSI 安装仍有 `msiexec` 进程，CMake 尚未进入 PATH；Ninja 已可用。
- Blutter 环境初始化已成功下载 ICU/Capstone；随后用项目虚拟环境识别出 Dart `2.19.6`，但构建阶段因本机 Windows SDK 未安装（`WindowsSDKVersion`/`WindowsSdkDir` 为空，CMake 找不到 C/C++ 编译器）在配置阶段停止，未生成 AOT 对象池或汇编输出；当前 AOT 结论仍以字符串/访问器清单为准。
- 改用 Docker/Linux 工具链后，Blutter 完整代码分析成功：已导出 `objs.txt`、`pp.txt`、`asm/` 和 Frida 模板。完整输出中的 Dart 版本、snapshot hash 与 APK 一致，说明这次对象池/汇编还原针对的是当前 APK，而不是示例包。
- 完整 AOT 还原确认当前 APK 注册了 `native/location`、`native/userauth` 等服务页协议；`KYAppVendorServiceSchemeLocationProcessor::process` 调用 `KYAbilityMapUtil::getLocation`，再通过 WebView `runJavaScript` 把结果回传页面。
- 当前 APK 的 `KYAbilityMapUtil::getLocation` 返回 `Future<Map<String, dynamic>>`：先创建 `AMapLocationOption`，默认 `needAddress=true`、高精度/导航级精度、`locationInterval=2000`，监听 `AMapFlutterLocation.onLocationChanged`，收到首个结果后停止定位。
- 定位结果映射已从 AOT 代码确认：原生高德结果的 `latitude`/`longitude` 被解析为 `lat`/`lon`（失败哨兵值为 `-2`），同时保留 `address`、`city`、`country`、`province`、`district`、`street`、`streetNumber`、`cityCode`、`description` 等键；这些是 App→WebView 定位回调数据，不是已确认的签到 HTTP body。
- `native/userauth` 处理器读取 `function` 和 `authType`，只接受 `authType=2`，刷新 App token 后向 WebView 注入回调；这是服务页取原生用户授权信息的桥，不等于晚点名提交接口。
- 服务目录 Request 的完整 AOT 方法已恢复：我的服务列表是 GET `/operation/service/app/v1/getMyHomeService`（无查询参数）；分类列表是 GET `/operation/service/app/v1/getServiceListByGroupType?groupType=<type>`；分类详情使用 `groupId` 查询参数；服务 URL 详情使用 `/auth/develop/app/v1/getAppUrlById?appId=<id>`，响应对象包含 `title`/`url`；分页我的服务列表使用 `pageNumber`/`numPerPage`。
- `trackSignIn`/`signIn` 已排除为晚点名签到：AOT 调用链是登录成功后的 `recordLoginEvent`→`postTracker`，并非服务页提交；服务目录相关 Request 也只有 GET，未发现签到专属 POST。
- 对完整 Blutter 输出检索 `attn`/`livecloud`/`oauth2` 没有命中生产入口（仅有无关的键盘字符串 `Attn`），因此晚点名 H5/最终接口仍由远程服务下发，无法从当前 APK 离线恢复。
- 对三个唯一字符串做公开源码/文档检索没有结果；没有可引用的公开协议可替代自有账号抓包。
- 进一步公开检索发现福州大学西二在线的官方开源仓库 `west2-online/fzuhelper-app`，其 App Store/项目描述明确包含“晚点名签到”功能；该仓库是一个独立 React Native 客户端，可能提供同一业务的可读实现，待与当前 Flutter APK 的版本/服务端区分。
- 官方仓库 `west2-online/fzuhelper-app` 的工具箱源码直接给出“晚点名签到” URL：`https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action`，类型为 WebView，且标记 `sso: true`。该仓库同时使用 `kysk-fdxy-app` scheme，与当前 APK 资源中的 scheme 一致，故这是目前最高置信的晚点名入口 URL；仍需确认当前 APK 版本是否使用同一后端。
- 官方 WebView 实现显示 SSO 模式不是把用户名/密码直接放进签到请求，而是先获取并设置 `https://sso.fzu.edu.cn` 的登录 Cookie，再加载晚点名 URL；还设置 User-Agent 标识 `appId/cn.edu.fzu.fdxypa appScheme/kysk-fdxy-app hengfeng/fdxyappzs appType/2 ruijie-facecamera`。因此可复现的关键认证材料是 SSO Cookie，签到表单的具体请求由远程页面生成。
- 当前 APK 的 `libapp.so`/资源中未命中 `yzsxg`、`livecloud` 或 `oauth2`，说明该入口 URL 确实不是本包硬编码，而是“我的服务”数据下发或配置关联；官方仓库的同 scheme 代码是目前唯一直接来源。
- 对入口 URL 的无凭证 GET 返回 302，Location 为 `https://sso.fzu.edu.cn/login?service=https%3A%2F%2Fyzsxg.fzu.edu.cn%2Flivecloud%2Fproject%2Ffzu%2Fattn%2Foauth2%2Fcallback.action`；响应同时设置了 yzsxg 侧 `web_route`/`JSESSIONID`，但这些不能替代登录后的 SSO Cookie。
- SSO 登录页公开 HTML 显示动态登录模式 `UsernamePassword`/`smsLogin` 和动态 flowkey/croypto/captcha 信息；因此不把静态登录字段硬编码为可直接绕过的流程，配置优先复用本人有效 Cookie。
- 浏览器当前页面实际呈现：签到时段 `21:30–23:59`、状态“未签到”、列表为空，并报“无法调用智汇福大APP的定位服务”；该错误出现在定位桥接前，尚未进入签到提交请求。
- 官方同 scheme 客户端的 WebView 注入协议已确认：页面调用 `navigator.geolocation.getCurrentPosition/watchPosition/clearWatch` 时，通过 `window.ReactNativeWebView.postMessage` 发送 `getCurrentPosition`/`watchPosition`/`clearWatch`；原生侧用设备定位后回传 `currentPosition`/`watchPosition` 或对应 Error。普通 Chrome 不提供 `window.ReactNativeWebView`，因此会触发当前错误。
- 官方客户端的 SSO WebView 在加载页面前设置 `sso.fzu.edu.cn` Cookie，并开启 Android `geolocationEnabled`；这说明不能只靠在请求体中填经纬度修复页面桥接错误。
- 官方 SSO 代码进一步给出正常登录流程字段（仅作协议学习/配置说明）：初始 GET `/login` 获取 `SESSION`、动态 `login-croypto` 和 `login-page-flowkey`；用户名密码 POST 字段为 `username`、`type=UsernamePassword`、`_eventId=submit`、`geolocation`、`execution`、`captcha_code`、`croypto`、AES-ECB/PKCS7+Base64 后的 `password`、`captcha_payload`，成功后从 `Set-Cookie` 取得 `SOURCEID_TGC`。这不是绕过认证，且动态 CAPTCHA/短信二次验证仍可能需要人工完成。
- 官方 SSO 二次验证字段为短信接口 JSON `businessNo=0008, phone`，校验接口 JSON `phone, token, delete=false, trustDevice=false`；脚本暂不自动发送短信或处理 CAPTCHA。
- 根目录交付配置已把 `https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action` 标为晚点名入口 URL，并记录 SSO Cookie 域、callback URL、应用 User-Agent；最终 `clockIn.action` 的 URL、GET 方法、加密 query.param 和 10 个加密前业务字段已由当前 H5 JS 确认，但默认仍不发送。
- `late_rollcall_checkin.py` 支持 JSON/form/raw 请求体、`${section.field}` 替换、请求/查询参数脱敏、回环 HTTP 错误测试和 `--send` 双重开关；`late_rollcall_config.json` 默认 `request.enabled=false` 且 body 为空。
- 已生成本地忽略文件 `data.json` 的最小占位模板：只保留 App/入口、SSO 会话、定位和最终请求配置；敏感值统一为 `XXXXX`，`request.body` 保持为空，最终请求字段以晚间实际捕获结果为准。
- `late_rollcall_checkin.py` 现在优先读取有内容的本地 `data.json`，不存在或为空时回退到仓库中的 `late_rollcall_config.json`；`.env` 和 `data.json` 均由 `.gitignore` 排除。
- 实体设备运行的智汇福大包是 `1.17.3` / versionCode `26042401`，与项目原始 APK `1.17.0` 不同；设备包 SHA-256 只保留在本地分析结果，不进入发布仓库。
- 实体 App 在定位权限授予后通过 WebView 日志确认了 `native/permission` 定位权限桥；当前页面显示的是此前已经存在的“签到成功”状态，本次没有点击最终签到。
- 电脑 mitmproxy 本身可以捕获福大域名的只读请求，但设备 WebView 经过代理时报 `Trust anchor for certification path not found` / SSL handshake failed，且没有产生设备端安全元数据；这条路径未能取得最终签到 body，不继续绕过证书校验。
- 直接在电脑内存中读取当前登录页返回的 H5 资源 `.../attn/assets/index-cb879b31.js` 后，发现真实业务接口：`POST /livecloud/project/fzu/attn/init.action`、`GET /livecloud/project/fzu/attn/currentTimestamp.action`、`GET /livecloud/project/fzu/attn/check.action`、`GET /livecloud/project/fzu/attn/clockIn.action`。
- H5 公共封装确认：`init.action` 使用空 JSON body 并在 `token` header 认证；其余三个接口同样使用 `token` header，`check`/`clockIn` 把加密后的业务对象放进 GET query 的 `param`，不是明文 POST body。
- `check.action` 加密前字段已确认是 `mapType`、`longitude`、`latitude`、`range`；`clockIn.action` 加密前字段已确认是 `campus`、`lon`、`lat`、`startTime`、`endTime`、`actualLocation`、`caIsNo`、`collUnit`、`way`、`isLate`。
- H5 加密调用已确认是 CryptoJS AES-128-CBC + PKCS7 + UTF-8 JSON + Base64 + `encodeURIComponent`；加密前对象的字段顺序需要保持 JavaScript 构造顺序。当前只记录算法，不把客户端常量写入公共配置。
- 只读运行时探测确认 `init.action` 返回外层 `success/code/msg/data`，`data` 包含 `paramsData`、`schoolData`、`userData`、`mapData`、`statusData`；`currentTimestamp.action` 的 `data` 包含 `date`、`userId`、`timestamp`。
- 本地原始历史的 push 风险已处理：其中包含 `base.apk.1`（105,656,864 bytes，超过 GitHub 普通单文件 100 MB 限制）、Flutter native 库和 `analysis/.venv`，且没有 LFS tracking，因此没有直接推送原始 `main`。
- 已按用户要求使用 `.gitignore` 忽略 APK/解包产物/虚拟环境，并从当前工作树制作代码文档干净快照；提交 `ab91fe9` 初次发布、`5d43847`/`fcb9f67` 记录同步、`89c5701` 浏览器复核记录，均已推送到 `origin/main`。远程目前只含脚本、JSON、测试和脱敏分析文档，本地原始 `main` 历史保持不变。
- 新增 `analysis/late_rollcall_static_inventory.md`，集中整理晚点名入口/SSO 回调/定位桥协议、字段状态、最终请求待确认项和晚间采集顺序；不含用户 token/Cookie/精确坐标。
- 公开入口探测结果：`https://app.fzu.edu.cn/fd-app/m/index.html` 返回 200；`https://app.fzu.edu.cn/zhfd/` 返回 404。对 `https://api.quingk.com/operation/service/app/v1/getMyHomeService`、`getPageService` 空 JSON POST 返回 404，登录路径空体超时；因此当前不能把 `api.quingk.com` 直接当作 Flutter 服务 API base URL。
- 这些探测未带凭证，也未触发签到；404 更可能表示缺少应用前缀/路由网关或 API 并不在该 host。
- 原始上下文搜索的控制台编码异常已通过 ASCII 转义修正。
- `trackSignIn` 的邻近字符串属于 `ky_flutter_org_std/src/mine/ky_flutter_org_mine_number_list_card_widget.dart` 和 `KYOrgServiceViewModel`；`signIn` 邻近 `KYAppVendorServiceCategoryDetailRequest`，没有同区域的提交路径。这些名称更像通用 UI/服务目录能力，尚不能指向“晚点名签到”专属接口。
- `resources.arsc` 精确命中没有发现“晚点名签到”中文文案；资源中明确的自定义 scheme 是 `kysk-fdxy-app`（资源键 `APP_SCHEME`）。清单中的 scheme 资源 ID需结合资源表校验，但这一字符串可作为高置信 scheme 候选。
- PATH 中未发现 `java`、`jadx`、`apktool`、`adb`、`7z`、`unzip`、`apkanalyzer` 等常用工具；系统有 `tar.exe`。

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| 先检查 ZIP/APK 结构和工具，再进行 DEX/资源搜索 | 先确认文件是否完整以及本机可用工具 |
| 脚本默认 dry-run，并显式要求 `--send` 才发送 | 便于审阅请求内容，降低误触发真实签到的风险 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| 文件扩展名为 `.apk.1` | 待通过文件头和 ZIP 列表确认其实际格式 |
| `Format-Hex -Count` 在当前 PowerShell 版本不支持 | 改用字节读取和 ZIP 条目检查，不影响 APK 读取 |
| 初版定向字符串脚本的控制字符正则转义错误 | 改为手工扫描 ASCII/UTF-8/UTF-16LE 可打印片段 |
| PowerShell 多行 `python -c` 参数发生引号折损 | 将扫描器写为 `analysis/extract_strings.py` 后直接执行文件 |
| 扫描结果含控制台 GBK 无法编码的 Unicode 字符 | 配置 stdout 使用 UTF-8 与 `backslashreplace`，继续输出命中结果 |
| 候选脚本在 `analysis` 工作目录下再次拼接 `analysis` 路径 | 从项目根目录执行，或传入相对于当前目录的正确路径 |
| AXML 属性起点相对结构体解析错误 | 按 `ResXMLTree_attrExt` 规则改为 `node + 16 + attributeStart` |
| Blutter 脚本 glob 在 PowerShell 中按字面传给 `rg` | 后续使用 `Get-ChildItem` 枚举文件再搜索；不影响工具仓库 |

## Resources
- `base.apk.1`（当前工作目录）

## Visual/Browser Findings
- 无。
