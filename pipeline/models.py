from dataclasses import dataclass
from datetime import date
import html
import re


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    date_posted: date
    source: str
    category: str = ""
    work_model: str = ""
    info: str = ""
    contributor: str = ""

    @property
    def dedup_key(self) -> str:
        return self.url.split("?")[0].rstrip("/").lower()

    @property
    def location_type(self) -> str:
        """Combined location + work model for table display."""
        loc = (self.location or "").strip() or "Not Listed"
        wm = (self.work_model or "").strip()
        if not wm or wm.lower() in loc.lower():
            return loc
        return f"{loc} · {wm}"

    def to_table_row(self) -> str:
        date_str = self.date_posted.strftime("%b %d")
        role = self._md_escape(self.title) or "Open Role"
        role_link = f"[{role}]({self.url})" if self.url else role
        parts = [
            date_str,
            role_link,
            self._md_escape(self.company) or "-",
            self._md_escape(self.location_type),
            self._md_escape(self.category) or "-",
            self._md_escape(self.source) or "-",
            self._md_escape(self.info) or "-",
        ]
        return "| " + " | ".join(parts) + " |"

    def to_html_row(self) -> str:
        date_str = self.date_posted.isoformat()
        title = html.escape(self.title or "Open Role")
        company = html.escape(self.company or "-")
        loc = html.escape(self.location_type)
        category = html.escape(self.category or "-")
        source = html.escape(self.source or "-")
        info = html.escape(self.info or "-")
        url = html.escape(self.url or "#", quote=True)
        blob = f"{self.title} {self.location_type} {self.info} {self.category}".lower()
        flags: list[str] = []
        if "remote" in blob:
            flags.append("remote")
        if "new grad" in blob or "new college" in blob or "entry level" in blob:
            flags.append("newgrad")
        if "intern" in blob and "internal" not in blob:
            flags.append("intern")
        if "h1b" in blob or "sponsor" in blob:
            flags.append("visa")
        flag_attr = " ".join(flags)
        return (
            f'<tr data-date="{date_str}" data-category="{category}" data-source="{source}" '
            f'data-company="{company}" data-location="{loc}" data-info="{info}" '
            f'data-flags="{flag_attr}">'
            f'<td data-sort="{date_str}"><span class="date">{self.date_posted.strftime("%b %d")}</span></td>'
            f'<td class="role"><a class="role-link" href="{url}" rel="noopener noreferrer" target="_blank">{title}</a></td>'
            f"<td>{company}</td><td>{loc}</td><td><span class=\"pill\">{category}</span></td>"
            f"<td>{source}</td><td>{info}</td>"
            f'<td class="apply-col"><a class="apply-btn" href="{url}" rel="noopener noreferrer" target="_blank">Apply</a></td>'
            f"</tr>"
        )

    @staticmethod
    def _md_escape(value: str) -> str:
        if not value:
            return ""
        return value.replace("|", "\\|").replace("\n", " ").strip()


def normalize_info_tags(*parts: str) -> str:
    """Dedupe and join sponsorship / visa / degree tags."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        for token in re.split(r"\s*\|\s*", part.strip()):
            token = token.strip()
            if not token:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
    return " | ".join(out)
