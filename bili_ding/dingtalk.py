"""钉钉通知封装模块。

封装钉钉机器人 Webhook 消息发送，包含 HMAC-SHA256 签名和重试机制。
消息格式为 Markdown 类型，支持图片和链接。
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 钉钉 Webhook 基础 URL
DINGTALK_BASE_URL = "https://oapi.dingtalk.com/robot/send"

# 重试配置
MAX_RETRIES = 3
# 指数退避初始延迟（秒）
RETRY_DELAY_BASE = 1


def _generate_sign(timestamp: str, secret: str) -> str:
    """生成钉钉 Webhook 的 HMAC-SHA256 签名。

    Args:
        timestamp: 当前毫秒时间戳
        secret: 钉钉机器人加签密钥

    Returns:
        URL 编码后的签名字符串
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return urllib.parse.quote_plus(base64.b64encode(hmac_code).decode())


def _build_webhook_url(token: str, secret: str) -> str:
    """构建完整的钉钉 Webhook URL（含签名）。"""
    timestamp = str(round(time.time() * 1000))
    sign = _generate_sign(timestamp, secret)
    return (
        f"{DINGTALK_BASE_URL}?"
        f"access_token={token}&timestamp={timestamp}&sign={sign}"
    )


def _build_markdown_content(
    author_name: str,
    type_cn: str,
    text: str,
    pics: list[str],
    url: str,
    hit_keywords: list[str],
) -> str:
    """构建钉钉 Markdown 消息内容。

    Args:
        author_name: UP 主昵称
        type_cn: 中文动态类型
        text: 动态文本内容
        pics: 图片 URL 列表
        url: 动态原文链接
        hit_keywords: 命中的关键词列表

    Returns:
        Markdown 格式的消息文本
    """
    lines = [f"## {author_name} 发布了新{type_cn}"]

    # 动态文本
    if text:
        lines.append("")
        # 截断过长文本（钉钉 Markdown 有长度限制）
        display_text = text[:500] + ("..." if len(text) > 500 else "")
        lines.append(display_text)

    # 关键词标注
    if hit_keywords:
        kw_str = "、".join(f'"{kw}"' for kw in hit_keywords)
        lines.append("")
        lines.append(f"> 含命中关键词：[{kw_str}]")

    # 图片
    if pics:
        lines.append("")
        for i, pic_url in enumerate(pics):
            # 只展示前 5 张图片（避免消息过长）
            if i >= 5:
                lines.append(f"> *(共 {len(pics)} 张图片，仅展示前 5 张)*")
                break
            lines.append(f"![图片{i + 1}]({pic_url})")

    # 原文链接
    lines.append("")
    lines.append(f"[查看原文]({url})")

    return "\n".join(lines)


def send_notification(
    token: str,
    secret: str,
    author_name: str,
    type_cn: str,
    text: str,
    pics: list[str],
    url: str,
    hit_keywords: list[str],
) -> bool:
    """发送钉钉 Markdown 通知。

    Args:
        token: 钉钉机器人 Access Token
        secret: 钉钉机器人加签密钥
        author_name: UP 主昵称
        type_cn: 中文动态类型
        text: 动态文本内容
        pics: 图片 URL 列表
        url: 动态原文链接
        hit_keywords: 命中的关键词列表

    Returns:
        True 表示发送成功，False 表示失败
    """
    webhook_url = _build_webhook_url(token, secret)
    markdown_text = _build_markdown_content(
        author_name, type_cn, text, pics, url, hit_keywords
    )

    message: dict[str, Any] = {
        "msgtype": "markdown",
        "markdown": {
            "title": f"{author_name} 发布了新{type_cn}",
            "text": markdown_text,
        },
    }

    last_error: str = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                webhook_url,
                headers={"Content-Type": "application/json"},
                data=json.dumps(message, ensure_ascii=False).encode("utf-8"),
                timeout=10,
            )
            result = resp.json()
            if result.get("errcode") == 0:
                logger.info(
                    f"钉钉通知发送成功: {author_name} ({type_cn})"
                )
                return True
            else:
                last_error = (
                    f"errcode={result.get('errcode')}, "
                    f"errmsg={result.get('errmsg', '')}"
                )
        except requests.RequestException as e:
            last_error = str(e)
        except ValueError:
            last_error = "返回非 JSON 响应"

        logger.warning(
            f"钉钉通知发送失败 (第{attempt}次): {last_error}"
        )

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
            time.sleep(delay)

    logger.error(f"钉钉通知发送失败，已达最大重试次数: {last_error}")
    return False
