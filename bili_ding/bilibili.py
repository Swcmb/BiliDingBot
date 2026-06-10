"""B站 API 封装模块。

封装 B 站空间动态 API 调用（含 WBI 签名），解析动态列表。
内置 Session 管理、Cookie 持久化与反爬策略。

动态类型映射:
    DYNAMIC_TYPE_WORD    - 纯文字动态
    DYNAMIC_TYPE_DRAW    - 图文动态
    DYNAMIC_TYPE_AV      - 视频投稿
    DYNAMIC_TYPE_FORWARD - 转发动态
    DYNAMIC_TYPE_ARTICLE - 专栏投稿
    其他                  - 不推送
"""

import functools
import hashlib
import logging
import time
import urllib.parse
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# B站动态 API 端点
BILI_DYNAMIC_API = (
    "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
)
# B站 WBI 密钥获取端点
BILI_NAV_API = "https://api.bilibili.com/x/web-interface/nav"
# B站首页（初始化 Cookie）
BILI_HOME = "https://www.bilibili.com/"

# 需要推送的动态类型及其中文名称
PUSHABLE_TYPES: dict[str, str] = {
    "DYNAMIC_TYPE_WORD": "纯文字动态",
    "DYNAMIC_TYPE_DRAW": "图文动态",
    "DYNAMIC_TYPE_AV": "视频投稿",
    "DYNAMIC_TYPE_FORWARD": "转发动态",
    "DYNAMIC_TYPE_ARTICLE": "专栏投稿",
}

# 默认请求头
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 最大 API 重试次数
MAX_API_RETRIES = 2
# API 重试等待秒数
API_RETRY_DELAY = 3
# HTTP 412 反爬等待秒数
RATE_LIMIT_DELAY = 10

# WBI v2 混排表（B站官方固定值）
_MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

# ---- 内部状态 ----
_session: Optional[requests.Session] = None
_wbi_mixin_key: Optional[str] = None


def _safe_get(obj: dict, *keys: str) -> Optional[str]:
    """安全地从嵌套字典中获取字符串值，任一层级缺失返回 None。"""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key, {})
    return obj if isinstance(obj, str) else None


def _init_session() -> requests.Session:
    """初始化 HTTP Session，从 B站首页获取 Cookie。"""
    global _session
    if _session is not None:
        return _session

    _session = requests.Session()
    _session.headers.update(DEFAULT_HEADERS)

    try:
        _session.get(BILI_HOME, timeout=15)
        logger.debug("已从 B站首页获取 Cookie")
    except requests.RequestException:
        logger.warning("访问 B站首页失败，继续使用默认 Session")

    return _session


def _ensure_mixin_key() -> str:
    """获取或刷新 WBI mixin key。

    从 B站 nav 端点获取 wbi_img 中的 img_key 和 sub_key，
    按规则拼接为 mixin_key 并缓存。
    """
    global _wbi_mixin_key
    if _wbi_mixin_key is not None:
        return _wbi_mixin_key

    session = _init_session()
    try:
        resp = session.get(
            BILI_NAV_API,
            headers={"Referer": BILI_HOME},
            timeout=15,
        )
        data = resp.json()
        wbi_img = (data.get("data") or {}).get("wbi_img") or {}
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        if img_url and sub_url:
            # 提取文件名（去掉路径和扩展名），拼接为 64 字符 raw_key
            img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
            raw_key = img_key + sub_key
            # WBI v2：使用混排表打乱字符顺序后取前 32 位
            _wbi_mixin_key = "".join(
                raw_key[i] for i in _MIXIN_KEY_ENC_TAB
            )[:32]
            logger.debug(
                f"WBI mixin_key 已缓存: {_wbi_mixin_key[:4]}..."
            )
            return _wbi_mixin_key
    except Exception as e:
        logger.error(f"获取 WBI 密钥失败: {e}")

    # 降级：使用已硬编码的 mixin_key（B站公开值，偶尔需更新）
    _wbi_mixin_key = "ea1db124af3c7062474693fa704f4ff8"
    logger.warning("使用降级 WBI mixin_key")
    return _wbi_mixin_key


def _sign_params(params: dict[str, str]) -> dict[str, str]:
    """对请求参数进行 WBI 签名，添加 w_rid 和 wts。

    WBI 签名步骤（v2）:
        1. 将 wts（当前秒级时间戳）加入参数
        2. 按 key 字母序排序所有参数
        3. 拼接为 query_string 格式（值需 URL 编码）
        4. w_rid = md5(query_string + mixin_key)
    """
    mixin_key = _ensure_mixin_key()

    # wts 必须在签名前加入参数列表
    signed = dict(params)
    signed["wts"] = str(int(time.time()))

    sorted_keys = sorted(signed.keys())
    query = "&".join(
        f"{k}={urllib.parse.quote(str(signed[k]), safe='')}"
        for k in sorted_keys
    )
    sign_str = query + mixin_key
    w_rid = hashlib.md5(sign_str.encode()).hexdigest()

    signed["w_rid"] = w_rid
    return signed


def fetch_dynamics(
    host_mid: str, request_interval: int = 2
) -> list[dict]:
    """获取指定用户的所有新动态（支持分页遍历、WBI 签名）。"""
    global _wbi_mixin_key

    session = _init_session()
    offset = ""
    all_dynamics: list[dict] = []
    has_more = True
    retries = 0
    total_items = 0  # API 返回的总条数
    skipped_items = 0  # 被过滤的非推送类型条数

    while has_more:
        # 构建基础参数
        raw_params: dict[str, str] = {"host_mid": host_mid}
        if offset:
            raw_params["offset"] = offset

        # WBI 签名
        params = _sign_params(raw_params)

        try:
            resp = session.get(
                BILI_DYNAMIC_API,
                params=params,
                headers={
                    "Referer": (
                        f"https://space.bilibili.com/{host_mid}/dynamic"
                    )
                },
                timeout=15,
            )
        except requests.RequestException as e:
            logger.error(f"请求 B站 API 失败 (uid={host_mid}): {e}")
            retries += 1
            if retries <= MAX_API_RETRIES:
                time.sleep(API_RETRY_DELAY)
                continue
            break

        # 处理反爬拦截
        if resp.status_code == 412:
            logger.error(
                f"B站 API 返回 412 (uid={host_mid})，"
                f"等待 {RATE_LIMIT_DELAY}s"
            )
            time.sleep(RATE_LIMIT_DELAY)
            retries += 1
            if retries <= MAX_API_RETRIES:
                continue
            break

        if resp.status_code != 200:
            logger.error(
                f"B站 API 返回异常状态码 {resp.status_code} "
                f"(uid={host_mid})"
            )
            retries += 1
            if retries <= MAX_API_RETRIES:
                time.sleep(API_RETRY_DELAY)
                continue
            break

        try:
            data = resp.json()
        except ValueError:
            logger.error(f"B站 API 返回非 JSON 数据 (uid={host_mid})")
            # WBI 密钥可能过期，刷新后重试
            _wbi_mixin_key = None
            retries += 1
            if retries <= MAX_API_RETRIES:
                continue
            break

        code = data.get("code")
        if code != 0:
            # -352 表示签名错误，刷新 mixin_key 后重试
            if code == -352 and retries < MAX_API_RETRIES:
                logger.warning(
                    f"B站 WBI 签名失效 (uid={host_mid})，刷新密钥后重试"
                )
                _wbi_mixin_key = None
                retries += 1
                continue

            logger.error(
                f"B站 API 业务错误 (uid={host_mid}): "
                f"code={code}, message={data.get('message', '')}"
            )
            break

        items = (data.get("data") or {}).get("items") or []
        has_more = bool((data.get("data") or {}).get("has_more", False))
        next_offset = (data.get("data") or {}).get("offset", "")

        # 解析每条动态
        for item in items:
            total_items += 1
            parsed = _parse_dynamic_item(item, host_mid)
            if parsed:
                all_dynamics.append(parsed)
            else:
                skipped_items += 1

        if has_more:
            offset = str(next_offset) if next_offset else ""
            time.sleep(request_interval)
        retries = 0  # 成功获取一页后重置重试计数

    if skipped_items > 0:
        logger.debug(
            f"uid={host_mid}: API 返回 {total_items} 条，"
            f"过滤非推送类型 {skipped_items} 条，"
            f"有效 {len(all_dynamics)} 条"
        )

    return all_dynamics


def _parse_dynamic_item(
    item: dict, host_mid: str
) -> Optional[dict]:
    """解析单条动态，提取关键信息。

    Returns:
        解析后的动态字典，若非推送类型返回 None
    """
    dyn_type = item.get("type", "")
    if not dyn_type or dyn_type not in PUSHABLE_TYPES:
        if dyn_type:
            logger.debug(
                f"跳过非推送类型: type={dyn_type}, uid={host_mid}"
            )
        return None

    modules = item.get("modules") or {}
    author_info = modules.get("module_author") or {}
    dyn_info = modules.get("module_dynamic") or {}

    author_name = author_info.get("name", host_mid)

    # 提取动态文本
    desc_obj = dyn_info.get("desc") or {}
    text = desc_obj.get("text", "") or ""

    # WORD 类型 desc.text 可能为空，从 major.opus.summary.text 补充
    if not text:
        major = dyn_info.get("major") or {}
        opus = major.get("opus") or {}
        summary = opus.get("summary") or {}
        text = summary.get("text", "") or ""

    pics = _extract_pictures(dyn_type, dyn_info)

    dynamic_id_str = item.get("id_str", "0")
    try:
        dynamic_id = int(dynamic_id_str)
    except (ValueError, TypeError):
        dynamic_id = 0

    url = f"https://t.bilibili.com/{dynamic_id_str}"

    return {
        "dynamic_id": dynamic_id,
        "type": dyn_type,
        "type_cn": PUSHABLE_TYPES.get(dyn_type, dyn_type),
        "author_name": author_name,
        "text": text,
        "pics": pics,
        "url": url,
    }


def _extract_pictures(dyn_type: str, dyn_info: dict) -> list[str]:
    """从动态信息中提取图片 URL 列表。

    不同动态类型的图片存放路径：
    - DRAW:  major.draw.items[].src
    - WORD:  major.opus.pics[].url
    """
    major = dyn_info.get("major") or {}
    pics: list[str] = []

    if dyn_type == "DYNAMIC_TYPE_DRAW":
        draw = major.get("draw") or {}
        for item in draw.get("items") or []:
            src = item.get("src", "")
            if src:
                pics.append(src)

    elif dyn_type == "DYNAMIC_TYPE_WORD":
        opus = major.get("opus") or {}
        for pic in (opus.get("pics") or []):
            url = pic.get("url", "")
            if url:
                pics.append(url)

    return pics
