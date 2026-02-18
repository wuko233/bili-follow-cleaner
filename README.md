# bili-follow-cleaner

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)    [![Release](https://img.shields.io/github/v/release/wuko233/bili-follow-cleaner)](https://github.com/wuko233/bili-follow-cleaner/releases) [![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)  [![Codacy Badge](https://app.codacy.com/project/badge/Grade/1e02fea405b74a189eaed4bbedce7686)](https://app.codacy.com/gh/wuko233/bili-follow-cleaner/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)

## 📌 项目简介

本工具用于批量清理B站不活跃的关注用户，提供 **Web可视化界面** 与 **命令行** 两种操作模式。

核心功能：
- **多维度检测**：支持按“最新动态”或“最新投稿（视频/音频/专栏）”判断活跃度。
- **白名单保护**：自动识别互关、特别关注用户，支持手动添加白名单。
- **智能筛选**：支持移除“账号已注销”用户、移除“无历史动态/投稿”用户。
- **风控规避**：随机请求延迟，模拟人类操作，减少 `-352` 风控风险。

## 📥 下载即用 (推荐)

如果你不想安装 Python 环境，可以直接下载编译好的可执行文件（Windows）：

1. 进入 [**Releases 页面**](https://github.com/wuko233/bili-follow-cleaner/releases)。
2. 下载最新版本的压缩包或 `.exe` 文件：
   - **`BiliCleaner_WebUI.exe`**：**(推荐)** 拥有完整的网页图形界面，操作更直观。
   - **`BiliCleaner_Terminal.exe`**：传统的命令行版本，轻量级。
3. 下载后直接双击运行即可（首次运行需扫码登录）。

---

## 📦 源码部署与运行

如果你是开发者或希望使用源码运行，请按以下步骤操作。

### 1. 环境准备
确保已安装 Python 3.12+ 环境，并安装项目依赖：

```bash
git clone https://github.com/wuko233/bili-follow-cleaner.git
cd bili-follow-cleaner
pip install -r requirements.txt
```

### 2. 启动方式

#### 方式 A：启动 Web UI (推荐)
提供直观的网页操作界面，支持扫码登录、参数热修改、实时日志查看。

```bash
streamlit run app.py
```
运行后浏览器会自动打开操作页面（通常为 `http://localhost:8501`）。

#### 方式 B：启动命令行版
传统的交互式命令行界面，按照提示输入数字进行配置。

```bash
python main.py
```

### 3. 自行编译 (可选)
如果你想修改代码并重新打包成 exe，可以使用内置的构建脚本：

```bash
python build.py
```
构建完成后，`dist/` 目录下会生成 `BiliCleaner_WebUI.exe` 和 `BiliCleaner_Terminal.exe`。

---

## 🔧 参数配置说明

无论使用哪种模式，核心参数逻辑一致：

| 参数名 | 默认值 | 说明 |
|:---|:---|:---|
| **检测类型** | 动态 | **动态**：按用户发布的动态时间判断<br>**投稿**：按用户发布的视频/音频/专栏时间判断 |
| **每页数量 (ps)** | 50 | 单次API请求获取的关注数 (1-50) |
| **不活跃阈值** | 365 | 超过此天数未活跃的用户将被取关 |
| **跳过数量** | 0 | 跳过关注列表中最近关注的 N 个人（防止误删刚关注还未发内容的UP） |
| **请求延迟** | 5-20s | 每次取关操作后的随机等待时间，防止触发风控 |
| **自动白名单** | True | 自动将“互粉好友”和“特别关注”加入白名单 |
| **移除无记录用户** | False | **⚠️危险选项**：是否取关从未发过动态/投稿的用户 |
| **移除注销用户** | False | **⚠️危险选项**：是否取关昵称为“账号已注销”的用户 |

## 🖥 使用流程 (Web UI)

1. **登录**：点击侧边栏“扫码登录”，使用B站App扫描二维码。登录成功后 Cookies 会自动保存至本地 `cookies.json`。
2. **配置**：在左侧边栏调整筛选条件（活跃阈值、白名单等）。
3. **运行**：点击主界面的“🚀 开始清理”按钮。
4. **监控**：右侧日志区会实时显示处理进度、取关详情及跳过原因。

## ⚠️ 注意事项

1. **风控说明**：
   - 默认延迟（5-20秒）较为保守，基本不会触发风控。
   - 如果遇到 `-352` 错误，请暂停脚本，等待一段时间后再试，并尝试增大延迟参数。

2. **数据安全**：
   - `cookies.json` 包含您的登录凭证，请勿发送给他人。
   - 脚本运行在本地，不会上传任何数据。

3. **活跃度判断逻辑**：
   - **动态模式**：对比用户最近两条动态的发布时间戳（修复置顶动态导致的误判）。
   - **投稿模式**：对比用户最新的视频、音频或专栏的发布时间。

## 📄 免责声明

本脚本仅供学习交流使用。使用本脚本需遵守Bilibili用户协议。开发者不对因使用本脚本导致的任何账号异常、数据丢失或封号承担责任。请谨慎设置“移除无记录用户”等高风险选项。