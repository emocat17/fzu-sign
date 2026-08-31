# Task Plan: APK「晚点名签到」接口分析

## Goal
从当前目录的 APK 中定位“我的服务 → 晚点名签到”对应的请求路径、请求字段、认证/签名要求，并整理成可配置、可审计、仅面向自有账号或测试环境的 Python 复现脚本。

## Current Phase
Phase 5

## Phases

### Phase 1: 文件与工具发现
- [x] 确认 APK 文件、哈希与可用逆向工具
- [x] 记录应用包名/版本和基础清单信息
- [x] **Status:** complete

### Phase 2: 静态定位签到功能
- [x] 搜索“晚点名签到”及相关中文/英文关键词
- [x] 定位调用链、URL、HTTP 方法、字段构造和认证逻辑
- [x] **Status:** complete（确认通用服务目录/WebView 链路；具体签到提交 URL/body 不在 APK 内）

### Phase 3: 请求还原与边界判断
- [x] 区分必填字段、可选字段、设备/时间/位置校验
- [x] 判断是否存在加密、签名、动态 token 或序列化协议
- [x] **Status:** complete（静态确认候选字段与 JSON/令牌线索；无法确认远程服务的真实校验）

### Phase 4: 验证与交付
- [x] 用静态证据或本地安全验证确认结论
- [x] 编写带预览/发送开关的脱敏 Python 脚本
- [x] 整理脱敏请求示例、复现步骤和限制
- [x] **Status:** complete

### Phase 5: 时间窗口动态采集（晚间）
- [ ] 在 21:30–23:59 复现页面状态和定位桥调用
- [ ] 记录脱敏后的入口/重定向、请求方法/URL/headers 名称/body 字段类型/响应状态
- [ ] 区分页面定位回调、SSO 会话和最终签到提交请求
- [ ] 仅在用户临近真实提交且明确确认后观察提交结果
- [ ] **Status:** pending（已建立采集记录模板）

### Phase 6: 远程仓库同步
- [ ] 确认远程仓库是否接收 APK/解包产物，选择只推送代码或配置 Git LFS
- [ ] 在不改写未确认历史的前提下提交并推送安全文件
- [ ] **Status:** blocked_pending_user_choice（远程为空且本地历史含超限 APK）

## Key Questions
1. APK 中“晚点名签到”实际使用哪个 Activity/Service/API？
2. 请求是 REST/表单/JSON/GraphQL 还是其他协议？
3. 哪些字段来自用户输入，哪些来自登录态、设备、时间或定位？
4. 是否需要动态 token、签名、加密或证书固定？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先静态分析，再考虑动态验证 | 不触碰真实签到状态，且能先建立可审计证据链 |
| 示例使用占位符和自有账号/测试环境 | 避免泄露凭证或代替用户向生产服务发起签到 |
| 不尝试绕过时间、定位、设备或服务端校验 | 这会超出学习和接口理解范围，可能造成未授权状态变更 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| `base.apk.1` 不匹配常见 APK 扩展名 | 1 | 按 ZIP/APK 内容探测，不依赖文件后缀 |
| 定向字符串脚本的正则转义错误 | 1 | 改用手工字节扫描 |
| PowerShell 多行 Python 参数引号折损 | 2 | 改为执行 `analysis/extract_strings.py` |
| 控制台 GBK 无法编码扫描到的字符 | 1 | 输出不可编码字符时使用反斜杠转义 |
| 候选脚本执行时工作目录与相对路径重复 | 1 | 从项目根目录执行 |
| AXML 属性起点偏移错误 | 1 | 按二进制 XML 结构修正 |
| 搜索脚本导入时执行顶层参数循环 | 1 | 增加 `__main__` 保护 |
| `resources.arsc` 类型块边界未校验导致越界 | 1 | 增加 entryCount/offsets/chunk 边界检查 |
| 原始上下文输出触发控制台 Unicode 编码错误 | 1 | 使用 ASCII 转义输出上下文 |
| claude-mem 数据/cache 手动递归删除被执行策略拒绝 | 1 | 使用 CLI 完成插件/注册卸载，保留目录不参与任务 |
| 公开 H5 搜索输出触发控制台 Unicode 编码错误 | 1 | 使用 ASCII-safe 输出 |
| 无凭证探测的 API host/路径返回 404 或超时 | 1 | 记录为未确认，继续从 Flutter 配置/请求链路定位 base URL |
| Blutter 需要的 CMake/Ninja/编译器不在 PATH | 1 | 探测 Visual Studio 安装位置；若不可用则回退动态抓包/配置脚本 |
| Blutter Python 探测依赖缺失 | 1 | 已手工读取 Dart metadata；是否安装临时依赖待决定 |
| CMake MSI 安装未立即完成 | 1 | 保留后台安装观察；必要时使用便携版 CMake |
| 资源查询器导入副作用/控制台编码错误 | 1 | 加 `__main__` 保护和 ASCII-safe 输出 |

## Notes
- 当前目录只发现 `base.apk.1`，大小约 101 MiB。
- 需要把关键静态发现及时写入 `findings.md`，并在阶段转换时更新本文件和 `progress.md`。
