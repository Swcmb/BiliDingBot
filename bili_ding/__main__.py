"""BiliDingBot 程序入口。

通过 `python -m bili_ding` 启动监控流程。
"""

import logging

from .config import config
from .monitor import run


def _setup_logging() -> None:
    """配置日志格式和级别。"""
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """主入口函数。

    步骤:
        1. 配置日志
        2. 加载配置文件（users.yaml + 环境变量）
        3. 执行监控流程
    """
    _setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("BiliDingBot 启动中...")

    # 加载配置（包含校验）
    config.load()

    logger.info(
        f"已加载 {len(config.users)} 个用户，"
        f"请求间隔: {config.request_interval}s，"
        f"钉钉: {'已配置' if config.is_dingtalk_ready() else '未配置'}"
    )

    # 执行监控
    run()

    logger.info("BiliDingBot 执行完毕。")


if __name__ == "__main__":
    main()
