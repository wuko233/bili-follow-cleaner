import streamlit as st
import asyncio
from datetime import timedelta
import json
import logging
import random
import time
from pathlib import Path
import requests
from bilibili_api import login_v2, user

# === 页面配置 ===
st.set_page_config(page_title="B站自动取关助手", page_icon="📺", layout="wide")

# === 日志配置 ===
# 定义日志文件路径
LOG_FILE = "bilibili_cleanup.log"

# 创建 logger
logger = logging.getLogger("BiliCleaner")
logger.setLevel(logging.INFO)

# 防止 Streamlit 刷新导致 handler 重复添加
if not logger.handlers:
    # 1. 文件 Handler (保存到本地)
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

# === 自定义 Streamlit 日志 Handler ===
class StreamlitHandler(logging.Handler):
    def __init__(self, log_container):
        super().__init__()
        self.log_container = log_container
        self.log_text = ""

    def emit(self, record):
        try:
            msg = self.format(record)
            # 在 UI 显示时去掉过于详细的时间戳，保持简洁
            ui_msg = msg.split(" - ", 2)[-1] if " - " in msg else msg
            
            self.log_text += f"{ui_msg}\n"
            # 限制 UI 日志长度
            if len(self.log_text) > 10000:
                self.log_text = self.log_text[-10000:]
            self.log_container.code(self.log_text, language='text')
        except Exception:
            self.handleError(record)

# === 配置类 ===
class Config:
    def __init__(self):
        self.ps = 50
        self.ignore_list = []
        self.INACTIVE_THRESHOLD = 365
        self.SKIP_NUM = 0
        self.DETECT_TYPE = 0
        self.REMOVE_EMPTY_DYNAMIC = False
        self.REMOVE_DELETED_USER = False
        self.LAG_START = 5
        self.LAG_END = 20
        self.AUTO_ADD_IGNORE = True
        self.cookies = None
        self.uid = None
        self.headers = {}

    def set_user_cookies(self, cookies):
        self.cookies = cookies
        self.uid = cookies["DedeUserID"]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": f"https://space.bilibili.com/{self.uid}/"
        }

# === 初始化 Session State ===
if 'config' not in st.session_state:
    st.session_state.config = Config()

config = st.session_state.config

# === 核心逻辑类 ===

class FollowedUser:
    def __init__(self, mid, uname):
        self.mid = mid
        self.name = uname

    async def get_latest_dynamic(self):
        """
        获取最新动态，比较前两条动态的时间戳（修复置顶导致乱序的问题）
        """
        try:
            credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
            u = user.User(self.mid, credential=credential)
            dynamics = await u.get_dynamics_new()
            
            items = dynamics.get('items', [])
            
            if not items:
                return None
            
            # 如果只有一条动态，直接返回
            if len(items) == 1:
                return items[0]
            
            # 如果有多条，比较前两条的时间戳
            try:
                # 获取发布时间戳
                ts1 = int(items[0]['modules']['module_author']['pub_ts'])
                ts2 = int(items[1]['modules']['module_author']['pub_ts'])
                
                # 返回较新的那个
                latest_dynamic = items[0] if ts1 >= ts2 else items[1]
                return latest_dynamic
                
            except (KeyError, TypeError) as e:
                # 如果数据结构异常，回退到取第一个
                logger.warning(f"⚠️ 解析动态时间戳异常 ({self.name}): {str(e)}，默认取第一条")
                return items[0]

        except Exception as e:
            logger.error(f"❌ 获取用户 {self.name} 动态失败: {str(e)}")
            return None
    
    async def get_latest_post_time(self):
        try:
            credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
            u = user.User(self.mid, credential=credential)
            
            # 并发获取视频、音频、专栏
            tasks = [u.get_videos(), u.get_audios(), u.get_articles()]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            timestamps = []
            
            # 视频
            if not isinstance(results[0], Exception):
                v_list = results[0]['list'].get('vlist', [])
                if v_list: timestamps.append(v_list[0]['created'])
            
            # 音频
            if not isinstance(results[1], Exception) and results[1].get('data'):
                timestamps.append(results[1]['data'][0]['ctime'] / 1000)
            
            # 专栏
            if not isinstance(results[2], Exception) and results[2].get('articles'):
                timestamps.append(results[2]['articles'][0]['publish_time'])
            
            return max(timestamps) if timestamps else None
        except Exception:
            return None

# === 业务逻辑函数 ===

async def check_login_status():
    """检查本地Cookies是否有效"""
    cookie_file = Path("cookies.json")
    if cookie_file.exists():
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                loaded_cookies = json.load(f)
                config.set_user_cookies(loaded_cookies)
            
            try:
                credential = user.Credential.from_cookies(config.cookies)
                u = user.User(config.uid, credential)
                info = await u.get_user_info()
                st.success(f"✅ Cookies有效！当前账号：{info['name']} (UID:{info['mid']})")
                return True
            except Exception as e:
                st.error(f"⚠️ cookies已失效：{str(e)}")
                return False
        except Exception as e:
            st.error(f"⚠️ cookies文件损坏：{str(e)}")
            return False
    return False

async def is_in_special_group_ui():
    """自动添加白名单逻辑"""
    try:
        logger.info("🔄 正在自动添加白名单（互关/特关）...")
        credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
        
        friends_list = []
        try:
            rel = await user.get_self_friends(credential)
            rel_list = rel.get("list", [])
            for iuser in rel_list:
                friends_list.append(iuser.get("mid"))
        except Exception as e:
            logger.error(f"❌ 获取互关失败：{str(e)}")

        special_list = []
        special_sn = 1
        await asyncio.sleep(2) 

        while True:
            try:
                rel_list = await user.get_self_special_followings(credential, pn=special_sn)
                if not rel_list:
                    break
                elif rel_list[0] in special_list:
                    break
                else:
                    special_list.extend(rel_list)
                special_sn += 1
                await asyncio.sleep(1)
            except Exception:
                break
        
        unique_id = set()
        count = 0
        for u in friends_list + special_list:
            if u not in unique_id:
                unique_id.add(u)
                if u not in config.ignore_list:
                    config.ignore_list.append(u)
                    count += 1
        
        logger.info(f"✅ 已将 {count} 个用户自动加入白名单")

    except Exception as e:
        logger.error(f"❌ 自动添加白名单出错: {str(e)}")

async def get_follow_list_ui(status_placeholder):
    pn = 1
    followed_list = []
    has_more = True
    
    logger.info("📦 开始获取关注列表...")
    
    while has_more:
        api_url = f"https://api.bilibili.com/x/relation/followings?vmid={config.uid}&pn={pn}&ps={config.ps}"
        try:
            # 异步请求网络
            response = await asyncio.to_thread(
                requests.get, 
                api_url, 
                headers=config.headers, 
                cookies=config.cookies
            )
            
            resp = response.json()
            if resp["code"] != 0:
                logger.error(f"请求关注列表失败: {resp.get('message')}")
                break
                
            data = resp.get("data", {})
            user_list = data.get("list", [])
            
            if not user_list:
                break

            for iuser in user_list:
                followed = FollowedUser(iuser.get("mid"), iuser.get("uname"))
                followed_list.append(followed)

            status_placeholder.text(f"正在爬取第 {pn} 页，已获取 {len(followed_list)} 个用户...")
            pn += 1
            await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"爬取列表异常: {str(e)}")
            break

    logger.info(f"📊 共获取到 {len(followed_list)} 个关注用户")
    return followed_list

async def unfollow_user_action(uid, name):
    try:
        credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
        u = user.User(uid=uid, credential=credential)
        await u.modify_relation(relation=user.RelationType.UNSUBSCRIBE)
        return True, f"🚫 已取关：{name} ({uid})"
    except Exception as e:
        return False, f"❌ 取关失败 {name}: {str(e)}"

async def process_task(progress_bar, status_text):
    start_ts = time.time()
    logger.info(f"========= 任务开始 =========")
    
    if config.AUTO_ADD_IGNORE:
        await is_in_special_group_ui()

    followed_list = await get_follow_list_ui(status_text)
    
    if not followed_list:
        logger.info("未获取到关注用户，任务结束。")
        return

    total = len(followed_list)
    stats = {'success': 0, 'fail': 0, 'skip': 0}
    current_ts = time.time()

    logger.info("🚀 开始分析用户活跃度...")

    for i, iuser in enumerate(followed_list):
        # 更新进度
        progress = (i + 1) / total
        progress_bar.progress(progress)
        status_text.text(f"正在处理 [{i+1}/{total}]: {iuser.name}")

        # 跳过逻辑
        if i < config.SKIP_NUM:
            logger.info(f"⏭️ 跳过第 {i+1} 位用户: {iuser.name}")
            stats['skip'] += 1
            continue

        handle_user = FollowedUser(iuser.mid, iuser.name)
        should_delete = False
        reason = ""

        # 白名单检查
        if iuser.mid in config.ignore_list:
            reason = f"🛡️ 用户 {iuser.name} 在白名单中，跳过。"
        elif iuser.name == "账号已注销":
             if config.REMOVE_DELETED_USER:
                 should_delete = True
                 reason = "💀 账号已注销，执行取关。"
             else:
                 reason = "💀 账号已注销，保留。"
        else:
            delay = random.randint(config.LAG_START, config.LAG_END)
            status_text.text(f"正在分析: {iuser.name} (等待 {delay}s)...")
            await asyncio.sleep(delay)

            # 根据配置选择检测方式
            if config.DETECT_TYPE == 0:
                last_active_data = await handle_user.get_latest_dynamic()
                if last_active_data and 'modules' in last_active_data:
                    last_active_ts = last_active_data['modules']['module_author']['pub_ts']
                else:
                    last_active_ts = None
            else:
                last_active_ts = await handle_user.get_latest_post_time()
            
            type_str = "动态" if config.DETECT_TYPE == 0 else "投稿"
            
            if last_active_ts is None:
                if config.REMOVE_EMPTY_DYNAMIC:
                    should_delete = True
                    reason = f"📉 {iuser.name} 无历史{type_str}，执行取关。"
                else:
                    reason = f"📉 {iuser.name} 无历史{type_str}，忽略。"
            else:
                last_active_ts = int(last_active_ts)
                past_days = int((current_ts - last_active_ts) / 86400)
                
                if past_days > config.INACTIVE_THRESHOLD:
                    should_delete = True
                    reason = f"🗓️ {iuser.name} 上次活跃 {past_days} 天前 (> {config.INACTIVE_THRESHOLD}天)，取关。"
                else:
                    reason = f"✅ {iuser.name} 上次活跃 {past_days} 天前，保留。"

        logger.info(reason)

        if should_delete:
            success, msg = await unfollow_user_action(iuser.mid, iuser.name)
            logger.info(msg)
            if success:
                stats['success'] += 1
            else:
                stats['fail'] += 1
        
    used_time = str(timedelta(seconds=int(time.time()-start_ts)))
    logger.info(f"🏁 任务完成！耗时: {used_time}")
    logger.info(f"统计: 成功取关 {stats['success']} | 失败 {stats['fail']} | 跳过 {stats['skip']}")
    logger.info(f"========= 任务结束 =========")

# === UI 主体 ===

with st.sidebar:
    st.header("🛠️ 参数配置")
    
    config.DETECT_TYPE = st.selectbox(
        "检测类型", 
        options=[0, 1], 
        format_func=lambda x: "最新动态" if x == 0 else "最新投稿",
        index=config.DETECT_TYPE
    )
    
    config.ps = st.slider("每页爬取数量", 1, 50, config.ps)
    
    config.INACTIVE_THRESHOLD = st.number_input(
        "不活跃天数阈值 (天)", 
        min_value=0, 
        value=config.INACTIVE_THRESHOLD
    )
    
    config.SKIP_NUM = st.number_input(
        "跳过最近关注人数", 
        min_value=0, 
        value=config.SKIP_NUM,
        help="防止误删刚关注还没有动态的UP主"
    )
    
    c1, c2 = st.columns(2)
    config.LAG_START = c1.number_input("最小延迟(s)", 0, 60, config.LAG_START)
    config.LAG_END = c2.number_input("最大延迟(s)", config.LAG_START, 120, config.LAG_END)
    
    st.markdown("---")
    st.subheader("⚠️ 危险选项")
    config.REMOVE_EMPTY_DYNAMIC = st.checkbox("移除无动态/投稿用户", config.REMOVE_EMPTY_DYNAMIC)
    config.REMOVE_DELETED_USER = st.checkbox("移除已注销用户", config.REMOVE_DELETED_USER)
    
    st.markdown("---")
    st.subheader("🛡️ 白名单设置")
    config.AUTO_ADD_IGNORE = st.checkbox("自动添加互关/特关到白名单", config.AUTO_ADD_IGNORE)
    
    ignore_str = st.text_area("手动白名单 UID (空格分隔)", value=" ".join(map(str, config.ignore_list)))
    try:
        if ignore_str.strip():
            config.ignore_list = list(map(int, ignore_str.strip().split()))
        else:
            config.ignore_list = []
    except ValueError:
        st.error("白名单格式错误，请输入数字UID")

st.title("🧹 B站关注列表清理助手")

# 登录模块
login_container = st.container()
with login_container:
    if not config.cookies:
        st.info("尚未检测到登录状态")
        
        # 登录按钮
        if st.button("扫码登录", key="login_btn"):
            qr_placeholder = st.empty()
            status_text_login = st.empty()
            
            try:
                # 1. 生成二维码
                qr = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB)
                asyncio.run(qr.generate_qrcode())
                
                # 2. 保存并显示图片
                pic = qr.get_qrcode_picture()
                img_path = "qr.jpg"
                pic.to_file(img_path)
                qr_placeholder.image(img_path, caption="请使用B站App扫码", width=250)
                
                status_text_login.info("⏳ 等待扫码中...")
                
                # 3. 循环轮询状态
                for _ in range(120): # 超时限制 120次 * 2秒 = 4分钟
                    status = asyncio.run(qr.check_state())
                    
                    if status == login_v2.QrCodeLoginEvents.SCAN:
                        status_text_login.info("正在等待扫描...")
                    
                    elif status == login_v2.QrCodeLoginEvents.CONF:
                        status_text_login.warning("👉 已扫描，请点击 [确认登录]")
                        
                    elif status == login_v2.QrCodeLoginEvents.DONE:
                        status_text_login.success("🎉 登录成功！")
                        qr_placeholder.empty()
                        
                        # 保存 Cookies
                        cookies = qr.get_credential().get_cookies()
                        config.set_user_cookies(cookies)
                        with open("cookies.json", 'w', encoding='utf-8') as f:
                            json.dump(cookies, f, ensure_ascii=False, indent=2)
                        
                        time.sleep(1)
                        st.rerun() 
                        break
                        
                    elif status == login_v2.QrCodeLoginEvents.TIMEOUT:
                        status_text_login.error("❌ 二维码已过期，请点击按钮重新生成")
                        break
                    
                    time.sleep(2)
            except Exception as e:
                st.error(f"登录过程出错: {str(e)}")
        
        if st.button("尝试加载本地Cookies"):
            if asyncio.run(check_login_status()):
                st.rerun()
    else:
        st.success(f"已登录 (UID: {config.uid})")
        if st.button("退出登录/切换账号"):
            config.cookies = None
            Path("cookies.json").unlink(missing_ok=True)
            st.rerun()

st.markdown("---")

# 运行控制区域
start_btn = st.button("🚀 开始清理", disabled=not config.cookies)

progress_bar = st.progress(0)
status_text = st.empty()

# 日志区域配置
log_expander = st.expander("📜 运行日志 (实时更新 + 本地保存)", expanded=True)
log_container = log_expander.empty()

# 绑定 Streamlit Handler 到当前容器
# 注意：每次rerun都会重新绑定，确保日志显示在最新的容器里
st_handler = None
for h in logger.handlers:
    if isinstance(h, StreamlitHandler):
        st_handler = h
        break

if not st_handler:
    st_handler = StreamlitHandler(log_container)
    logger.addHandler(st_handler)
else:
    st_handler.log_container = log_container

if start_btn:
    # 清空旧日志显示 (UI层面)
    st_handler.log_text = ""
    log_container.code("任务启动...", language='text')
    
    # 运行主逻辑
    asyncio.run(process_task(progress_bar, status_text))
    st.success("✅ 所有任务执行完毕")
