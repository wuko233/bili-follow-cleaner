# bili-follow-cleaner

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)  [![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)  [![Codacy Badge](https://app.codacy.com/project/badge/Grade/1e02fea405b74a189eaed4bbedce7686)](https://app.codacy.com/gh/wuko233/bili-follow-cleaner/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)


## 📌 项目简介

本脚本用于批量清理B站不活跃的关注用户，通过扫描用户最新动态实现按条件取关。支持白名单保护、自动识别互关用户、请求频率控制等功能。

## 📦 依赖安装

本项目依赖于[bilibili-api](https://github.com/Nemo2011/bilibili-api)，请先配置`bilibili-api`环境：[快速上手](https://github.com/Nemo2011/bilibili-api#%E5%BF%AB%E9%80%9F%E4%B8%8A%E6%89%8B)

本项目还依赖以下第三方库：

```bash
pip install httpx requests
```

## ⚙️ 初始配置

1. 安装Python 3.9+环境

2. 创建项目目录并安装依赖库

3. clone本仓库或下载`main.py`

## 🚀 快速启动

```bash
python main.py
```

## 🔧 参数配置说明

| 参数名               | 默认值 | 说明                                                                 |
|----------------------|--------|----------------------------------------------------------------------|
| ps                   | 50     | 每页请求数量 (1-50)                                                 |
| INACTIVE_THRESHOLD   | 365    | 不活跃天数阈值                                                      |
| SKIP_NUM             | 0      | 跳过最近关注的用户数                                                |
| LAG_START-LAG_END    | 5-20   | 随机请求延迟区间(秒) 防止风控                                        |
| AUTO_ADD_IGNORE      | True   | 自动添加互关/特别关注用户到白名单                                   |

## 🖥 使用流程

1. 首次运行会自动触发扫码登录

2. 登录成功后自动保存cookies至`cookies.json`

3. 按提示配置参数：

   - 设置白名单UID（支持批量）

   - 调整活跃度检测阈值

   - 配置请求延迟参数

4. 脚本自动执行取关操作

5. 日志记录在`unfollow.log`

## ⚠️ 注意事项

1. 风控策略：

   - 默认请求延迟5-20秒

   - 遇到-352错误码时需增大延迟参数

2. 数据保护：

   - `cookies.json`包含登录凭证，请勿泄露

   - 白名单用户永久排除在清理范围外

3. 特殊逻辑：

   - 当`AUTO_ADD_IGNORE`启用时：

     - 自动识别互关用户

     - 自动识别特别关注用户

   - 不活跃天数 = 当前时间 - 最近两条动态的最新时间戳

## 🛠 进阶功能

- 手动修改配置：

  ```python
  # 直接编辑脚本全局变量
  ignore_list = [114514, 1919810]  # 添加永久白名单UID
  ```

- 重新登录：
  删除当前目录下的`cookies.json`文件后重新运行脚本

## 📄 免责声明

本脚本仅供学习交流，使用本脚本需遵守B站用户协议，过度频繁操作可能导致账号异常，请谨慎使用并自行承担风险。