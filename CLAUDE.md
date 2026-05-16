# 财联社电报 CLI

命令行工具，获取和筛选 https://www.cls.cn/telegraph 的电报快讯。

## 项目结构

```
cls/
  cls_telegraph.py    # 单文件 CLI，包含所有逻辑
  requirements.txt    # 依赖: requests
```

## 运行

```bash
pip install -r requirements.txt
python cls_telegraph.py -h
```

## API 体系

项目使用了两套 API，各有分工：

### v1 API（主力）

- **URL**: `https://www.cls.cn/v1/roll/get_roll_list`
- **用途**: 单次获取、live 模式加载历史（支持无限深度分页）
- **需要签名**: 是
- **分页**: `last_time` 参数传入最后一条的 `ctime`，返回更早的数据
- **服务端分类**: `category` 参数（red/announcement/watch/hk_us/fund/remind）
- **签名算法**: 所有参数（含 app/os/sv/category 等）按 key 字母排序 → 拼接为 `key=value&key=value` → SHA-1 hex → MD5 hex

### nodeapi（辅助）

- **URL**: `https://www.cls.cn/nodeapi/updateTelegraphList`
- **用途**: live 模式定时刷新最新数据
- **需要签名**: 否（但需要浏览器 User-Agent）
- **限制**: 总数据池约 50 条，不支持深度分页

### 为什么两套 API 并存

- nodeapi 无需签名、响应快，适合高频轮询刷新
- v1 API 支持无限分页和服务端分类过滤，适合批量获取和历史加载
- live 模式中：刷新用 nodeapi，加载历史用 v1 API

## 开发历程

### 第一阶段：需求分析与 API 探测

1. 通过 WebFetch 分析 https://www.cls.cn/telegraph 页面结构
2. 发现页面基于 Next.js，初始数据通过 `initialState.telegraph.telegraphList` 嵌入 HTML
3. 探测到 nodeapi 接口：`/nodeapi/updateTelegraphList` 和 `/nodeapi/telegraphList`
4. 确认数据字段结构：id, title, content, ctime, level(A/B/C), stock_list, subjects, audio_url 等
5. 发现网站的分类筛选（全部/加红/公司/看盘/港美股/基金/提醒）是客户端过滤，API 不直接支持

### 第二阶段：初版实现

1. 单文件 Python CLI，基于 `argparse` + `requests`
2. 使用 nodeapi 获取数据，客户端做所有过滤（level/keyword/subject/stock/时间戳）
3. 支持终端彩色输出和 JSON 输出
4. 初版 `-f` 模式是简单的 `time.sleep` 循环 + print 追加

### 第三阶段：遇到问题与修复

- **418 错误**: nodeapi 拒绝无 User-Agent 的请求 → 添加浏览器 Headers
- **分类不生效**: nodeapi 的 category 参数无效，所有分类都返回相同数据 → 确认是客户端过滤

### 第四阶段：live 模式重写（参照 wscn）

参照 `/Users/zhangjinshi/claudecode_workplace/wallstreetcn_com/wscn.py` 的 live 模式，将 `-f` 重写为 curses 全屏 UI：

- 顶部栏：标题 + 实时时间 + 筛选条件
- 中间：带颜色的电报内容（A=红色加粗, B=黄色, C=青色），CJK 感知换行
- 底部：状态栏（总条数、刷新倒计时、操作提示、搜索状态）
- 交互：j/k 滚动、鼠标滚轮、gg/G 跳转、/ 搜索、n/N 匹配导航、q 退出
- 新电报 `★ NEW` 高亮，有新内容自动回顶部
- 滚到顶部按 ↑ 手动触发刷新

### 第五阶段：突破 50 条限制

发现 nodeapi 两个接口数据池都只有约 50 条，无法加载更多历史。通过分析网站 JS bundle 找到了 v1 API：

1. 从 `pages/telegraph.js` 找到真正的 API 路径 `/v1/roll/get_roll_list` 和参数（refresh_type, rn, last_time, category）
2. 追踪 `Object(Q.request)` → `bMwp` 模块 → 发现请求带签名参数 `sign`
3. 追踪签名函数 `p` → `W2Yj` 模块 → 依赖 `KjvB`(SHA-1) 和 `aCH8`(MD5)
4. 逆向出签名算法：所有参数（含 app/os/sv）按 key 排序拼接 → SHA-1 → MD5
5. 尝试多种参数组合，确认签名必须包含所有参数（含空 category）
6. v1 API 支持无限分页，成功获取 80+ 条数据

### 第六阶段：整合与 bug 修复

- 非 live 模式改用 v1 API，自动分页获取任意条数
- live 模式加载历史改用 v1 API
- 新增 `-c/--category` 参数支持服务端分类过滤
- 修复：`filter_args` 中的 `category` 不应传给客户端 `filter_items`（它是 API 层参数）
- 修复：v1 API 每次最多返回约 20 条，非 live 模式需多次分页请求

### 第七阶段：live 模式正文显示残缺修复

现象：live 模式下，含换行的长正文（如《新闻联播》要闻汇总）只能看到首尾几行残片，中间内容凭空消失。

根因：
1. `cjk_wrap` 逐字符累计宽度时把 `\n` 当宽度 1 的普通字符塞进当前行，不断行
2. `render_item_lines` 渲染 `content` 段时直接把整段（含 `\n`）丢给 `cjk_wrap`
3. 产出的"逻辑行"里嵌着原始 `\n`，`stdscr.addnstr` 把 `\n` 当真换行处理，撑出额外屏幕行
4. 后续 `display_lines` 按 `body_start + i` 绝对行号绘制，覆盖掉被撑出来的行 → 中间内容被盖掉

修复：
- `cjk_wrap` 遇到 `\n` 强制断行（应用 `subsequent_indent`），从根上保证产出的每行不含 `\n`
- 正文截断从硬编码 200 提升到默认 1000，并新增 `--content-limit N` 参数，live 与非 live 共用

非 live 模式没踩到这个坑因为走的是 `print()`，原生处理 `\n`。

## 电报数据字段

每条电报（roll_data 数组元素）的关键字段：

| 字段 | 说明 |
|------|------|
| id | 唯一 ID |
| title | 标题（可能为空） |
| content | 正文（与 title 可能相同） |
| ctime | 发布 Unix 时间戳 |
| level | 重要等级: A(加红/重大), B(较重要), C(普通) |
| stock_list | 关联股票数组，含 name, StockID, RiseRange |
| subjects | 所属话题数组，含 subject_id, subject_name |
| reading_num | 阅读量 |
| comment_num | 评论数 |
| audio_url | 语音播报链接数组 |
| bold | 是否加粗(0/1) |
| type | 内容类型标识符 |

## 注意事项

- 所有 HTTP 请求需带浏览器 User-Agent，否则返回 418
- v1 API 签名中空字符串参数（如 `category=`）也参与签名计算，不可省略
- nodeapi 的 `updateTelegraphList` 返回最新数据（用于刷新），`telegraphList` 返回更早数据（分页），但两者数据池都限制在约 50 条
- v1 API 的 `last_time` 语义是"返回该时间之前的数据"，用于向下分页
- `cjk_wrap` 现在会把 `\n` 当强制断行，调用方不必再预先 `split("\n")`；新增依赖此行为的调用点直接传含 `\n` 文本即可
