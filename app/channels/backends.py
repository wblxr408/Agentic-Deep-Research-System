"""Thin adapters to public endpoints and fixed, read-only upstream CLI operations."""
from __future__ import annotations

import html
import base64
import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, quote, urlencode, urlsplit

import yaml

from app.channels.execution import classify_failure, public_url
from app.channels.models import ChannelError


def decode_output(raw: str):
    # This upstream quota response has exit code zero and no structured envelope.
    if raw.lstrip().startswith("You've hit Exa's free MCP rate limit."):
        raise ChannelError("rate_limited")
    try:
        return json.loads(raw)
    except ValueError:
        pass
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if rows:
            return rows
    except ValueError:
        pass
    try:
        value = yaml.safe_load(raw)
        if isinstance(value, (dict, list)):
            return value
    except yaml.YAMLError:
        pass
    # Exa mcporter may emit text containing JSON or Markdown; only explicit URLs count.
    matches = list(re.finditer(r"(?:Title:\s*(?P<title>[^\n]+)\n)?(?:URL:|Source:)\s*(?P<url>https://[^\s]+)(?P<body>.*?)(?=\n(?:Title:|URL:|Source:)|\Z)", raw, re.S))
    if matches:
        return [{"url": m["url"], "title": (m["title"] or "Source").strip(), "content": m["body"].strip()} for m in matches]
    raise ChannelError("invalid_output")


def rows(payload, depth=0) -> list[dict]:
    if depth > 16:
        raise ChannelError("invalid_output")
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    if payload.get("success") is False or payload.get("ok") is False or payload.get("error") or payload.get("isError"):
        raise ChannelError(classify_failure(str(payload.get("error") or payload.get("message") or payload.get("content") or "")) or "upstream_error")
    if isinstance(payload.get("code"), int) and payload["code"] != 0:
        raise ChannelError({-101: "auth_required", 36: "account_risk", 9: "rate_limited", 37: "account_risk"}.get(payload["code"], "upstream_error"))
    for key in ("items", "results", "feeds", "posts", "tweets", "jobs", "users", "jobList", "entries", "rows", "data", "zpData", "result", "feed"):
        if isinstance(payload.get(key), (list, dict)):
            return rows(payload[key], depth+1)
    if isinstance(payload.get("post"), dict):
        comments = []
        def append_comments(values, level=0):
            for comment in values[:100]:
                if not isinstance(comment, dict):
                    continue
                comments.append(comment)
                if level < 5 and isinstance(comment.get("replies"), list):
                    append_comments(comment["replies"], level+1)
        append_comments(payload.get("comments", []))
        return [payload["post"], *comments]
    if isinstance(payload.get("video"), dict):
        return [payload["video"]]
    if isinstance(payload.get("content"), list):
        merged = []
        for block in payload["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                merged.extend(rows(decode_output(block.get("text", "")), depth+1))
        return merged
    return [payload]


def clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return html.unescape(re.sub(r"<[^>]+>", "", str(value))).strip()


def normalize(payload, channel, *, source_url=None) -> list[dict]:
    result = []
    for row in rows(payload):
        card = row.get("noteCard") or row.get("note_card") or {}
        if isinstance(card, dict):
            row = {**row, **card}
        nested = row.get("note")
        if isinstance(nested, dict):
            row = {**row, **nested}
        if source_url and isinstance(row.get("field"), str) and row.get("value") is not None:
            row = {**row, "content": row["field"] + ": " + clean(row["value"])}
        url = row.get("html_url") or row.get("webpage_url") or row.get("note_url") or row.get("url") or row.get("link") or row.get("source_url")
        if row.get("permalink") and (not url or channel == "reddit"):
            url = row["permalink"] if row["permalink"].startswith("https://") else "https://www.reddit.com" + row["permalink"]
        if not url and channel == "twitter" and row.get("id") and row.get("username"):
            url = f"https://x.com/{quote(str(row['username']), safe='')}/status/{quote(str(row['id']), safe='')}"
        if not url and channel == "xiaohongshu" and row.get("id") and (row.get("xsecToken") or row.get("xsec_token")):
            url = "https://www.xiaohongshu.com/explore/" + quote(str(row["id"]), safe="") + "?" + urlencode({"xsec_token": row.get("xsecToken") or row.get("xsec_token"), "xsec_source": "pc_search"})
        if not url and channel == "instagram" and row.get("username"):
            url = f"https://www.instagram.com/{quote(str(row['username']), safe='')}/"
        if not url and channel == "boss" and row.get("encryptJobId"):
            url = f"https://www.zhipin.com/job_detail/{quote(str(row['encryptJobId']), safe='')}.html"
        if not url and channel == "xueqiu" and row.get("symbol"):
            url = "https://xueqiu.com/S/" + quote(str(row["symbol"]), safe="")
        if not url and channel == "bilibili" and row.get("bvid"):
            url = "https://www.bilibili.com/video/" + quote(str(row["bvid"]), safe="")
        url = url or source_url
        if not isinstance(url, str):
            continue
        try:
            public_url(url)
        except ChannelError:
            continue
        title = clean(row.get("title") or row.get("displayTitle") or row.get("full_name") or row.get("name") or row.get("jobName") or row.get("username") or row.get("text", "")[:100])
        content = "\n".join((f"{k}: " if k in ("price", "changePercent", "salaryDesc", "date", "likes", "friends", "followers") else "") + clean(row[k]) for k in ("content", "text", "full_text", "selftext", "description", "desc", "snippet", "biography", "headline", "summary", "experiences", "jobDescription", "postDescription", "brandName", "salaryDesc", "current", "price", "changePercent", "transcript", "caption", "body", "date", "likes", "friends", "followers") if row.get(k) is not None)
        if not title and not content:
            continue
        result.append({"url": url, "title": title or url, "content": content or title})
    if source_url:
        # A read adapter often emits one row per caption, comment or post. Keep
        # the complete returned text under its actual requested source.
        grouped = {}
        for item in result:
            previous = grouped.get(item["url"])
            if previous:
                previous["content"] += "\n" + item["content"]
            else:
                grouped[item["url"]] = item
        return list(grouped.values())
    return result


class Backends:
    def __init__(self, commands, http, legacy_search=None):
        self.commands, self.http, self.legacy_search = commands, http, legacy_search

    def collect(self, request, backend, config, timeout, budget):
        channel, operation, query, limit = request.channel, request.operation, request.query, request.limit
        def command(argv, secrets=()):
            from app.model_scope import host_credentials_allowed
            if not host_credentials_allowed():
                raise ChannelError('administrator_required')
            return self.commands.run(argv, timeout=budget.take(), secrets=secrets)
        def get(url):
            return self.http.get(url, timeout=budget.remaining(),on_request=budget.take)
        source = query if operation == "read" and query.startswith("https://") else None
        if backend == "duckduckgo":
            if operation != "search":
                raise ChannelError("unsupported_operation")
            from app.agents.search import SearchAgent
            parser = SearchAgent()
            page = get("https://html.duckduckgo.com/html/?" + urlencode({"q": query}))
            if "anomaly.js" in page:
                # Do not solve or resubmit a challenge; another search engine
                # can answer the query without accessing this blocked engine.
                raise ChannelError("access_denied")
            values = parser._parse_duckduckgo_html(page, query)
            if not values:
                payload = decode_output(get("https://api.duckduckgo.com/?" + urlencode({"q": query, "format": "json", "no_html": 1})))
                values = []
                if payload.get("AbstractText") and payload.get("AbstractURL"):
                    values.append({"url": payload["AbstractURL"], "title": payload.get("Heading", query), "snippet": payload["AbstractText"]})
                values.extend({"url": t["FirstURL"], "title": payload.get("Heading", query), "snippet": t["Text"]} for t in payload.get("RelatedTopics", []) if t.get("FirstURL") and t.get("Text"))
            return normalize([v.model_dump() if hasattr(v, "model_dump") else v for v in values], channel)
        if backend == "bing-rss":
            if operation != "search":
                raise ChannelError("unsupported_operation")
            raw = get("https://www.bing.com/search?" + urlencode({"q": query, "format": "rss", "mkt": "en-US"}))
            if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                raise ChannelError("invalid_output")
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                raise ChannelError("invalid_output") from None
            return normalize([{"url": item.findtext("link"), "title": item.findtext("title"), "description": item.findtext("description")} for item in root.findall("./channel/item")], channel)
        if backend == "jina":
            if operation != "read":
                raise ChannelError("unsupported_operation")
            public_url(query, resolve=True)
            text = get("https://r.jina.ai/" + query)
            if not text.strip() or "Markdown Content:" not in text:
                raise ChannelError("empty_content")
            body = text.split("Markdown Content:", 1)[1].strip()
            title = text.split("Title:", 1)[-1].splitlines()[0].strip()
            return [{"url": query, "title": title, "content": body}] if body else []
        if backend == "xiaoyuzhou-page":
            if operation != "read" or not re.fullmatch(r"/(podcast|episode)/[a-fA-F0-9]{24}/?", urlsplit(query).path):
                raise ChannelError("unsupported_input")
            from app.channels.pages import xiaoyuzhou_page
            return xiaoyuzhou_page(get(query), query)
        if backend == "github-api":
            if operation == "search":
                raw = get("https://api.github.com/search/repositories?" + urlencode({"q": query, "per_page": limit}))
            else:
                parts = urlsplit(query).path.strip("/").split("/")
                if len(parts) != 2:
                    raise ChannelError("unsupported_input")
                endpoint = "https://api.github.com/repos/" + "/".join(quote(p, safe="") for p in parts)
                metadata = decode_output(get(endpoint))
                readme = decode_output(get(endpoint + "/readme"))
                try:
                    if readme.get("encoding") != "base64":
                        raise ValueError
                    body = base64.b64decode(readme.get("content", "").replace("\n", ""), validate=True).decode("utf-8")
                except (ValueError, UnicodeError, AttributeError):
                    raise ChannelError("invalid_output") from None
                metadata["content"] = body
                return normalize(metadata, channel, source_url=source)
            return normalize(decode_output(raw), channel, source_url=source)
        if backend == "feed":
            feeds = [query] if operation == "read" else config.feeds
            if not feeds:
                raise ChannelError("configuration_required")
            output = []
            for feed in feeds:
                raw = get(feed)
                if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
                    raise ChannelError("invalid_output")
                try:
                    root = ET.fromstring(raw)
                except ET.ParseError:
                    raise ChannelError("invalid_output") from None
                for item in [*root.findall(".//item"), *root.findall(".//{http://www.w3.org/2005/Atom}entry")][:100]:
                    def text(tag):
                        found = item.find(tag)
                        if found is None:
                            found = item.find("{http://www.w3.org/2005/Atom}" + tag)
                        return "" if found is None else "".join(found.itertext()).strip()
                    title = text("title")
                    body = text("description") or text("summary") or text("content")
                    link = text("link")
                    if not link:
                        element = item.find("{http://www.w3.org/2005/Atom}link")
                        link = element.get("href", "") if element is not None else ""
                    if operation == "read" or query.lower() in (title + " " + body).lower():
                        output.extend(normalize({"url": link, "title": title, "content": body}, channel))
                    if len(output) >= limit:
                        return output
            return output
        if backend == "v2ex-api":
            if operation == "read":
                match = re.fullmatch(r"/t/(\d+)/?", urlsplit(query).path)
                if not match:
                    raise ChannelError("unsupported_input")
                topic_id = match[1]
                topics = rows(decode_output(get("https://www.v2ex.com/api/topics/show.json?id=" + topic_id)))
                replies = rows(decode_output(get("https://www.v2ex.com/api/replies/show.json?topic_id=" + topic_id)))
                if topics:
                    topics[0]["content"] = clean(topics[0].get("content")) + "\n" + "\n".join(clean(r.get("content")) for r in replies)
                return normalize(topics, channel, source_url=query)
            topics = rows(decode_output(get("https://www.v2ex.com/api/topics/latest.json")))
            return normalize([r for r in topics if query.lower() in (clean(r.get("title")) + clean(r.get("content"))).lower()], channel)
        if backend == "bilibili-api":
            if operation == "search":
                raw = get("https://api.bilibili.com/x/web-interface/search/type?" + urlencode({"search_type": "video", "keyword": query}))
            else:
                bvid = self._bvid(query)
                raw = get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid)
            items = normalize(decode_output(raw), channel, source_url=source)
            if operation == "read" and items:
                for item in items:
                    item["content"] += "\n字幕未获取；以下内容仅为公开视频元数据。"
                raise ChannelError("no_transcript", partial_items=items)
            return items
        if backend == "gh":
            if operation == "read":
                raw = command(["gh", "repo", "view", query], ("GH_TOKEN", "GITHUB_TOKEN"))
                return [{"url": query, "title": urlsplit(query).path.strip("/"), "content": raw.strip()}] if raw.strip() else []
            return normalize(decode_output(command(["gh", "search", "repos", query, "--limit", str(limit), "--json", "name,description,url"], ("GH_TOKEN", "GITHUB_TOKEN"))), channel)
        if backend == "yt-dlp":
            fields = ["id", "webpage_url", "title", "description"]
            if operation == "read":
                fields += ["subtitles", "automatic_captions"]
            template = "{" + ",".join(json.dumps(field) + ":%(" + field + ")j" for field in fields) + "}"
            raw = command(["yt-dlp", "--ignore-config", "--no-warnings", "--skip-download", "--print", template, "--no-playlist", "--", query if operation == "read" else f"ytsearch{limit}:{query}"])
            payload = decode_output(raw)
            if operation == "read":
                for video in rows(payload):
                    transcript = ""
                    captions = video.get("subtitles") or video.get("automatic_captions") or {}
                    for language in ("zh-Hans", "zh", "en", *captions):
                        candidates = captions.get(language) or []
                        caption = next((c for c in candidates if c.get("ext") == "json3"), None)
                        if caption:
                            data = decode_output(get(caption["url"]))
                            transcript = "\n".join("".join(s.get("utf8", "") for s in e.get("segs", [])) for e in data.get("events", []))
                            break
                    video["transcript"] = transcript.strip() or "字幕未获取；以下内容仅为公开视频元数据。"
            items = normalize(payload, channel, source_url=source)
            if operation == "read" and not any(v.get("transcript") and "字幕未获取" not in v["transcript"] for v in rows(payload)):
                raise ChannelError("no_transcript", partial_items=items)
            return items
        if backend == "transcribe":
            if operation != "read" or not config.transcription_provider:
                raise ChannelError("configuration_required")
            # Provider must be deliberately configured in Agent-Reach; research LLM keys are never forwarded.
            raw = command(["agent-reach", "transcribe", query, "--provider", config.transcription_provider])
            return [{"url": query, "title": "音频转录", "content": raw.strip()}] if raw.strip() else []
        if backend == "exa-mcp":
            argv = ["mcporter", "call", "exa.web_search_exa", "query=" + query, "numResults=" + str(limit)]
        elif backend == "linkedin-mcp":
            if os.environ.get("CHANNELS_LINKEDIN_SESSION_READY", "").lower() != "true":
                raise ChannelError("auth_required")
            if operation == "search":
                argv = ["mcporter", "call", "linkedin.search_jobs", "keywords=" + query, "max_pages=1"]
            else:
                parts = urlsplit(query).path.strip("/").split("/")
                if len(parts) != 2 or parts[0] not in ("in", "company"):
                    raise ChannelError("unsupported_input")
                function, key = ("get_person_profile", "linkedin_username") if parts[0] == "in" else ("get_company_profile", "company_name")
                argv = ["mcporter", "call", "linkedin." + function, key + "=" + parts[1]]
        elif backend == "xhs-mcp":
            if operation == "search":
                argv = ["mcporter", "call", "xiaohongshu.search_feeds", "keyword=" + query]
            else:
                token = parse_qs(urlsplit(query).query).get("xsec_token", [""])[0]
                if not token:
                    raise ChannelError("unsupported_input")
                argv = ["mcporter", "call", "xiaohongshu.get_feed_detail", "feed_id=" + urlsplit(query).path.split("/")[-1], "xsec_token=" + token]
        elif backend == "twitter":
            if not os.environ.get("TWITTER_AUTH_TOKEN") or not os.environ.get("TWITTER_CT0"):
                raise ChannelError("auth_required")
            argv = ["twitter", "search", query, "-n", str(limit), "--json"] if operation == "search" else ["twitter", "tweet", query, "--json"]
        elif backend == "rdt":
            if operation == "read":
                match = re.search(r"/comments/([a-zA-Z0-9]+)(?:/|$)", urlsplit(query).path)
                if not match:
                    raise ChannelError("unsupported_input")
                argv = ["rdt", "read", match[1], "--limit", str(limit), "--json"]
            else:
                argv = ["rdt", "search", query, "--limit", str(limit), "--json"]
        elif backend == "bili":
            argv = ["bili", "search", query, "--type", "video", "-n", str(limit), "--json"] if operation == "search" else ["bili", "video", self._bvid(query), "--json"]
        elif backend == "xhs":
            argv = ["xhs", "search" if operation == "search" else "read", query, "--json"]
        elif backend == "boss":
            if operation != "search":
                raise ChannelError("unsupported_operation")
            argv = ["boss", "--browser-source", "existing-browser", "--cdp-url", "http://localhost:9222", "--json", "search", query, "--page", "1"]
        elif backend == "opencli":
            op = "search"
            value = query
            if operation == "read":
                op = {"twitter": "article", "reddit": "read", "xiaohongshu": "note", "facebook": "profile", "instagram": "user", "youtube": "transcript", "bilibili": "subtitle", "xueqiu": "stock"}[channel]
                if channel == "bilibili":
                    value = self._bvid(query)
                if channel == "instagram":
                    value = urlsplit(query).path.strip("/").split("/")[0]
                if channel == "facebook":
                    value = urlsplit(query).path.strip("/").split("/")[0]
                    if not value or value == "profile.php":
                        raise ChannelError("unsupported_input")
                if channel == "xueqiu":
                    value = urlsplit(query).path.split("/")[-1]
            argv = ["opencli", channel, op, value, "-f", "json"]
        else:
            raise ChannelError("unsupported_backend")
        secret_names = ("TWITTER_AUTH_TOKEN", "TWITTER_CT0") if backend == "twitter" else (("OPENCLI_PROFILE", "OPENCLI_CDP_ENDPOINT") if backend == "opencli" else ())
        payload = decode_output(command(argv, secret_names))
        # Transcript arrays carry text but no individual URLs; bind to requested video.
        items = normalize(payload, channel, source_url=source)
        if backend == "bili" and operation == "read" and items:
            for item in items:
                item["content"] += "\n字幕未获取；以下内容仅为公开视频元数据。"
            raise ChannelError("no_transcript", partial_items=items)
        return items

    @staticmethod
    def _bvid(url):
        match = re.search(r"/video/(BV[a-zA-Z0-9]+)", urlsplit(url).path)
        if not match:
            raise ChannelError("unsupported_input")
        return match[1]
