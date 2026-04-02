#!/usr/bin/env python3
"""财联社电报 CLI - 获取和筛选财联社电报快讯"""

import argparse
import curses
import hashlib
import json
import sys
import time as _time
import unicodedata
from datetime import datetime

import requests

API_V1_URL = "https://www.cls.cn/v1/roll/get_roll_list"
NODEAPI_URL = "https://www.cls.cn/nodeapi"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Referer": "https://www.cls.cn/telegraph",
    "Accept": "application/json, text/plain, */*",
}
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
# 网站分类标签对应的 category 参数值
CATEGORY_MAP = {
    "全部": "", "加红": "red", "公司": "announcement", "看盘": "watch",
    "港美股": "hk_us", "基金": "fund", "提醒": "remind",
}


# ── 文本工具 ──────────────────────────────────────────────

def display_width(s):
    """计算字符串的终端显示宽度（中文占2列）"""
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def cjk_wrap(text, width, initial_indent="", subsequent_indent=""):
    """CJK 感知的文本换行，按显示宽度折行"""
    lines = []
    indent = initial_indent
    line = indent
    line_w = display_width(indent)
    for ch in text:
        ch_w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if line_w + ch_w > width:
            lines.append(line)
            indent = subsequent_indent
            line = indent + ch
            line_w = display_width(indent) + ch_w
        else:
            line += ch
            line_w += ch_w
    if line.strip():
        lines.append(line)
    return lines


# ── API ───────────────────────────────────────────────────

def _make_sign(params):
    """生成 API 签名: 参数按 key 排序拼接 → SHA-1 → MD5"""
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted(params.keys()))
    sha1 = hashlib.sha1(sign_str.encode()).hexdigest()
    return hashlib.md5(sha1.encode()).hexdigest()


def fetch_v1(last_time=None, count=20, category=""):
    """通过 v1 API 获取电报列表（支持深度分页）"""
    ts = last_time or int(_time.time())
    params = {
        "app": "CailianpressWeb",
        "os": "web",
        "sv": "8.4.6",
        "refresh_type": "1",
        "rn": str(count),
        "last_time": str(ts),
        "category": category,
    }
    params["sign"] = _make_sign(params)
    resp = requests.get(API_V1_URL, params=params, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno") not in (None, 0, "0"):
        raise RuntimeError(f"API 返回错误: {data}")
    return data.get("data", {}).get("roll_data", [])


def fetch_telegraph_nodeapi(count=20):
    """通过 nodeapi 获取最新电报（用于 live 刷新，无需签名）"""
    params = {"app": "CailianpressWeb", "os": "web", "sv": "8.4.6", "rn": count}
    resp = requests.get(f"{NODEAPI_URL}/updateTelegraphList", params=params,
                        headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error") != 0:
        return []
    return data["data"].get("roll_data", [])


# ── 过滤 ──────────────────────────────────────────────────

def filter_items(items, level=None, keyword=None, subject=None, stock=None,
                 since=None, before=None):
    """客户端过滤"""
    result = items

    if level:
        level_upper = level.upper()
        result = [i for i in result if i.get("level", "").upper() == level_upper]

    if keyword:
        kw = keyword.lower()
        result = [i for i in result
                  if kw in (i.get("title") or "").lower()
                  or kw in (i.get("content") or "").lower()]

    if subject:
        sub_kw = subject.lower()
        result = [i for i in result
                  if any(sub_kw in (s.get("subject_name") or "").lower()
                         for s in (i.get("subjects") or []))]

    if stock:
        stock_lower = stock.lower()
        result = [i for i in result
                  if any(stock_lower in (s.get("StockID") or "").lower()
                         or stock_lower in (s.get("name") or "").lower()
                         for s in (i.get("stock_list") or []))]

    if since is not None:
        result = [i for i in result if i.get("ctime", 0) >= since]

    if before is not None:
        result = [i for i in result if i.get("ctime", 0) <= before]

    return result


# ── 终端输出（非 live 模式）──────────────────────────────

def format_time(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def format_time_short(timestamp):
    return datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")


def format_terminal(items, show_stock=True):
    if not items:
        print("没有找到匹配的电报。")
        return

    level_colors = {"A": "\033[91m", "B": "\033[93m", "C": "\033[0m"}
    reset = "\033[0m"

    for item in items:
        ctime = item.get("ctime", 0)
        level = item.get("level", "C")
        title = item.get("title") or item.get("content", "")
        content = item.get("content", "")
        color = level_colors.get(level, "")

        print(f"{color}[{format_time(ctime)}] [{level}] {title}{reset}")

        if content and content != title and not title.startswith(content[:20]):
            display = content[:200] + ("..." if len(content) > 200 else "")
            print(f"  {display}")

        if show_stock and item.get("stock_list"):
            stocks = []
            for s in item["stock_list"]:
                name = s.get("name", "")
                sid = s.get("StockID", "")
                rise = s.get("RiseRange")
                rise_str = f" {rise:+.2f}%" if rise is not None else ""
                stocks.append(f"{name}({sid}){rise_str}")
            print(f"  📈 {' | '.join(stocks)}")

        subjects = item.get("subjects") or []
        if subjects:
            tags = [s.get("subject_name", "") for s in subjects if s.get("subject_name")]
            if tags:
                print(f"  🏷️  {', '.join(tags)}")

        print()


def format_json(items):
    print(json.dumps(items, ensure_ascii=False, indent=2))


# ── curses live 渲染 ─────────────────────────────────────

def render_item_lines(item, width):
    """将一条电报渲染为多行 (tag, text) 列表"""
    lines = []
    ctime = item.get("ctime", 0)
    level = item.get("level", "C")
    title = item.get("title") or ""
    content = item.get("content") or ""
    text = title or content

    time_str = format_time_short(ctime)
    if level == "A":
        tag = "level_a"
        prefix = f"[{time_str}] ‼️  "
    elif level == "B":
        tag = "level_b"
        prefix = f"[{time_str}] 🔴 "
    else:
        tag = "normal"
        prefix = f"[{time_str}] "

    indent = "         "
    first = True
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if first:
            wrapped = cjk_wrap(paragraph, width - 1,
                               initial_indent=prefix,
                               subsequent_indent=indent)
            first = False
        else:
            wrapped = cjk_wrap(paragraph, width - 1,
                               initial_indent=indent,
                               subsequent_indent=indent)
        for line in wrapped:
            lines.append((tag, line))

    # 内容（如果和标题不同）
    if content and title and content != title and not title.startswith(content[:20]):
        display = content[:200] + ("..." if len(content) > 200 else "")
        for line in cjk_wrap(display, width - 1,
                             initial_indent=indent,
                             subsequent_indent=indent):
            lines.append(("content", line))

    # 关联股票
    if item.get("stock_list"):
        stocks = []
        for s in item["stock_list"]:
            name = s.get("name", "")
            sid = s.get("StockID", "")
            rise = s.get("RiseRange")
            rise_str = f" {rise:+.2f}%" if rise is not None else ""
            stocks.append(f"{name}({sid}){rise_str}")
        stock_line = f"{indent}📈 {' | '.join(stocks)}"
        lines.append(("stock", stock_line))

    # 话题标签
    subjects = item.get("subjects") or []
    if subjects:
        tags = [s.get("subject_name", "") for s in subjects if s.get("subject_name")]
        if tags:
            lines.append(("subject", f"{indent}🏷️  {', '.join(tags)}"))

    return lines


def live_monitor(filter_args, interval=15):
    """curses 实时监控模式"""

    def _main(stdscr):
        curses.curs_set(0)
        curses.use_default_colors()
        curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)

        curses.init_pair(1, curses.COLOR_CYAN, -1)      # 普通/时间
        curses.init_pair(2, curses.COLOR_RED, -1)        # level A
        curses.init_pair(3, curses.COLOR_YELLOW, -1)     # level B
        curses.init_pair(4, curses.COLOR_GREEN, -1)      # 股票
        curses.init_pair(5, curses.COLOR_MAGENTA, -1)    # 话题
        curses.init_pair(6, curses.COLOR_GREEN, -1)      # 状态栏
        curses.init_pair(7, curses.COLOR_WHITE, -1)      # 日期/header
        curses.init_pair(8, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # 搜索高亮

        TAG_ATTR = {
            "normal":  curses.color_pair(1),
            "level_a": curses.color_pair(2) | curses.A_BOLD,
            "level_b": curses.color_pair(3),
            "content": curses.color_pair(0),
            "stock":   curses.color_pair(4),
            "subject": curses.color_pair(5),
            "date":    curses.color_pair(7) | curses.A_BOLD,
            "sep":     curses.color_pair(0),
            "new":     curses.color_pair(7) | curses.A_BOLD | curses.A_REVERSE,
        }

        last_key = -1
        all_items = []
        seen_ids = set()
        display_lines = []
        scroll_pos = 0
        last_fetch = 0
        first_load = True
        new_ids = set()
        loading_history = False
        error_msg = ""
        search_keyword = ""
        search_matches = []
        search_match_idx = -1

        # 构建过滤参数描述
        filter_desc = []
        if filter_args.get("level"):
            filter_desc.append(f"等级={filter_args['level'].upper()}")
        if filter_args.get("keyword"):
            filter_desc.append(f"关键词={filter_args['keyword']}")
        if filter_args.get("subject"):
            filter_desc.append(f"话题={filter_args['subject']}")
        if filter_args.get("stock"):
            filter_desc.append(f"股票={filter_args['stock']}")

        def do_filter(items):
            kw = {k: v for k, v in filter_args.items() if k != "category"}
            return filter_items(items, **kw)

        def refresh_data():
            nonlocal all_items, seen_ids, display_lines, last_fetch, first_load, new_ids, error_msg
            try:
                raw = fetch_telegraph_nodeapi(count=20)
                fetched = do_filter(raw)
                new_ids = set()
                for it in fetched:
                    item_id = it.get("id")
                    if item_id not in seen_ids:
                        if not first_load:
                            new_ids.add(item_id)
                        seen_ids.add(item_id)
                first_load = False
                # 合并：新的在前，去重
                merged = []
                merged_ids = set()
                for it in fetched + all_items:
                    item_id = it.get("id")
                    if item_id not in merged_ids:
                        merged.append(it)
                        merged_ids.add(item_id)
                all_items = merged
                error_msg = ""
            except Exception as e:
                error_msg = f"刷新失败: {e}"
            last_fetch = _time.time()
            rebuild_lines()

        def load_history():
            """翻到底部时加载更多历史数据（使用 v1 API 支持深度分页）"""
            nonlocal all_items, seen_ids, loading_history, error_msg
            if loading_history or not all_items:
                return
            loading_history = True
            try:
                oldest_ctime = min(it.get("ctime", 0) for it in all_items)
                raw = fetch_v1(last_time=oldest_ctime, count=50,
                               category=filter_args.get("category", ""))
                fetched = do_filter(raw)
                for it in fetched:
                    item_id = it.get("id")
                    if item_id not in seen_ids:
                        all_items.append(it)
                        seen_ids.add(item_id)
                error_msg = ""
            except Exception as e:
                error_msg = f"加载历史失败: {e}"
            loading_history = False
            rebuild_lines()

        def rebuild_lines():
            nonlocal display_lines
            h, w = stdscr.getmaxyx()
            display_lines = []
            current_date = None
            first_item = True
            for it in all_items:
                ctime = it.get("ctime", 0)
                item_date = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d")
                # 日期分隔线
                if item_date != current_date:
                    current_date = item_date
                    if not first_item:
                        dt = datetime.fromtimestamp(ctime)
                        wd = WEEKDAYS[dt.weekday()]
                        date_label = f"{dt.month:02d}月{dt.day:02d}日，{wd}"
                        display_lines.append(("sep", ""))
                        display_lines.append(("date", f" {date_label}"))
                        display_lines.append(("sep", ""))
                else:
                    if not first_item:
                        display_lines.append(("sep", ""))
                first_item = False
                if it.get("id") in new_ids and len(all_items) > len(new_ids):
                    display_lines.append(("new", " ★ NEW "))
                display_lines.extend(render_item_lines(it, w))
            if search_keyword:
                update_search()

        def update_search():
            nonlocal search_matches, search_match_idx
            search_matches = []
            if not search_keyword:
                search_match_idx = -1
                return
            kw = search_keyword.lower()
            for i, (tag, text) in enumerate(display_lines):
                if tag != "sep" and kw in text.lower():
                    search_matches.append(i)
            search_match_idx = 0 if search_matches else -1

        def search_goto(idx):
            nonlocal scroll_pos, search_match_idx
            if not search_matches:
                return
            search_match_idx = idx % len(search_matches)
            h, _ = stdscr.getmaxyx()
            body_h = h - 4
            target = search_matches[search_match_idx]
            scroll_pos = max(0, target - body_h // 3)
            max_scroll = max(0, len(display_lines) - body_h)
            scroll_pos = min(scroll_pos, max_scroll)

        def do_search_input():
            curses.curs_set(1)
            h, w = stdscr.getmaxyx()
            prompt_y = h - 1
            buf = ""
            while True:
                try:
                    stdscr.move(prompt_y, 0)
                    stdscr.clrtoeol()
                    display = f"/{buf}"
                    stdscr.addnstr(prompt_y, 0, display, w - 1, curses.A_BOLD)
                except curses.error:
                    pass
                stdscr.refresh()

                ch = stdscr.getch()
                if ch == 27:
                    curses.curs_set(0)
                    return None
                elif ch in (curses.KEY_ENTER, 10, 13):
                    curses.curs_set(0)
                    return buf
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    buf = buf[:-1]
                elif 32 <= ch <= 126:
                    buf += chr(ch)
                else:
                    try:
                        curses.ungetch(ch)
                        raw = stdscr.get_wch()
                        if isinstance(raw, str) and raw.isprintable():
                            buf += raw
                    except Exception:
                        pass

        def draw():
            stdscr.erase()
            h, w = stdscr.getmaxyx()

            # 顶部栏
            now_dt = datetime.now()
            now_time = now_dt.strftime("%H:%M:%S")
            wd = WEEKDAYS[now_dt.weekday()]
            header = f" 财联社电报 | {now_dt.month:02d}月{now_dt.day:02d}日，{wd}，{now_time}"
            if filter_desc:
                header += f"  | 筛选: {', '.join(filter_desc)}"
            try:
                stdscr.addnstr(0, 0, header, w - 1,
                               curses.color_pair(7) | curses.A_BOLD)
            except curses.error:
                pass
            try:
                stdscr.addnstr(1, 0, "─" * (w - 1), w - 1, curses.color_pair(6))
            except curses.error:
                pass

            # 底部状态栏
            status_y = h - 2
            body_start = 2
            body_h = status_y - body_start
            highlight_attr = curses.color_pair(8) | curses.A_BOLD
            match_set = set(search_matches) if search_keyword else set()
            current_match = (search_matches[search_match_idx]
                             if search_matches and search_match_idx >= 0 else -1)

            # 内容区域
            for i in range(body_h):
                line_idx = scroll_pos + i
                if line_idx >= len(display_lines):
                    break
                tag, text = display_lines[line_idx]
                if line_idx in match_set:
                    attr = highlight_attr if line_idx == current_match else curses.color_pair(8)
                    try:
                        stdscr.addnstr(body_start + i, 0, text, w - 1, attr)
                    except curses.error:
                        pass
                else:
                    attr = TAG_ATTR.get(tag, 0)
                    try:
                        stdscr.addnstr(body_start + i, 0, text, w - 1, attr)
                    except curses.error:
                        pass

            # 底部分隔线
            try:
                stdscr.addnstr(status_y, 0, "─" * (w - 1), w - 1, curses.color_pair(6))
            except curses.error:
                pass

            # 状态信息
            total = len(all_items)
            countdown = max(0, int(interval - (_time.time() - last_fetch)))
            status = f" 📡 共 {total} 条 | {countdown}s 后刷新 | ↑↓/jk翻页 /搜索 q退出"
            if search_keyword:
                mi = search_match_idx + 1 if search_matches else 0
                status += f" | 🔍 \"{search_keyword}\" [{mi}/{len(search_matches)}]"
            if error_msg:
                status += f" | ⚠ {error_msg}"
            try:
                stdscr.addnstr(status_y + 1, 0, status, w - 1,
                               curses.color_pair(6) | curses.A_BOLD)
            except curses.error:
                pass

            stdscr.refresh()

        # 首次加载
        refresh_data()
        stdscr.timeout(200)

        while True:
            draw()
            key = stdscr.getch()
            h, w = stdscr.getmaxyx()
            body_h = h - 4
            max_scroll = max(0, len(display_lines) - body_h)

            if key == 27:
                if search_keyword:
                    search_keyword = ""
                    search_matches = []
                    search_match_idx = -1
                else:
                    break
            elif key == ord('q') or key == ord('Q'):
                break
            elif key == curses.KEY_UP or key == ord('k'):
                if scroll_pos == 0:
                    if _time.time() - last_fetch >= 3:
                        refresh_data()
                else:
                    scroll_pos = max(0, scroll_pos - 1)
            elif key == curses.KEY_DOWN or key == ord('j'):
                scroll_pos = min(max_scroll, scroll_pos + 1)
            elif key == curses.KEY_MOUSE:
                try:
                    _, _, _, _, bstate = curses.getmouse()
                    if bstate & curses.BUTTON4_PRESSED:
                        scroll_pos = max(0, scroll_pos - 3)
                    elif bstate & curses.BUTTON5_PRESSED:
                        scroll_pos = min(max_scroll, scroll_pos + 3)
                except curses.error:
                    pass
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(0, scroll_pos - body_h)
            elif key == curses.KEY_NPAGE:
                scroll_pos = min(max_scroll, scroll_pos + body_h)
            elif key == ord('g'):
                if last_key == ord('g'):
                    scroll_pos = 0
            elif key == ord('G'):
                scroll_pos = max_scroll
            elif key == ord('/'):
                kw = do_search_input()
                if kw is not None:
                    search_keyword = kw
                    update_search()
                    if search_matches:
                        search_goto(0)
            elif key == ord('n'):
                if search_matches:
                    search_goto(search_match_idx + 1)
            elif key == ord('N'):
                if search_matches:
                    search_goto(search_match_idx - 1)
            elif key == curses.KEY_RESIZE:
                rebuild_lines()
                if search_keyword:
                    update_search()

            # 翻到底部再按下键时加载更多历史
            if (key in (curses.KEY_DOWN, ord('j'), curses.KEY_NPAGE)
                    and scroll_pos >= max_scroll and max_scroll > 0):
                load_history()

            last_key = key

            # 定时刷新
            if _time.time() - last_fetch >= interval:
                old_count = len(all_items)
                refresh_data()
                if len(all_items) > old_count:
                    scroll_pos = 0  # 有新内容自动回顶部

    curses.wrapper(_main)


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cls-telegraph",
        description="财联社电报 CLI - 获取和筛选财联社电报快讯",
    )

    fetch_group = parser.add_argument_group("获取控制")
    fetch_group.add_argument("-n", "--count", type=int, default=20,
                             help="获取条数（默认 20）")
    fetch_group.add_argument("--since", type=int, default=None,
                             help="获取该 Unix 时间戳之后的电报")
    fetch_group.add_argument("--before", type=int, default=None,
                             help="获取该 Unix 时间戳之前的电报")

    filter_group = parser.add_argument_group("筛选")
    filter_group.add_argument("-l", "--level", choices=["A", "B", "C", "a", "b", "c"],
                              help="按等级筛选: A(加红) / B(重要) / C(普通)")
    filter_group.add_argument("-k", "--keyword", help="按关键词搜索（匹配标题和内容）")
    filter_group.add_argument("-s", "--subject", help="按话题分类筛选（如 '公告', '港股'）")
    filter_group.add_argument("--stock", help="按关联股票筛选（代码或名称，如 sz300093）")
    filter_group.add_argument("-c", "--category",
                              choices=list(CATEGORY_MAP.keys()) + list(CATEGORY_MAP.values()),
                              help="按网站分类筛选: 加红/公司/看盘/港美股/基金/提醒")

    output_group = parser.add_argument_group("输出")
    output_group.add_argument("--json", action="store_true", help="输出 JSON 格式")
    output_group.add_argument("--no-stock", action="store_true",
                              help="不显示关联股票信息")

    follow_group = parser.add_argument_group("实时模式")
    follow_group.add_argument("-f", "--follow", action="store_true",
                              help="全屏实时监听新电报（q 退出）")
    follow_group.add_argument("--interval", type=int, default=15,
                              help="监听刷新间隔秒数（默认 15）")

    args = parser.parse_args()

    # 解析 category
    api_category = ""
    if args.category:
        api_category = CATEGORY_MAP.get(args.category, args.category)

    if args.follow:
        filter_kw = {
            "level": args.level,
            "keyword": args.keyword,
            "subject": args.subject,
            "stock": args.stock,
            "since": args.since,
            "before": args.before,
            "category": api_category,
        }
        live_monitor(filter_kw, interval=args.interval)
        return

    # 单次获取模式 - 使用 v1 API（自动分页）
    items = []
    last_time = None
    needed = args.count
    max_rounds = max(needed // 20 + 2, 3)  # 足够的轮次

    for _ in range(max_rounds):
        raw = fetch_v1(last_time=last_time, count=20, category=api_category)
        if not raw:
            break
        filtered = filter_items(raw, level=args.level, keyword=args.keyword,
                                subject=args.subject, stock=args.stock,
                                since=args.since, before=args.before)
        items.extend(filtered)
        if len(items) >= needed:
            break
        last_time = raw[-1].get("ctime")

    items = items[:needed]

    if args.json:
        format_json(items)
    else:
        format_terminal(items, show_stock=not args.no_stock)


if __name__ == "__main__":
    main()
