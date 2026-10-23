"""Read public page data without executing scripts or fetching audio."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.channels.models import ChannelError


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.script = False
        self.data = []
        self.text = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self.script = True
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li"):
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag == "script":
            self.script = False
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li"):
            self.text.append("\n")

    def handle_data(self, data):
        if self.script:
            self.data.append(data)
        elif not self.hidden:
            self.text.append(data)


def page_text(value):
    if not isinstance(value, str):
        return ""
    parser = PageParser()
    parser.feed(value)
    return "\n".join(line.strip() for line in "".join(parser.text).splitlines() if line.strip())


def xiaoyuzhou_page(raw, source):
    parser = PageParser()
    parser.feed(raw)
    try:
        props = json.loads("".join(parser.data))["props"]["pageProps"]
        kind = urlsplit(source).path.strip("/").split("/")[0]
        record = props[kind]
        if not isinstance(record, dict):
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ChannelError("invalid_output") from None
    parts = [page_text(record.get(key)) for key in ("description", "shownotes")]
    episodes = record.get("episodes") or []
    if isinstance(episodes, list):
        for episode in episodes[:20]:
            if not isinstance(episode, dict) or not re.fullmatch(r"[a-fA-F0-9]{24}", str(episode.get("eid", ""))):
                continue
            parts.append(f"{page_text(episode.get('title'))}\nhttps://www.xiaoyuzhoufm.com/episode/{episode['eid']}\n{page_text(episode.get('description'))}")
    content = "\n\n".join(part for part in parts if part)
    if not content:
        return []
    return [{"url": source, "title": page_text(record.get("title")) or source,
             "content": "公开节目介绍 / shownotes（音频转录未获取）\n\n" + content}]
