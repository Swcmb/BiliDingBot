"""状态持久化模块。

管理 data/state.json 文件，记录每个用户的最新 dynamic_id、
最近检测时间及连续失败次数。提供读取、更新、保存功能。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import STATE_JSON_PATH

logger = logging.getLogger(__name__)

# 日志时区
TZ_CN = timezone(timedelta(hours=8))  # UTC+8


class Storage:
    """状态持久化管理器。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._dirty: bool = False  # 标记是否有变更需要保存

    def load(self) -> None:
        """加载 state.json，若不存在或损坏则初始化为空。"""
        path = STATE_JSON_PATH

        if not path.exists():
            logger.info("state.json 不存在，将在首次运行中创建。")
            self._data = {}
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    self._data = {}
                    return
                self._data = json.loads(content)
        except (json.JSONDecodeError, ValueError) as e:
            # 文件损坏：备份并重新初始化
            backup_path = Path(str(path) + ".bak")
            logger.error(f"state.json 格式损坏: {e}，备份至 {backup_path} 并重新初始化")
            try:
                path.rename(backup_path)
            except OSError:
                logger.error("备份损坏文件失败，直接覆盖。")
            self._data = {}
            self._dirty = True

    def save(self) -> None:
        """保存 state.json（仅在数据变更时写入）。"""
        if not self._dirty:
            return

        STATE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        logger.info("state.json 已保存")
        self._dirty = False

    def get_user_state(self, uid: str) -> dict[str, Any]:
        """获取指定用户的状态，若不存在则返回默认值。"""
        return self._data.get(uid, {})

    def get_latest_dynamic_id(self, uid: str) -> int:
        """获取用户的最新 dynamic_id，若未记录则返回 0。"""
        return self._data.get(uid, {}).get("latest_dynamic_id", 0)

    def update_dynamic_id(self, uid: str, dynamic_id: int) -> None:
        """更新用户的最新 dynamic_id。"""
        if uid not in self._data:
            self._data[uid] = {}
        self._data[uid]["latest_dynamic_id"] = dynamic_id
        self._data[uid]["last_check_time"] = datetime.now(TZ_CN).isoformat()
        self._data[uid]["consecutive_failures"] = 0
        self._dirty = True

    def touch_check_time(self, uid: str) -> None:
        """仅更新最近检测时间（无新动态时）。"""
        if uid not in self._data:
            self._data[uid] = {}
        self._data[uid]["last_check_time"] = datetime.now(TZ_CN).isoformat()
        self._dirty = True

    def record_failure(self, uid: str) -> None:
        """记录一次推送失败，递增连续失败计数。"""
        if uid not in self._data:
            self._data[uid] = {}
        current = self._data[uid].get("consecutive_failures", 0) + 1
        self._data[uid]["consecutive_failures"] = current
        if current >= 3:
            logger.warning(
                f"用户 {uid} 已连续 {current} 次推送失败，请检查钉钉配置！"
            )
        self._dirty = True

    def is_first_run(self, uid: str) -> bool:
        """判断是否为首次运行（该用户状态尚未记录）。"""
        return uid not in self._data or "latest_dynamic_id" not in self._data.get(uid, {})


# 全局单例
storage = Storage()
