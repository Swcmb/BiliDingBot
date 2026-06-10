# BiliDingBot

基于 GitHub Actions 的 B站动态监控与钉钉推送系统。

## 功能特性

- **多用户监控**: 支持配置多个 B站 UID，同时监控多位 UP 主
- **动态检测**: 通过 B站 API 获取用户空间动态，识别新动态
- **钉钉推送**: 通过钉钉机器人 Webhook 发送 Markdown 格式通知
- **图片支持**: 动态中的图片自动嵌入钉钉消息
- **关键词筛选**: 支持关键词过滤，仅推送包含指定关键词的动态
- **状态持久化**: 使用 `data/state.json` 记录最新动态 ID，避免重复推送
- **定时运行**: GitHub Actions 定时执行（默认每 30 分钟）

## 快速开始

### 1. 配置钉钉机器人

在钉钉群中添加「自定义机器人」，获取：
- **Webhook URL** 中的 `access_token`
- **加签密钥**（开启「安全设置」中的「加签」）

### 2. 设置 GitHub Secrets

在仓库的 **Settings > Secrets and variables > Actions** 中添加：

| Secret 名称 | 说明 |
|------------|------|
| `DINGTALK_TOKEN` | 钉钉机器人的 Access Token |
| `DINGTALK_SECRET` | 钉钉机器人的加签密钥 |

### 3. 配置监控用户

编辑 `config/users.yaml` 文件：

```yaml
users:
  - uid: "288592887"
    name: "谭乔"
    keywords: ["交通安全", "普法"]  # 仅推送包含这些关键词的动态

  - uid: "280793434"
    name: "共青团中央"
    keywords: []  # 空列表 = 推送所有动态

request_interval: 2  # 请求间隔（秒）
```

### 4. 启用 GitHub Actions

推送代码到 GitHub 后，Actions 会自动运行：
- **定时触发**: 每 30 分钟执行一次
- **手动触发**: 在 Actions 页面点击「Run workflow」

## 项目结构

```
BiliDingBot/
├── .github/workflows/monitor.yml   # GitHub Actions 配置
├── bili_ding/                      # 核心模块
│   ├── __main__.py                 # 程序入口
│   ├── config.py                   # 配置管理
│   ├── bilibili.py                 # B站 API 封装
│   ├── dingtalk.py                 # 钉钉通知封装
│   ├── monitor.py                  # 监控调度逻辑
│   └── storage.py                  # 状态持久化
├── config/users.yaml               # 用户配置文件
├── data/state.json                 # 运行时状态（自动生成）
└── requirements.txt                # 依赖列表
```

## 动态类型支持

| 类型 | 说明 | 是否推送 |
|------|------|---------|
| `DYNAMIC_TYPE_WORD` | 纯文字动态 | 是 |
| `DYNAMIC_TYPE_DRAW` | 图文动态 | 是 |
| `DYNAMIC_TYPE_AV` | 视频投稿 | 是 |
| `DYNAMIC_TYPE_FORWARD` | 转发动态 | 是 |
| `DYNAMIC_TYPE_ARTICLE` | 专栏投稿 | 是 |
| `DYNAMIC_TYPE_LIVE_RCMD` | 直播推荐 | 否 |
| `DYNAMIC_TYPE_LIVE` | 直播中 | 否 |

## 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量（可选，用于测试钉钉推送）
export DINGTALK_TOKEN=your_token
export DINGTALK_SECRET=your_secret

# 运行程序
python -m bili_ding
```

## 注意事项

1. **WBI 签名**: B站 API 需要 WBI 签名，程序会自动获取密钥
2. **状态持久化**: `data/state.json` 需要纳入版本控制，以便在 GitHub Actions 中跨运行持久化
3. **反爬策略**: 程序内置请求间隔和重试机制，避免被封禁
4. **定时延迟**: GitHub Actions 的 schedule 触发器可能有延迟（通常 15-60 分钟）

## License

MIT
