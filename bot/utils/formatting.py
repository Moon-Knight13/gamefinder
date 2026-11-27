from __future__ import annotations


def format_bar(count: int, max_count: int) -> str:
    if count <= 0:
        return ""
    return "\U0001f7e9" * count


def format_heatmap(week_data: list[dict], threshold: int) -> str:
    from bot.utils.time_blocks import BLOCK_ORDER

    days: dict[str, dict[str, int]] = {}
    for row in week_data:
        d = row["date"]
        if d not in days:
            days[d] = {}
        days[d][row["block"]] = row["count"]

    lines = []
    header = "         " + "  ".join(["Morn", " Aft", " Eve"])
    lines.append(header)

    for date_str in sorted(days.keys()):
        counts = days[date_str]
        cells = []
        for block in BLOCK_ORDER:
            c = counts.get(block, 0)
            if c >= threshold:
                cells.append(f" {c:>2}\U0001f7e9")
            elif c > 0:
                cells.append(f" {c:>2}⬜")
            else:
                cells.append("  0⬛")
        day_label = date_str[-5:]
        lines.append(f"{day_label}  {'  '.join(cells)}")

    return "\n".join(lines)


def format_ranked_windows(windows: list[dict], threshold: int) -> str:
    lines = []
    for w in windows:
        count = w["count"]
        if count < threshold:
            continue
        bar = format_bar(count, count)
        block_label = w["block"].capitalize()
        lines.append(f"{bar}  {count}  {w['date']} · {block_label}")
    return "\n".join(lines) if lines else "No windows meet threshold."
