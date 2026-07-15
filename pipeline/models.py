from dataclasses import dataclass, field
from datetime import date


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

    @property
    def dedup_key(self) -> str:
        return self.url.split("?")[0].rstrip("/").lower()

    def to_table_row(self) -> str:
        date_str = self.date_posted.strftime("%b %d")
        role_link = f"[{self.title}]({self.url})" if self.url else self.title
        parts = [
            date_str,
            role_link,
            self.company,
            self.location,
            self.category,
            self.work_model or "-",
            self.source,
            self.info or "-",
        ]
        return "| " + " | ".join(parts) + " |"
