"""BiliDingBot - B站用户动态监控与钉钉推送系统。

基于 GitHub Actions 定时运行，监控 B 站用户的动态更新，
通过钉钉机器人 Webhook 发送实时通知。
支持多用户监控、关键词筛选和图片消息推送。

用法:
    python -m bili_ding
"""

__version__ = "1.0.0"
