# Progress Log

## Session: 2026-09-01

### Phase 1: 文件与工具发现
- **Status:** in_progress
- **Started:** 2026-09-01
- Actions taken:
  - 读取并遵循 `using-superpowers` 与 `planning-with-files` 技能说明。
  - 快速检索记忆索引，未发现本项目或 APK 逆向相关历史。
  - 列出工作目录，发现 `base.apk.1`。
  - 建立任务计划、发现记录和进度日志。
  - 用户补充最终交付物：可配置账号/字段的一键 Python 签到脚本。
  - 确认 `base.apk.1` 大小为 105,656,864 字节，`tar -tf` 可正常读取 APK 条目。
  - 探测常用逆向工具：当前 PATH 仅发现系统 `tar.exe`，未发现 Java/jadx/apktool/adb 等。
  - 提取 `classes.dex`、Flutter `libapp.so`（arm64）及 Flutter 资源，确认业务主要在 Dart AOT。
  - 定向扫描命中账号/服务/定位/签到相关 Dart 类名和若干候选 API 路径；初版输出曾被噪声截断，下一步改做 URL/字段专项提取。
  - 用偏移感知扫描区分真实路径与机器码噪声：确认 84 条高置信路径、26 个字段/签到相关命中；未见明显签到提交 endpoint。
  - 修正并运行 AXML 解析器：确认包名、版本、Flutter 入口、定位/网络权限及 cleartext/network-security 配置。
  - 解析 `resources.arsc`/相关资源，发现 `app.fzu.edu.cn` 的两个入口地址；修正字符串搜索脚本的导入副作用后准备重新搜索精确命中。
  - 精确搜索资源字符串池，确认 `/fd-app/m/index.html` 与环境标识；已完成清单结构解码，准备映射资源 ID 和 network security config。
  - 资源表解析初次因类型块伪匹配越界中止，已加边界校验，待重跑。
  - 对 arm64 `libapp.so` 与 DEX 做中文/英文签到词精确搜索：无中文模块名，只有通用英文符号；搜索器已改为 ASCII-safe 输出。
  - 查看签到命中附近的 AOT 字符串：`trackSignIn` 靠近组织/服务列表类，`signIn` 靠近服务分类详情请求；未发现与其相邻的签到提交路径。
  - 资源表/字符串搜索确认 `APP_SCHEME=kysk-fdxy-app`，并抽取到 `res/` 490 个资源文件；network security config 为 `res/4u.xml`。
  - 解析 `libapp.so` ELF：确认 Dart snapshot data/instructions 边界和仅有 `_kDart*` 动态符号，确定下一步需要 snapshot-aware 解析或动态抓包。
  - 克隆并检查 Blutter AOT 工具；当前缺少 CMake/Ninja/编译器，先探测 Visual Studio 安装位置，再决定是否构建。
  - 发现 MSVC 编译器实际已安装，但 CMake/Ninja 缺失；运行 Blutter Dart 探测时因缺少 `requests` 模块中止。
  - 手工读取 snapshot metadata：Dart 2.19.6 stable，snapshot hash `adb4292f3ec25074ca70abcd2d5c7251`。
  - 建立 `analysis/.venv` 并安装 Blutter Python 依赖；Dart 版本探测成功。
  - 尝试安装 CMake/Ninja：Ninja 已就绪，CMake MSI 仍在后台安装。
  - 资源全局字符串池精确定位了生产 H5、scheme、环境和 app 标识；修正资源查询器导入副作用/编码问题，待重跑。
  - 公开检索 API 路径/类名/`trackSignIn`，未发现公开源码或协议。
  - 公开检索到官方 `west2-online/fzuhelper-app` 开源仓库，搜索结果显示其包含“晚点名签到”；准备只读克隆并搜索实现。
  - 在官方仓库 `app/(tabs)/toolbox.tsx` 读取到晚点名入口：`https://yzsxg.fzu.edu.cn/livecloud/project/fzu/attn/oauth2/authorize.action`，WebView + SSO；其 scheme 与当前 APK 一致。
  - 阅读官方 WebView/SSO 实现：先设置 `sso.fzu.edu.cn` Cookie，再加载入口 URL，并使用包含 appId/appScheme 的 User-Agent；未见签到表单 API。
  - 验证晚点名入口无凭证返回 SSO 302/cookie；当前 APK 本地未含 `yzsxg/livecloud/oauth2` 字符串，确认入口来自动态服务配置。
  - 读取 SSO 登录页：登录方式/flowkey/croypto/captcha 动态，配置不硬编码登录绕过，优先复用有效 Cookie。
  - 浏览器复现签到页面：确认当前时段/空列表/定位桥错误；读取官方同 scheme 客户端源码，确认 ReactNativeWebView 定位请求-回传消息格式与 Android geolocationEnabled 设置。
  - 阅读官方 SSO 登录实现：整理动态 `SESSION/croypto/flowkey`、AES 加密密码、`SOURCEID_TGC` Cookie 及短信二次验证字段；未将动态认证流程硬编码进脚本。
  - 根配置加入晚点名入口 URL、SSO callback/domain/UA、空的待捕获提交请求模板和字段状态分组。
  - 脚本完成 JSON/form/raw 编码、占位符渲染、URL/header/body 脱敏与显式 `--send` 保护；新增对应 TDD 测试。
  - 按用户要求将本地忽略的 `data.json` 精简为最小占位模板，仅保留 App/入口、会话、定位和最终请求配置；真实签到 body 仍为空。
  - 脚本默认优先读取有内容的 `data.json`，空文件或不存在时回退到 `late_rollcall_config.json`；11 项测试通过。
  - 核对远程 push 风险：本地历史已包含 105,656,864 字节 APK 和分析环境，Git LFS 未配置；未直接推送原始历史。
  - 使用 `.gitignore` 排除 APK/解包产物/虚拟环境，制作 12 个文件的代码文档干净快照，并以提交 `ab91fe9` 初次发布、`5d43847` 和 `fcb9f67` 同步到 `origin/main`；本地原始 `main` 保持不变。
  - 建立 `analysis/late_rollcall_static_inventory.md`，把当前可确认 URL、SSO/定位桥协议、字段状态和晚间动态采集步骤集中化。
  - DEX 精确解析确认仅为 Flutter/native 壳层，未包含业务请求实现。
  - 按用户要求运行 claude-mem 卸载；卸载成功，用户数据/旧 cache 目录的额外手动删除被策略拒绝，未影响项目分析。
  - 生成 AOT 服务清单：确认通用 vendor-service 请求类、WebView scheme processors，以及目录/打开/认证/定位相关字段候选；未见专属签到类。
  - 只读抓取公开 H5 主包和预加载 chunk：确认 JSON + header `token` 的通用封装、`serviceId` 深链；未发现签到业务实现。
  - 对公开入口和候选 API 做无凭证只读探测：H5 入口 200，`/zhfd/` 404，api host 上两个目录 POST 404，登录空体超时；暂不据此构造脚本。
  - AOT 访问器清单补充了服务对象字段和 `KYOrgVendorServiceRequest` 的 `serviceId/appToken` 线索，但仍无法从字符串池确认请求方法/完整 body。
  - 检查非图片 assets 与嵌套 `ae/res.zip`：未发现签到 H5/JS；`res.zip` 仅含 `global.db`。
  - 完成 TDD Task 1/2/3：先观察缺失模块/配置/安全函数测试失败，再实现并通过 6 个 unittest。
  - 生成根目录 `late_rollcall_checkin.py` 与 `late_rollcall_config.json`；默认 dry-run 正常输出 URL/字段清单，`--send` 在 `enabled=false` 下以退出码 2 拒绝发送。
- Files created/modified:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### Phase 2: 静态定位签到功能
- **Status:** complete
- Actions taken:
  -
- Files created/modified:
  -

### Phase 4: 验证与交付
- **Status:** complete
- Actions taken:
  - 根目录配置写入官方同 scheme 客户端确认的晚点名 SSO 入口 URL。
  - 将 SSO Cookie/回调/UA、APK 观察到的字段、服务元数据候选、待抓包提交字段分组记录。
  - 完成 10 个 unittest、语法编译、JSON 解析、dry-run 和 `--send` 防护验证。
- Files created/modified:
  - `late_rollcall_checkin.py`
  - `late_rollcall_config.json`
  - `analysis/test_late_rollcall_checkin.py`
  - `docs/superpowers/plans/2026-09-01-late-rollcall-checkin.md`
  - `findings.md`
  - `progress.md`
  - `task_plan.md`

### Phase 5: 时间窗口动态采集
- **Status:** in_progress
- Actions taken:
  - 用户确认晚间在有效签到时段继续动态观察。
  - 读取官方同 scheme 客户端的定位桥协议，确认页面到原生定位回调的事件名和返回对象结构。
  - 建立 `analysis/evening_capture_log.md`，规定脱敏记录格式和提交前确认点。
- Files created/modified:
  - `analysis/evening_capture_log.md`
  - Blutter 初始化成功；Windows 原生构建因 Windows SDK 缺失停在 CMake 配置阶段，随后改用 Docker/Linux 工具链完成当前 APK 的完整 AOT 还原。
  - 完整 AOT 输出已导出 `objs.txt`、`pp.txt`、`asm/` 和 Frida 模板；Dart 版本与 snapshot hash 均与当前 APK 一致。
  - 还原 `native/location` → `KYAbilityMapUtil.getLocation` → 高德定位回调 → `lat`/`lon`/`city` → WebView `runJavaScript` 的调用链；确认定位字段是 App/WebView 桥数据，不是最终签到 body。
  - 还原通用“我的服务”目录请求的 GET 路径及查询字段；`trackSignIn`/`signIn` 归类为登录行为统计，不是晚点名提交。
  - 完整 AOT 输出未发现 `attn`、`livecloud`、`oauth2` 或签到专属 Request 类，确认最终 H5 请求仍需有效页面运行时采集。
  - Chrome 中找到用户的登录标签页，但可见 DOM/网络能力暂时无响应；未刷新页面、未点击签到、未传输敏感数据。

### Phase 6: 远程仓库同步
- **Status:** complete
- Actions taken:
  - `.gitignore` 增加 APK、解包目录、虚拟环境和本地抓包文件规则。
  - 远程仓库使用无 APK 的独立根提交，避免把本地历史中的超限二进制上传。
  - 推送后复核 `origin/main` 文件清单，仅包含脚本、JSON、测试和脱敏文档。
- Remote commits: `ab91fe9` (initial clean publication), `5d43847`/`fcb9f67` (analysis record synchronization), `89c5701` (browser inspection record), `af0e64f` (AOT analysis references), `2e9ea1c` (AOT docs), `780f016` (local data template loading)

## Test Results
| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Unit tests | `python -m unittest discover -s analysis -p test_late_rollcall_checkin.py -q` | 11 pass | 11 pass | PASS |
| Python syntax | `python -m py_compile late_rollcall_checkin.py analysis/test_late_rollcall_checkin.py` | exit 0 | exit 0 | PASS |
| JSON syntax | `python -m json.tool late_rollcall_config.json` | exit 0 | exit 0 | PASS |
| Default run | `python late_rollcall_checkin.py` | no network | exit 0, dry-run | PASS |
| Send guard | `python late_rollcall_checkin.py --send` | reject disabled request | exit 2, no request | PASS |

## Error Log
| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-09-01 | `using-superpowers` 初始路径不存在 | 1 | 按技能根目录映射改用正确路径 |
| 2026-09-01 | PowerShell `Format-Hex` 不接受 `-Count` | 1 | 改用其他字节/ZIP 检查方式 |
| 2026-09-01 | Python 定向字符串脚本正则转义错误 | 1 | 改为手工扫描可打印片段，避免该正则路径 |
| 2026-09-01 | PowerShell 多行 Python `-c` 引号折损 | 2 | 创建本地扫描辅助脚本并直接运行 |
| 2026-09-01 | 扫描器输出触发 GBK `UnicodeEncodeError` | 1 | stdout 改为 UTF-8/backslashreplace |
| 2026-09-01 | 候选脚本执行路径重复为 `analysis\analysis` | 1 | 改从项目根目录执行 |
| 2026-09-01 | AXML 属性解析错位 | 1 | 修正属性起点相对 `ResXMLTree_attrExt` 的偏移 |
| 2026-09-01 | 递归删除 claude-mem 数据/cache 被执行策略拒绝 | 1 | CLI 卸载已完成；保留目录不参与任务 |
| 2026-09-01 | PowerShell 下 `rg` 的脚本目录 glob 无效 | 1 | 记录为工具探测噪声，后续改用文件枚举 |
| 2026-09-01 | 公开 H5 搜索输出触发 GBK `UnicodeEncodeError` | 1 | stdout 与上下文改为 ASCII-safe |
| 2026-09-01 | Blutter Dart 探测缺少 Python `requests` | 1 | 记录依赖缺口，改用项目虚拟环境 |
| 2026-09-01 | Blutter CMake 配置找不到 C/C++ 编译器 | 1 | 确认本机 Windows SDK 环境变量为空，记录为 AOT 构建阻塞；不影响字符串/访问器静态分析 |
| 2026-09-01 | 资源查询器导入 `parse_arsc` 触发顶层循环并 GBK 编码中断 | 1 | 加主程序保护并使用安全 stdout |
| 2026-09-01 | Windows Blutter 构建受 Windows SDK 阻塞 | 1 | 在 Docker/Linux 中使用同一 Dart 2.19.6 工具链完成完整 AOT 还原，并核对当前 APK snapshot hash |


## 5-Question Reboot Check
| Question | Answer |
|----------|--------|
| Where am I? | Phase 5 in progress; Phase 6 remote publication complete；APK AOT 静态还原已完成 |
| Where am I going? | 交付已确认入口与配置模板；真实提交 URL/body 需自有账号抓包后填入 |
| What's the goal? | 解析“晚点名签到”接口字段与安全复现方式 |
| What have I learned? | 晚点名是动态下发的 SSO WebView 入口；APK 只负责服务目录和原生定位/授权桥，最终提交请求不在 APK/公开 H5 内 |
| What have I done? | 完成完整 AOT 静态分析、定位字段/调用链、服务目录请求还原、配置脚本、字段清单和验证 |
