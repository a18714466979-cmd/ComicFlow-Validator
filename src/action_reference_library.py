"""Project-local viewing bookmarks for the action editor. This module performs no network I/O."""

import re
from dataclasses import asdict, dataclass
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4


PLATFORMS = ("YouTube", "Youku", "Tencent Video")


class ReferenceError(ValueError):
    def __init__(self, chinese: str, english: str):
        super().__init__(chinese)
        self.english = english


def _unsupported():
    return ReferenceError(
        "请粘贴 YouTube、优酷或腾讯视频的 HTTPS 播放页链接。短链无法识别时，请先在浏览器打开，再复制播放页地址。",
        "Paste an HTTPS playback page from YouTube, Youku or Tencent Video. For an unsupported share link, open it in your browser and copy the playback page URL.",
    )


def _single(query, key):
    values = query.get(key, [])
    return values[0] if len(values) == 1 else ""


def _format_seconds(seconds):
    hours, tail = divmod(seconds, 3600)
    minutes, seconds = divmod(tail, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _duration(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,8}(?::[0-9]{1,2}){0,2}", value.strip()):
        raise ReferenceError("时间码请使用秒数、分:秒或时:分:秒。", "Use seconds, MM:SS or HH:MM:SS for a timecode.")
    parts = [int(part) for part in value.strip().split(":")]
    if any(part > 59 for part in parts[1:]):
        raise ReferenceError("时间码冒号后的各段须在 00 至 59 之间。", "Each timecode component after a colon must be between 00 and 59.")
    seconds = 0
    for part in parts:
        seconds = 60 * seconds + part
    return seconds


def _youtube_time(value):
    if not value:
        return ""
    if re.fullmatch(r"[0-9]{1,8}", value):
        return _format_seconds(int(value))
    match = re.fullmatch(r"(?:(\d{1,4})h)?(?:(\d{1,6})m)?(?:(\d{1,8})s)?", value, re.ASCII)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(item or 0) for item in match.groups())
        return _format_seconds(3600 * hours + 60 * minutes + seconds)
    return ""


def _video_page(url):
    if (not isinstance(url, str) or not url or len(url) > 4096 or "\\" in url
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in url)):
        raise _unsupported()
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)):
            raise _unsupported()
    except ValueError:
        raise _unsupported() from None
    host = parsed.hostname
    path = unquote(parsed.path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if host in {"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be"}:
        if host == "youtu.be":
            vid = path.removeprefix("/")
        elif path == "/watch":
            vid = _single(query, "v")
        else:
            match = re.fullmatch(r"/(?:shorts|live)/([A-Za-z0-9_-]{11})", path)
            vid = match[1] if match else ""
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            timecode = _single(query, "t") or _single(query, "start") or _single(parse_qs(parsed.fragment), "t")
            return "YouTube", f"https://www.youtube.com/watch?v={vid}", _youtube_time(timecode)
    if host in {"v.youku.com", "m.youku.com"}:
        match = re.fullmatch(r"/(?:v_show|video)/id_([A-Za-z0-9_+-]{4,128}={0,2})\.html", path)
        if match:
            return "Youku", f"https://v.youku.com/v_show/id_{match[1]}.html", ""
    if host in {"v.qq.com", "m.v.qq.com"}:
        key = r"[a-zA-Z0-9]{5,32}"
        if re.fullmatch(rf"/x/(?:page/{key}|cover/{key}(?:/{key})?)\.html", path):
            return "Tencent Video", "https://v.qq.com" + path, ""
        if path in {"/x/m/play", "/z/msite/play-short/index.html"}:
            vid, cid = _single(query, "vid"), _single(query, "cid")
            if re.fullmatch(key, vid):
                return "Tencent Video", f"https://v.qq.com/x/page/{vid}.html", ""
            if not vid and re.fullmatch(key, cid):
                return "Tencent Video", f"https://v.qq.com/x/cover/{cid}.html", ""
    raise _unsupported()


@dataclass(frozen=True)
class ActionReference:
    id: str
    title: str
    url: str
    start: str
    end: str
    notes: str

    @property
    def platform(self):
        return _video_page(self.url)[0]

    def playback_url(self):
        platform, url, _ = _video_page(self.url)
        if platform == "YouTube" and self.start:
            return f"{url}&t={_duration(self.start)}s"
        return url


def make_reference(title, url, start="", end="", notes="", *, ref_id=None):
    if (not isinstance(title, str) or not title.strip() or len(title) > 180
            or any(ord(char) < 32 or ord(char) == 127 for char in title) or len(title.splitlines()) != 1):
        raise ReferenceError("请填写单行片名或片段名，最多 180 个字符。", "Enter a single-line film or clip title (up to 180 characters).")
    if not isinstance(notes, str) or len(notes) > 1500 or "\0" in notes:
        raise ReferenceError("镜头笔记最多 1500 个字符。", "Shot notes must be text of up to 1500 characters.")
    _, canonical, shared_start = _video_page(url.strip() if isinstance(url, str) else url)
    if not isinstance(start, str) or not isinstance(end, str):
        raise ReferenceError("起止时间码需要文本。", "Start and end timecodes must be text.")
    start = start.strip() or shared_start
    end = end.strip()
    start_seconds = _duration(start) if start else 0
    end_seconds = _duration(end) if end else None
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ReferenceError("结束时间必须晚于开始时间。", "The end time must be later than the start time.")
    if ref_id is None:
        ref_id = uuid4().hex
    if not isinstance(ref_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ref_id):
        raise ReferenceError("参考条目缺少有效 ID。", "The reference needs a valid ID.")
    return ActionReference(ref_id, title.strip(), canonical,
                           _format_seconds(start_seconds) if start or end else "",
                           _format_seconds(end_seconds) if end else "", notes.strip())


def refs_from_records(records):
    if not isinstance(records, list):
        raise ReferenceError("动作参考库应为条目列表。", "The action reference library must be a list.")
    refs, seen = [], set()
    for item in records:
        if (not isinstance(item, dict) or not {"id", "title", "url"} <= item.keys()
                or item.keys() - {"id", "title", "url", "start", "end", "notes"} or item["id"] is None):
            raise ReferenceError("动作参考条目字段无效。", "Invalid fields in an action reference.")
        ref = make_reference(item["title"], item["url"], item.get("start", ""), item.get("end", ""),
                             item.get("notes", ""), ref_id=item["id"])
        if ref.id in seen:
            raise ReferenceError("动作参考条目 ID 重复。", "Duplicate action reference ID.")
        seen.add(ref.id)
        refs.append(ref)
    return refs


def refs_to_records(refs):
    return [asdict(ref) for ref in refs_from_records([asdict(ref) for ref in refs])]


def filter_references(refs, query="", platform=""):
    keywords = query.casefold().split()
    matches = []
    for ref in refs:
        source = ref.platform
        if platform and source != platform:
            continue
        content = " ".join((ref.title, ref.notes, source, ref.start, ref.end)).casefold()
        if all(word in content for word in keywords):
            matches.append(ref)
    return matches
