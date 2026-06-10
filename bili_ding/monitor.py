"""核心监控调度模块。

遍历用户配置 → 获取B站动态 → 关键词匹配 → 钉钉推送 → 更新状态。
错误隔离到用户级别，单个用户的失败不影响其他用户。
"""

import logging
import time
from typing import Optional

from .bilibili import fetch_dynamics
from .config import config
from .dingtalk import send_notification
from .storage import storage

logger = logging.getLogger(__name__)


def _match_keywords(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """检查文本是否匹配任意关键词。

    Args:
        text: 待匹配的文本
        keywords: 关键词列表

    Returns:
        (是否命中, 命中的关键词列表)
    """
    if not keywords:
        return True, []

    hit: list[str] = []
    lower_text = text.lower()
    for kw in keywords:
        if kw.lower() in lower_text:
            hit.append(kw)
    return len(hit) > 0, hit


def _process_user(user: dict, request_interval: int) -> None:
    """处理单个用户的动态监控。

    Args:
        user: 用户配置字典（uid, name, keywords）
        request_interval: 请求间隔秒数
    """
    uid: str = user["uid"]
    name: str = user.get("name", uid)
    keywords: list[str] = user.get("keywords", [])

    logger.info(f"开始检测用户: {name} (uid={uid})")

    # 获取动态列表
    dynamics = fetch_dynamics(uid, request_interval)
    if not dynamics:
        logger.info(f"用户 {name} 无动态数据，跳过。")
        return

    # 如果是首次运行，记录最新动态ID但不推送
    if storage.is_first_run(uid):
        latest = max(d["dynamic_id"] for d in dynamics)
        storage.update_dynamic_id(uid, latest)
        logger.info(
            f"首次运行: {name}, 记录最新动态ID={latest}, 不推送。"
        )
        return

    latest_known_id = storage.get_latest_dynamic_id(uid)

    # 递减排序（新→旧），便于遇到旧ID时提前停止
    sorted_dynamics = sorted(
        dynamics, key=lambda d: d["dynamic_id"], reverse=True
    )

    new_dynamics: list[dict] = []
    for d in sorted_dynamics:
        if d["dynamic_id"] > latest_known_id:
            new_dynamics.append(d)
        else:
            # 递减排序下，后续所有ID都更小，均为已处理
            break

    if not new_dynamics:
        logger.info(f"用户 {name} 无新动态。")
        storage.touch_check_time(uid)
        return

    logger.info(
        f"发现 {len(new_dynamics)} 条新动态: {name} (uid={uid})"
    )

    # 遍历新动态（从旧到新推送，符合阅读习惯）
    new_dynamics.sort(key=lambda d: d["dynamic_id"])

    new_max_id = new_dynamics[-1]["dynamic_id"]

    for d in new_dynamics:
        # 关键词匹配
        matched, hit_keywords = _match_keywords(d["text"], keywords)
        if not matched:
            logger.debug(
                f"动态 {d['dynamic_id']} 未命中关键词，跳过。"
            )
            continue

        # 发送钉钉通知
        logger.info(
            f"推送动态 {d['dynamic_id']}: {d['type_cn']}"
            + (f", 命中关键词: {hit_keywords}" if hit_keywords else "")
        )

        if config.is_dingtalk_ready():
            success = send_notification(
                token=config.dingtalk_token,
                secret=config.dingtalk_secret,
                author_name=d["author_name"],
                type_cn=d["type_cn"],
                text=d["text"],
                pics=d["pics"],
                url=d["url"],
                hit_keywords=hit_keywords,
            )
            if success:
                storage.update_dynamic_id(uid, new_max_id)
            else:
                storage.record_failure(uid)
        else:
            logger.warning(
                "钉钉配置未就绪，跳过推送。"
                "请设置环境变量 DINGTALK_TOKEN 和 DINGTALK_SECRET。"
            )

    # 无新动态或全部跳过关键词 → 也更新最新ID，避免重复检测
    if storage.get_latest_dynamic_id(uid) < new_max_id:
        storage.update_dynamic_id(uid, new_max_id)


def run() -> None:
    """执行监控主流程。

    遍历所有配置的用户，对每个用户执行动态检测和推送。
    错误隔离到用户级别。
    """
    if not config.users:
        logger.info("无用户配置，退出。")
        return

    # 加载历史状态
    storage.load()

    request_interval = config.request_interval

    for i, user in enumerate(config.users):
        # 多个用户之间添加间隔（非第一个用户时）
        if i > 0:
            time.sleep(request_interval)

        try:
            _process_user(user, request_interval)
        except Exception:
            logger.exception(
                f"处理用户 {user.get('uid', '?')} 时发生未预期错误，跳过。"
            )

    # 保存状态
    storage.save()
    logger.info("监控流程完成。")
