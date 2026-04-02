# cls-telegraph

财联社电报 CLI 工具，在终端获取、筛选和实时监控 [财联社电报](https://www.cls.cn/telegraph) 快讯。

## 功能

- 获取最新电报，支持指定条数（无上限）
- 按等级 / 关键词 / 话题 / 股票 / 时间戳 / 分类多维度筛选
- 服务端分类过滤（加红 / 公司 / 看盘 / 港美股 / 基金 / 提醒）
- 终端彩色输出 + JSON 输出
- **全屏实时监控模式**（curses UI，类似 `htop` 的交互体验）

## 安装

```bash
git clone https://github.com/<your-username>/cls-telegraph.git
cd cls-telegraph
pip install -r requirements.txt
```

依赖：Python 3.8+，`requests`

## 用法

### 基础获取

```bash
# 获取最新 20 条
python cls_telegraph.py

# 获取 50 条
python cls_telegraph.py -n 50

# JSON 输出（可管道到 jq）
python cls_telegraph.py -n 10 --json
```

### 筛选

```bash
# 按等级：A(加红/重大) B(重要) C(普通)
python cls_telegraph.py -l A

# 按服务端分类
python cls_telegraph.py -c 加红
python cls_telegraph.py -c 港美股

# 按关键词搜索（匹配标题和内容）
python cls_telegraph.py -k "原油"

# 按话题
python cls_telegraph.py -s "港股"

# 按关联股票（代码或名称）
python cls_telegraph.py --stock "ST西发"

# 指定时间范围（Unix 时间戳）
python cls_telegraph.py --since 1775140000 --before 1775145000

# 组合使用
python cls_telegraph.py -n 30 -c 港美股 -k "IPO" --json
```

### 实时监控模式

```bash
# 全屏监控，默认 15 秒刷新
python cls_telegraph.py -f

# 自定义刷新间隔
python cls_telegraph.py -f --interval 10

# 带筛选的监控
python cls_telegraph.py -f -l B
python cls_telegraph.py -f -c 加红
python cls_telegraph.py -f -k "原油"
```

**实时模式操作：**

| 按键 | 功能 |
|------|------|
| `j` / `k` / `↑` / `↓` | 逐行滚动 |
| 鼠标滚轮 | 3 行滚动 |
| `Page Up` / `Page Down` | 翻页 |
| `gg` | 回到顶部 |
| `G` | 跳到底部 |
| `/` | 搜索 |
| `n` / `N` | 下一个 / 上一个匹配 |
| `ESC` | 清除搜索 |
| `q` | 退出 |

- 新电报到达时显示 `★ NEW` 标记并自动回到顶部
- 在顶部按 `↑` 手动刷新
- 滚到底部按 `↓` 自动加载更多历史

### 完整参数

```
python cls_telegraph.py -h

获取控制:
  -n, --count N          获取条数（默认 20）
  --since TIMESTAMP      获取该 Unix 时间戳之后的电报
  --before TIMESTAMP     获取该 Unix 时间戳之前的电报

筛选:
  -l, --level {A,B,C}    按等级筛选: A(加红) / B(重要) / C(普通)
  -k, --keyword TEXT     按关键词搜索（匹配标题和内容）
  -s, --subject TEXT     按话题分类筛选（如 '公告', '港股'）
  --stock CODE           按关联股票筛选（代码或名称）
  -c, --category NAME    服务端分类: 加红/公司/看盘/港美股/基金/提醒

输出:
  --json                 输出 JSON 格式
  --no-stock             不显示关联股票信息

实时模式:
  -f, --follow           全屏实时监听新电报（q 退出）
  --interval N           监听刷新间隔秒数（默认 15）
```

## 输出示例

**终端模式：**

```
[2026-04-02 22:57:07] [B] ST西发董事长罗希失联 股价已连续两日跌停
  【ST西发董事长罗希失联...】
  📈 ST西发(sz000752) -5.01%
  🏷️  A股公告速递

[2026-04-02 22:52:02] [B] 小米集团调整子公司股东 雷军持股比例增加
  【小米集团调整子公司股东...】
  🏷️  港股动态, 小米汽车
```

等级颜色：A = 红色加粗，B = 黄色，C = 默认

**实时监控模式：**

```
 财联社电报 | 04月02日，星期三，23:25:04
─────────────────────────────────────────
 ★ NEW
[23:25:04] WTI原油期货涨幅再度扩大至10%
         🏷️  环球市场情报, 原油市场动态
                  ...
─────────────────────────────────────────
 📡 共 42 条 | 12s 后刷新 | ↑↓/jk翻页 /搜索 q退出
```

## License

MIT
