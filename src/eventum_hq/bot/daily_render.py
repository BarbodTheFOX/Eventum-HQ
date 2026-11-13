"""Turns a :class:`DailyReport` into a Telegram rich message (Markdown) or, as a fallback, HTML.

Rich messages (Bot API 10.1+) understand GitHub-style Markdown: headings, lists,
tables, dividers. Everything a person typed is escaped, so a stray ``*`` or ``|``
in a note can never break the layout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from eventum_hq.bot import texts
from eventum_hq.bot.formatters import esc, fa_digits, humanize_delta
from eventum_hq.core.jalali import jalali_date_parts
from eventum_hq.services.daily_report import DailyReport, HoursRow, NoteGroup, SectionKind

# characters with a Markdown meaning inside a line
_MD_SPECIAL = re.compile(r"([\\`*_~=|\[\]<>#$])")
_MD_LEADING = re.compile(r"^([-+]|\d+[.)])")
_URL = re.compile(r"^https?://", re.IGNORECASE)


def md_escape(text: str) -> str:
    """Escape user text for rich-message Markdown. Links stay clickable (only ``|`` is encoded)."""
    words = []
    for word in text.split(" "):
        if _URL.match(word):
            words.append(word.replace("|", "%7C"))
        else:
            words.append(_MD_SPECIAL.sub(r"\\\1", word))
    out = " ".join(words)
    match = _MD_LEADING.match(out)
    if match:  # "1. foo" / "- foo" would start a nested list
        token = match.group(1)
        out = (token[:-1] + "\\" + token[-1]) + out[len(token):]
    return out


def _hours_number(value: float) -> str:
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return fa_digits(text.replace(".", "٫"))


def _name(full_name: str | None) -> str:
    return (full_name or "").strip() or texts.NO_NAME


@dataclass(slots=True)
class _Group:
    title: str | None
    lines: list[tuple[str | None, str, bool]]  # (label, text, paragraph) — raw, not escaped


@dataclass(slots=True)
class _Section:
    title: str
    groups: list[_Group]
    hours: list[HoursRow] | None = None
    total: float | None = None


def _from_notes(groups: list[NoteGroup]) -> list[_Group]:
    return [_Group(g.title, [(i.label, i.text, i.paragraph) for i in g.items]) for g in groups]


def _auto_group(lines: list[str]) -> list[_Group]:
    return [_Group(texts.DAILY_FROM_BOT, [(None, line, False) for line in lines])] if lines else []


def _sections(report: DailyReport) -> list[_Section]:
    notes, auto = report.notes, report.auto
    out: list[_Section] = []

    def add(kind: str, groups: list[_Group]) -> None:
        if any(g.lines for g in groups):
            out.append(_Section(texts.DAILY_SECTION_TITLES[kind], groups))

    publishing = notes.section(SectionKind.PUBLISHING)
    published = [texts.DAILY_AUTO_PUBLISHED.format(title=i.title, code=i.code) for i in auto.published]
    add("PUBLISHING", (_from_notes(publishing.groups) if publishing else []) + _auto_group(published))

    video = notes.section(SectionKind.VIDEO)
    if video:
        add("VIDEO", _from_notes(video.groups))

    for section in notes.custom:
        title = section.title if section.kind == SectionKind.CUSTOM else texts.DAILY_SECTION_TITLES["NOTES"]
        groups = _from_notes(section.groups)
        if any(g.lines for g in groups):
            out.append(_Section(title or texts.DAILY_SECTION_TITLES["NOTES"], groups))

    production: list[str] = []
    if auto.outputs:
        parts = [texts.DAILY_AUTO_OUTPUT_PART.format(n=fa_digits(n), label=texts.OUTPUT_TYPE_LABELS[str(t)])
                 for t, n in sorted(auto.outputs.items(), key=lambda kv: str(kv[0]))]
        production.append(texts.DAILY_AUTO_OUTPUTS.format(items="، ".join(parts)))
    for user, tasks in auto.delivered:
        production.append(texts.DAILY_AUTO_DELIVERED.format(
            name=_name(user.full_name), n=fa_digits(len(tasks)), codes="، ".join(t.code for t in tasks)))
    add("PRODUCTION", _auto_group(production))

    pending = notes.section(SectionKind.PENDING)
    open_lines = [texts.DAILY_AUTO_OVERDUE.format(
        code=line.task.code, title=line.task.title, name=_name(line.assignee.full_name),
        delta=humanize_delta(line.task.due_at, report.generated_at) if line.task.due_at else "")
        for line in auto.overdue]
    open_lines += [texts.DAILY_AUTO_NO_COVER.format(title=i.title, code=i.code) for i in auto.reels_without_cover]
    if auto.awaiting_final:
        open_lines.append(texts.DAILY_AUTO_AWAITING.format(n=fa_digits(auto.awaiting_final)))
    add("PENDING", (_from_notes(pending.groups) if pending else []) + _auto_group(open_lines))

    if notes.hours:
        out.append(_Section(texts.DAILY_SECTION_TITLES["HOURS"], [], hours=notes.hours, total=notes.total_hours))
    return out


def _date_parts(report: DailyReport) -> tuple[str, str, str, str]:
    y, m, d, weekday = jalali_date_parts(report.day)
    return texts.WEEKDAYS[weekday], fa_digits(d), texts.JALALI_MONTHS[m - 1], fa_digits(y)


def _date_line(report: DailyReport) -> str:
    weekday, d, month, y = _date_parts(report)
    day = report.day
    return texts.DAILY_DATE_LINE.format(weekday=weekday, d=d, month=month, y=y, gd=day.day,
                                        gmonth=texts.ENGLISH_MONTHS[day.month - 1], gy=day.year)


def _hashtags(report: DailyReport) -> str:
    weekday, d, month, y = _date_parts(report)
    return texts.DAILY_HASHTAGS.format(weekday=weekday.replace("‌", "_").replace(" ", "_"),
                                       d=d, month=month, y=y)


def _hours_value(row: HoursRow) -> str:
    return texts.DAILY_HOURS_VALUE.format(n=_hours_number(row.hours)) if row.hours is not None else row.value


# ---- Markdown (rich message) ---------------------------------------------------------------


def _md_item(label: str | None, text: str, paragraph: bool) -> str:
    body = f"**{md_escape(label)}:** {md_escape(text)}" if label else md_escape(text)
    return body if paragraph else f"- {body}"


def render_markdown(report: DailyReport) -> str:
    lines = [f"# {texts.DAILY_BRAND}", f"### {texts.DAILY_TITLE}", md_escape(_date_line(report))]
    for n, section in enumerate(_sections(report), start=1):
        lines += ["", "---", "", f"## {md_escape(texts.DAILY_SECTION_HEADING.format(n=n, title=section.title))}"]
        if section.hours is not None:
            lines += ["", texts.DAILY_HOURS_HEADER, "| --- | --- | --- |"]
            for i, row in enumerate(section.hours, start=1):
                lines.append(f"| {fa_digits(i)} | {md_escape(row.name)} | {md_escape(_hours_value(row))} |")
            if section.total is not None:
                total = texts.DAILY_HOURS_VALUE.format(n=_hours_number(section.total))
                lines.append(f"|  | **{texts.DAILY_HOURS_TOTAL}** | **{md_escape(total)}** |")
            continue
        for group in section.groups:
            if not group.lines and not group.title:
                continue
            lines.append("")
            if group.title:
                lines += [f"#### {md_escape(group.title)}", ""]
            previous_paragraph = None
            for label, text, paragraph in group.lines:
                if previous_paragraph is not None and paragraph != previous_paragraph:
                    lines.append("")  # a list and a paragraph need a blank line between them
                lines.append(_md_item(label, text, paragraph))
                if paragraph:
                    lines.append("")
                previous_paragraph = paragraph
    lines += ["", "---", "", md_escape(_hashtags(report))]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


# ---- HTML (fallback: ordinary message) -------------------------------------------------------


def render_html(report: DailyReport) -> str:
    lines = [f"<b>{texts.DAILY_BRAND}</b>", f"<b>{texts.DAILY_TITLE}</b>", esc(_date_line(report))]
    for n, section in enumerate(_sections(report), start=1):
        lines += ["", f"<b>{esc(texts.DAILY_SECTION_HEADING.format(n=n, title=section.title))}</b>"]
        if section.hours is not None:
            for i, row in enumerate(section.hours, start=1):
                lines.append(f"{fa_digits(i)}. {esc(row.name)} — {esc(_hours_value(row))}")
            if section.total is not None:
                total = texts.DAILY_HOURS_VALUE.format(n=_hours_number(section.total))
                lines.append(f"<b>{texts.DAILY_HOURS_TOTAL}: {esc(total)}</b>")
            continue
        for group in section.groups:
            if group.title:
                lines.append(f"<b>{esc(group.title)}</b>")
            for label, text, paragraph in group.lines:
                body = f"<b>{esc(label)}:</b> {esc(text)}" if label else esc(text)
                lines.append(body if paragraph else f"• {body}")
    lines += ["", esc(_hashtags(report))]
    return "\n".join(lines)

