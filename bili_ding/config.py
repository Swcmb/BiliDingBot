"""配置管理与校验模块。

读取 users.yaml 配置文件和环境变量，提供统一的配置接口。
所有 B 站 UID 统一转为字符串类型，确保与 state.json 的 key 一致。
"""

import os
import sys
from pathlib import Path
from typing import Any

import yaml

# 项目根目录（bili_ding 的父目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 配置文件路径
USERS_YAML_PATH = PROJECT_ROOT / "config" / "users.yaml"
STATE_JSON_PATH = PROJECT_ROOT / "data" / "state.json"


class ConfigError(Exception):
    """配置错误异常。"""

    pass


class Config:
    """统一配置管理。"""

    def __init__(self) -> None:
        self.users: list[dict[str, Any]] = []
        self.request_interval: int = 2

        # 钉钉配置（仅从环境变量读取，保证安全性）
        self.dingtalk_token: str = os.environ.get("DINGTALK_TOKEN", "")
        self.dingtalk_secret: str = os.environ.get("DINGTALK_SECRET", "")

    def load(self) -> None:
        """加载并校验 users.yaml 配置文件。"""
        if not USERS_YAML_PATH.exists():
            raise ConfigError(f"配置文件不存在: {USERS_YAML_PATH}")

        with open(USERS_YAML_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if raw is None:
            print("配置文件中无有效内容，退出。")
            sys.exit(0)

        # 加载用户列表
        raw_users = raw.get("users", [])
        if not raw_users:
            print("users.yaml 中未配置任何用户，退出。")
            sys.exit(0)

        self._validate_users(raw_users)
        self.users = raw_users

        # 加载请求间隔
        self.request_interval = raw.get("request_interval", 2)

        # 校验钉钉配置
        self._validate_dingtalk()

    def _validate_users(self, raw_users: list) -> None:
        """校验用户配置格式。"""
        for i, user in enumerate(raw_users):
            if "uid" not in user:
                raise ConfigError(f"第 {i + 1} 个用户缺少 uid 字段")
            # UID 强制转为字符串
            user["uid"] = str(user["uid"])
            # name 可选，默认使用 UID
            user.setdefault("name", user["uid"])
            # keywords 必须是列表
            keywords = user.get("keywords", [])
            if not isinstance(keywords, list):
                raise ConfigError(
                    f"用户 {user['uid']} 的 keywords 必须是列表类型"
                )
            user["keywords"] = keywords

    def _validate_dingtalk(self) -> None:
        """校验钉钉环境变量。"""
        if not self.dingtalk_token:
            print(
                "警告: 环境变量 DINGTALK_TOKEN 未设置，将跳过钉钉通知。"
            )
        if not self.dingtalk_secret:
            print(
                "警告: 环境变量 DINGTALK_SECRET 未设置，将跳过钉钉通知。"
            )

    def is_dingtalk_ready(self) -> bool:
        """检查钉钉配置是否就绪。"""
        return bool(self.dingtalk_token and self.dingtalk_secret)


# 全局单例
config = Config()
