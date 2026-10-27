"""Platform capabilities and upstream choices are trusted server-side data."""
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    label: str
    backends: tuple[str, ...]
    operations: tuple[str, ...] = ("search", "read")
    domains: tuple[str, ...] = ()
    setup: str = ""
    optional_backends: tuple[str, ...] = ()


CATALOG = {s.name: s for s in (
    ChannelSpec("web", "网页", ("duckduckgo", "bing-rss", "exa-mcp", "jina"), setup="DuckDuckGo / Bing RSS 搜索，Exa MCP 备选；网页正文经 Jina Reader 读取"),
    ChannelSpec("exa", "Exa 全网搜索", ("exa-mcp",), ("search",), setup="安装 mcporter 并配置名为 exa 的 MCP 服务"),
    ChannelSpec("github", "GitHub", ("github-api",), domains=("github.com",), setup="公开仓库经官方 API；个人授权在账号页单独启用"),
    ChannelSpec("youtube", "YouTube", ("yt-dlp", "opencli"), domains=("youtube.com", "youtu.be"), setup="安装 yt-dlp；字幕备选需要 OpenCLI", optional_backends=("transcribe",)),
    ChannelSpec("bilibili", "B站", ("bili", "opencli", "bilibili-api"), domains=("bilibili.com",), setup="bili 搜索/详情；OpenCLI 读取字幕"),
    ChannelSpec("rss", "RSS / Atom", ("feed",), setup="配置公开 HTTPS feed URL，或直接读取 feed URL"),
    ChannelSpec("v2ex", "V2EX", ("v2ex-api",), domains=("v2ex.com",), setup="搜索在公开最新主题内筛选；链接读取主题与回复"),
    ChannelSpec("twitter", "Twitter / X", ("twitter", "opencli"), domains=("x.com", "twitter.com"), setup="twitter 用显式环境 Token；或已有 OpenCLI 登录态"),
    ChannelSpec("reddit", "Reddit", ("opencli",), domains=("reddit.com",), setup="使用已有 OpenCLI 登录态；存量 rdt 仅手动选择，其上游可能自动读取浏览器 Cookie，需在隔离环境使用", optional_backends=("rdt",)),
    ChannelSpec("xiaohongshu", "小红书", ("opencli", "xhs-mcp"), domains=("xiaohongshu.com",), setup="已有 OpenCLI 登录态；MCP 使用显式配置；存量 xhs 仅手动选择，需确认上游凭据行为", optional_backends=("xhs",)),
    ChannelSpec("facebook", "Facebook", ("opencli",), domains=("facebook.com",), setup="已有 Chrome / OpenCLI 登录态"),
    ChannelSpec("instagram", "Instagram", ("opencli",), domains=("instagram.com",), setup="搜索用户；读取用户名对应最近帖子；已有 OpenCLI 登录态"),
    ChannelSpec("linkedin", "LinkedIn", ("linkedin-mcp", "jina"), domains=("linkedin.com",), setup="专用 MCP profile 手动登录后导出 CHANNELS_LINKEDIN_SESSION_READY=true；公开页面可 Jina 读取"),
    ChannelSpec("boss", "Boss直聘", ("boss",), ("search",), domains=("zhipin.com",), setup="已登录专用 Chrome / 本地 CDP；严格 existing-browser 模式"),
    ChannelSpec("xueqiu", "雪球", ("opencli",), domains=("xueqiu.com",), setup="已有 OpenCLI 登录态；读取股票 URL 或代码"),
    ChannelSpec("xiaoyuzhou", "小宇宙", ("xiaoyuzhou-page", "jina"), ("read",), domains=("xiaoyuzhoufm.com",), setup="原站公开节目介绍/单集 shownotes；音频转录需显式配置", optional_backends=("transcribe",)),
)}

ALIASES = {"x": "twitter", "小红书": "xiaohongshu", "推特": "twitter", "b站": "bilibili",
           "bilibili": "bilibili", "雪球": "xueqiu", "小宇宙": "xiaoyuzhou", "boss直聘": "boss"}


def route_query(query: str) -> tuple[str, str, str]:
    """Explicit platform prefixes and exact hostname boundaries, never fuzzy URLs."""
    prefix, sep, value = query.partition(":")
    name = ALIASES.get(prefix.strip().lower(), prefix.strip().lower())
    if sep and name in CATALOG:
        operation = "read" if value.strip().startswith("https://") else "search"
        return name, operation, value.strip()
    if query.strip().startswith(("https://", "http://")):
        host = (urlsplit(query.strip()).hostname or "").lower()
        for spec in CATALOG.values():
            if any(host == d or host.endswith("." + d) for d in spec.domains):
                return spec.name, "read", query.strip()
        return "web", "read", query.strip()
    return "web", "search", query.strip()
