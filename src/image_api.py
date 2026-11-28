"""Image generation and editing using documented provider requests."""

import base64
import hmac
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from uuid import uuid4

from .vision import NoRedirect


TEXT = "文生图"
REFERENCE = "参考图生图"
EDIT = "局部编辑"
MAX_IMAGE_BYTES = 32 * 1024**2
MAX_REPLY_BYTES = 48 * 1024**2
MAX_UPLOAD_BYTES = 40 * 1024**2


@dataclass(frozen=True)
class ImageProvider:
    base: str
    model: str
    adapter: str
    references: int = 0
    edits: bool = False
    asynchronous: bool = False

    @property
    def modes(self):
        return (TEXT,) + ((REFERENCE,) if self.references else ()) + ((EDIT,) if self.edits else ())


IMAGE_PROVIDERS = {
    "火山方舟 Seedream": ImageProvider("https://ark.cn-beijing.volces.com/api/v3", "doubao-seedream-5-5-261028", "ark", 10, True),
    "OpenAI GPT Image": ImageProvider("https://api.openai.com/v1", "gpt-image-2", "openai", 16, True),
    "Google Gemini": ImageProvider("https://generativelanguage.googleapis.com/v1beta", "gemini-nano-banana-2.1", "gemini", 14, True),
    "阿里云百炼 千问": ImageProvider("", "qwen-image-3.0-pro", "dashscope", 3, True),
    "阿里云百炼 万相": ImageProvider("", "wan2.7-image-pro", "dashscope", 9, True),
    "xAI Grok Imagine": ImageProvider("https://api.x.ai/v1", "grok-imagine-image-2.0", "xai", 1, True),
    "智谱 CogView": ImageProvider("https://open.bigmodel.cn/api/paas/v4", "cogview-4-250304", "glm"),
    "腾讯云混元": ImageProvider("https://hunyuan.tencentcloudapi.com", "SubmitHunyuanImageJob", "tencent", 1, False, True),
    "百度千帆": ImageProvider("https://qianfan.baidubce.com/v2", "qwen-image", "baidu"),
    "硅基流动": ImageProvider("https://api.siliconflow.cn/v1", "black-forest-labs/FLUX.1-schnell", "silicon"),
    "OpenRouter": ImageProvider("https://openrouter.ai/api/v1", "bytedance-seed/seedream-4.5", "openrouter", 10, True),
    "自定义 OpenAI Images 兼容": ImageProvider("", "", "openai", 16, True),
}


@dataclass(frozen=True)
class ImageSettings:
    provider: str
    base: str
    model: str
    key: str = field(repr=False)
    secret_id: str = field(default="", repr=False)


@dataclass(frozen=True)
class ImageReply:
    results: tuple[bytes, ...] = ()
    task_id: str = ""
    request_id: str = ""
    status: str = "ready"


class ImageRequestError(ValueError):
    def __init__(self, message: str, *, uncertain: bool = False, request_id: str = ""):
        super().__init__(message)
        self.uncertain = uncertain
        self.request_id = request_id


def checked_url(url: str, *, output: bool = False) -> str:
    if not isinstance(url, str) or any(ord(char) < 33 or char == "\\" for char in url):
        raise ValueError("请输入有效的 HTTPS 基础地址。")
    parsed = urlsplit(url)
    if (parsed.scheme == "http" and output and parsed.hostname and parsed.hostname.endswith(".bcebos.com")
            and parsed.port in (None, 80)):
        parsed = parsed._replace(scheme="https", netloc=parsed.hostname)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or (parsed.query and not output)):
        raise ValueError("请输入有效的 HTTPS 基础地址。")
    if output:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global
                                or ipaddress.ip_address(item[4][0]).is_multicast for item in addresses):
            raise ValueError("服务返回的图片下载地址不可用。")
    return parsed.geturl()


def json_request(url, body, headers):
    return Request(url, data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                   headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
                   method="POST")


def tencent_request(settings: ImageSettings, action: str, body: dict, timestamp: int | None = None) -> Request:
    target = "https://hunyuan.tencentcloudapi.com"
    if settings.base.rstrip("/") != target:
        raise ValueError("请使用腾讯云混元官方基础地址。")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", settings.secret_id) or not settings.key:
        raise ValueError("腾讯云混元需要 SecretId 和 SecretKey。")
    stamp = int(time.time()) if timestamp is None else timestamp
    date = datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y-%m-%d")
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    content_type = "application/json; charset=utf-8"
    host = "hunyuan.tencentcloudapi.com"
    signed = "content-type;host;x-tc-action"
    canonical = (f"POST\n/\n\ncontent-type:{content_type}\nhost:{host}\nx-tc-action:{action.lower()}\n"
                 f"\n{signed}\n{sha256(data).hexdigest()}")
    scope = f"{date}/hunyuan/tc3_request"
    algorithm = "TC3-HMAC-SHA256"
    signature_data = f"{algorithm}\n{stamp}\n{scope}\n{sha256(canonical.encode()).hexdigest()}"
    signing_key = ("TC3" + settings.key).encode()
    for value in (date, "hunyuan", "tc3_request"):
        signing_key = hmac.digest(signing_key, value.encode(), "sha256")
    signature = hmac.digest(signing_key, signature_data.encode(), "sha256").hex()
    auth = (f"{algorithm} Credential={settings.secret_id}/{scope}, SignedHeaders={signed}, Signature={signature}")
    return Request(target + "/", data=data, headers={
        "Authorization": auth, "Content-Type": content_type, "Host": host, "X-TC-Action": action,
        "X-TC-Version": "2023-09-01", "X-TC-Region": "ap-guangzhou", "X-TC-Timestamp": str(stamp),
    }, method="POST")


def data_url(asset: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(asset).decode("ascii")


def multipart_request(url, headers, body, references, mask):
    boundary = f"comicflow-{uuid4().hex}"
    parts = []
    for key, value in body.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    files = [("image" if len(references) == 1 else "image[]", f"reference-{n}.png", data)
             for n, data in enumerate(references, 1)]
    if mask:
        files.append(("mask", "mask.png", mask))
    for name, filename, data in files:
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"'
                      '\r\nContent-Type: image/png\r\n\r\n').encode("ascii"))
        parts.extend((data, b"\r\n"))
    parts.append(f"--{boundary}--\r\n".encode("ascii"))
    return Request(url, data=b"".join(parts), headers={**headers,
                   "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")


def build_image_request(settings: ImageSettings, mode: str, prompt: str, references: tuple[bytes, ...] = (),
                        *, edit_box: tuple[int, int, int, int] | None = None, mask: bytes = b"",
                        preview: bool = False, aspect_ratio: str = "16:9") -> Request:
    """Build the provider payload, leaving an offline preview unsigned."""
    if aspect_ratio not in {"16:9", "9:16"}:
        raise ValueError("图像请求仅支持 16:9 或 9:16。")

    def dimensions(width, height, separator="x"):
        first, second = (height, width) if aspect_ratio == "9:16" else (width, height)
        return f"{first}{separator}{second}"

    provider = IMAGE_PROVIDERS[settings.provider]
    adapter = provider.adapter
    base = checked_url(settings.base.rstrip("/"))
    if not settings.model:
        raise ValueError("请填写图像模型 ID。")
    if not preview and (not settings.key or not all(33 <= ord(char) <= 126 for char in settings.key)):
        raise ValueError("请填写有效的 API 密钥。")
    if not prompt.strip():
        raise ValueError("请填写本次图片提示词。")
    if mode not in provider.modes:
        raise ValueError("所选接口未提供该生图模式。")
    if (mode == TEXT and references) or (mode == REFERENCE and not 1 <= len(references) <= provider.references):
        raise ValueError(f"请按所选模式选择批准参考图。本接口最多 {provider.references} 张。")
    if mode == EDIT and (not 1 <= len(references) <= provider.references or not edit_box):
        raise ValueError("局部编辑需要批准原图、编辑范围，以及可选的后续参考图。")
    if sum(map(len, references)) + len(mask) > MAX_UPLOAD_BYTES:
        raise ValueError("参考图合计超过本地请求大小限制。请选择更少的批准参考图。")
    headers = {} if preview else {"Authorization": f"Bearer {settings.key}"}
    body = {"model": settings.model, "prompt": prompt}
    path = "/images/generations"
    if adapter == "openai":
        width = dimensions(2048, 1152) if settings.model.startswith("gpt-image-2") else "auto"
        body.update(size=width, n=1, output_format="png")
        if references:
            return multipart_request(base + "/images/edits", headers, body, references, mask if mode == EDIT else b"")
    elif adapter == "ark":
        body.update(response_format="b64_json", size=dimensions(2560, 1440))
        if references:
            urls = [data_url(item) for item in references]
            body["image"] = urls[0] if len(urls) == 1 else urls
    elif adapter == "gemini":
        parts = [{"type": "text", "text": prompt}]
        parts.extend({"type": "image", "mime_type": "image/png", "data": base64.b64encode(item).decode("ascii")}
                     for item in references)
        body = {"model": settings.model, "input": parts, "store": False,
                "response_format": {"type": "image", "mime_type": "image/png", "aspect_ratio": aspect_ratio, "image_size": "2K"}}
        headers = {"Api-Revision": "2026-05-20"}
        if not preview:
            headers["x-goog-api-key"] = settings.key
        path = "/interactions"
    elif adapter == "dashscope":
        content = [{"image": data_url(item)} for item in references] + [{"text": prompt}]
        parameters = {"size": dimensions(2048, 1152, "*"), "n": 1}
        if settings.model.startswith("wan2.7-image"):
            if edit_box:
                parameters["bbox_list"] = [[list(edit_box)], *([] for _ in references[1:])]
        else:
            parameters["prompt_extend"] = False
            if settings.model.startswith("qwen-image-3.0"):
                parameters["response_format"] = "b64_json"
        body = {"model": settings.model, "input": {"messages": [{"role": "user", "content": content}]},
                "parameters": parameters}
        path = "/services/aigc/multimodal-generation/generation"
    elif adapter == "xai":
        body.update(response_format="b64_json", aspect_ratio=aspect_ratio)
        if references:
            body["image"] = {"url": data_url(references[0]), "type": "image_url"}
            path = "/images/edits"
    elif adapter == "tencent":
        if base != provider.base:
            raise ValueError("请使用腾讯云混元官方基础地址。")
        payload = {"Prompt": prompt, "Resolution": dimensions(1280, 720, ":"), "Revise": 0}
        if references:
            encoded = base64.b64encode(references[0]).decode("ascii")
            if len(encoded) >= 8_000_000:
                raise ValueError("腾讯云混元的单张参考图编码须小于 8 MB。")
            payload["ContentImage"] = {"ImageBase64": encoded}
        if preview:
            return json_request(base + "/", payload, {"X-TC-Action": "SubmitHunyuanImageJob"})
        return tencent_request(settings, "SubmitHunyuanImageJob", payload)
    elif adapter == "openrouter":
        body.update(aspect_ratio=aspect_ratio, resolution="2K", response_format="b64_json")
        if references:
            body["input_references"] = [{"type": "image_url", "image_url": {"url": data_url(item)}} for item in references]
        path = "/images"
    elif adapter == "silicon":
        body["image_size"] = dimensions(1024, 576)
    else:
        body["size"] = dimensions(1344, 756) if adapter == "glm" else dimensions(2048, 1152)
    return json_request(base + path, body, headers)


def safe_request_id(value, request: Request) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        return ""
    credentials = (request.get_header("Authorization", ""), request.get_header("X-goog-api-key", ""))
    if any(value in credential for credential in credentials):
        return ""
    bearer = credentials[0].removeprefix("Bearer ")
    if any(secret and secret in value for secret in (bearer, credentials[1])):
        return ""
    return value


def response_request_id(headers, request: Request) -> str:
    if headers is None:
        return ""
    value = headers.get("x-request-id") or headers.get("request-id") or headers.get("x-siliconcloud-trace-id")
    return safe_request_id(value, request)


def read_bytes(request: Request, limit: int) -> tuple[bytes, str]:
    request_id = ""
    try:
        with build_opener(NoRedirect()).open(request, timeout=150) as response:
            request_id = response_request_id(response.headers, request)
            raw = response.read(limit + 1)
    except HTTPError as exc:
        request_id = response_request_id(exc.headers, request)
        exc.close()
        uncertain = exc.code >= 500 or exc.code == 408
        guidance = {
            401: "请核对 API Key 是否有效及所属服务。",
            403: "请核对当前账户的模型或接入点调用权限。",
            404: "请核对接口地址、模型 ID 或接入点是否已开通。",
            413: "请求内容过大，请检查参考图的大小和数量。",
            429: "请检查服务商的调用频率、配额和服务状态，再决定何时重试。",
        }
        hint = ("请先在服务商后台核对受理状态，再决定是否重试。" if uncertain
                else guidance.get(exc.code, "请核对接口、模型和请求参数。"))
        raise ImageRequestError(f"服务返回 HTTP {exc.code}。{hint}", uncertain=uncertain,
                                request_id=request_id) from None
    except (URLError, TimeoutError, OSError):
        raise ImageRequestError("连接失败或超时，请先在服务商后台核对请求。",
                                uncertain=True, request_id=request_id) from None
    if len(raw) > limit:
        raise ImageRequestError("服务返回的数据超过本地大小限制。", uncertain=True, request_id=request_id)
    return raw, request_id


def load_result(value: str) -> bytes:
    if value.startswith(("https://", "http://")):
        url = checked_url(value, output=True)
        return read_bytes(Request(url, headers={"Accept": "image/*"}, method="GET"), MAX_IMAGE_BYTES)[0]
    if value.startswith("data:"):
        prefix, separator, value = value.partition(",")
        if not separator or not re.fullmatch(r"data:image/(png|jpeg|webp);base64", prefix, re.I):
            raise ValueError("服务没有返回支持的图片格式。")
    if len(value) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
        raise ValueError("服务返回的图片超过本地大小限制。")
    output = base64.b64decode(value, validate=True)
    if not output or len(output) > MAX_IMAGE_BYTES:
        raise ValueError("服务没有返回可用的图片数据。")
    return output


def response_images(adapter: str, reply: dict):
    if adapter == "gemini":
        return [item.get("data") or item.get("uri") for step in reply.get("steps", [])
                if step.get("type") == "model_output" for item in step.get("content", []) if item.get("type") == "image"]
    if adapter == "dashscope":
        return [item["image"] for choice in reply.get("output", {}).get("choices", [])
                for item in choice.get("message", {}).get("content", []) if "image" in item]
    rows = reply.get("images" if adapter == "silicon" else "data", [])
    return [row.get("b64_json") or row.get("url") for row in rows if row.get("b64_json") or row.get("url")]


def successful_reply(request: Request, adapter: str, *, task_id: str = "") -> ImageReply:
    raw, header_id = read_bytes(request, MAX_REPLY_BYTES)
    identity = header_id
    try:
        reply = json.loads(raw)
        identity = header_id or safe_request_id(reply.get("request_id") or reply.get("id"), request)
        if adapter == "tencent":
            value = reply["Response"]
            identity = safe_request_id(value.get("RequestId"), request) or header_id
            if "Error" in value or str(value.get("JobStatusCode")) == "4":
                return ImageReply(task_id=task_id, request_id=identity, status="failed")
            if not task_id:
                return ImageReply(task_id=value["JobId"], request_id=identity, status="queued")
            if str(value.get("JobStatusCode")) in {"1", "2"}:
                return ImageReply(task_id=task_id, request_id=identity, status="queued")
            urls = value["ResultImage"]
        elif reply.get("error") or (adapter in {"dashscope", "baidu", "silicon"}
                                    and reply.get("code") not in {None, "", 0, "0", 200, "200"}):
            return ImageReply(request_id=identity, status="failed")
        else:
            urls = response_images(adapter, reply)
        if not urls or len(urls) > 4:
            raise ValueError("服务返回的图片数量不可用。")
        return ImageReply(tuple(load_result(value) for value in urls), task_id, identity)
    except (ValueError, KeyError, TypeError, AttributeError, OSError):
        raise ImageRequestError("服务已响应，但图片或任务结果无法读取。请先核对服务端记录。",
                                uncertain=True, request_id=identity) from None


def submit_image(settings: ImageSettings, request: Request) -> ImageReply:
    return successful_reply(request, IMAGE_PROVIDERS[settings.provider].adapter)


def query_image(settings: ImageSettings, task_id: str) -> ImageReply:
    if not IMAGE_PROVIDERS[settings.provider].asynchronous or not re.fullmatch(r"[\w-]{1,200}", task_id):
        raise ValueError("此接口或任务编号不支持查询。")
    return successful_reply(tencent_request(settings, "QueryHunyuanImageJob", {"JobId": task_id}), "tencent", task_id=task_id)
