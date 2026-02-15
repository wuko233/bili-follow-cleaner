from datetime import timedelta
import json
import logging
import random
import time
from pathlib import Path

import requests
from bilibili_api import login_v2, sync, user


# 初始化参数
class Config:
    def __init__(self):
        self.ps = 50  # 一次爬取的用户数
        self.ignore_list = [] # 手动白名单
        self.INACTIVE_THRESHOLD = 365 # 不活跃天数阈值
        self.SKIP_NUM = 0 # 跳过最近关注的n位用户
        self.DETECT_TYPE = 0 # 0 = 动态， 1 = 投稿（视频/音频/专栏）
        self.REMOVE_EMPTY_DYNAMIC = False
        self.REMOVE_DELETED_USER = False
        self.LAG_START = 5
        self.LAG_END = 20
        self.AUTO_ADD_IGNORE = True
    
    def set_user_cookies(self, cookies):
        self.cookies = cookies
        self.uid = cookies["DedeUserID"]
        self.headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{self.uid}/"
        }

logging.basicConfig(filename='unfollow.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class APIExpection:
    """API异常"""
    def __init__(self, message, status_code):
        self.message = message
        self.status_code = status_code
        super().__init__(f"状态码 {status_code}: {message}")

async def login() -> None:
    cookie_file = Path("cookies.json")

    if cookie_file.exists():

        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                config.set_user_cookies(json.load(f))
            
            try:
                uid = config.uid
                cookies = config.cookies
                credential = user.Credential.from_cookies(cookies)
                u = user.User(uid, credential)
                await user.get_self_coins(credential) # 用于验证cookies状态
                info = await u.get_user_info()
                print("检测到有效cookies，自动登录成功！\n")
                print(f"当前账号：\n名称：{info["name"]}\nUID:{info["mid"]}")
                return True, cookies
            except Exception as e:
                print(f"cookies已失效：{str(e)}")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"cookies文件损坏：{str(e)}")

    print("无有效cookies，开始扫码登录...")

    qr = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB) # 生成二维码登录实例，平台选择网页端
    await qr.generate_qrcode()                                          # 生成二维码
    pic = qr.get_qrcode_picture()
    pic.to_file("./qr.jpg")
    print(qr.get_qrcode_terminal())                                     # 生成终端二维码文本，打印
    print("Ctrl加+/-可缩放终端大小\n")
    print("如以上内容为乱码，请手动打开目录中qr.jpg扫描")

    while not qr.has_done():                                            # 在完成扫描前轮询
        status = await qr.check_state()
        if (str(status) != "QrCodeLoginEvents.SCAN"):
            print(status)
        time.sleep(1)
    cookies = qr.get_credential().get_cookies()
    config.set_user_cookies(cookies)
    with open(cookie_file, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print("登录成功，已保存Cookies")

def show_current_parameters():
    """显示当前参数配置"""
    print("\n当前参数配置：")
    print(f"0. 爬取类型： {"动态" if config.DETECT_TYPE == 0 else "视频"}")
    print(f"1. 每页爬取数量：{config.ps}")
    print(f"2. 白名单用户数：{len(config.ignore_list)}")
    print(f"3. 自动添加白名单（互关/特关）：{'是' if config.AUTO_ADD_IGNORE else '否'}")
    print(f"4. 不活跃天数阈值：{config.INACTIVE_THRESHOLD}天")
    print(f"5. 跳过最近关注数：{config.SKIP_NUM}")
    print(f"6. 是否删除无动态用户：{'是' if config.REMOVE_EMPTY_DYNAMIC else '否'}")
    print(f"7. 是否直接删除已注销用户：{'是' if config.REMOVE_DELETED_USER else '否'}")
    print(f"8. 请求延迟区间：{config.LAG_START}-{config.LAG_END}秒")

def set_parameter():
    """交互式参数配置入口"""
    while True:
        show_current_parameters()
        print("!!!操作不可逆，强烈建议检查一遍!!!")
        msg = input("\n是否要修改参数？[y/n]：").strip().lower()
        
        if msg in {'n', 'no'}:
            return
        elif msg in {'y', 'yes'}:
            break
        else:
            print("输入无效，请输入 y(yes) 或 n(no)")
            continue

    # 配置爬取种类
    while True:
        print("请选择检测类型：\n最新动态 请输入0\n最新投稿（视频/音频/专栏）请输入1")
        msg = input("\n请选择检测类型：").strip().lower()
        
        if msg == "0":
            config.DETECT_TYPE = 0
            print("已选择最新动态。\n")
            break
        elif msg == "1":
            config.DETECT_TYPE = 1
            print("已选择最新投稿。\n")
            break
        else:
            print("输入无效，请输入 0 或 1")
            continue

    # 配置每页数量
    while True:
        try:
            new_ps = int(input(f"\n请输入每页爬取数量（当前：{config.ps}）："))
            if 1 <= new_ps <= 50:
                config.ps = new_ps
                break
            print("请输入1-50之间的整数")
        except ValueError:
            print("请输入有效的数字")

    # 配置白名单
    if input("\n是否需要修改白名单？[y/n]：").lower() == 'y':
        print("\n当前白名单用户：", config.ignore_list)
        try:
            new_list = list(map(int, input("请输入要添加的UID（多个用空格分隔，留空取消）：").split()))
            config.ignore_list.extend(new_list)
            print(f"已添加{len(new_list)}个白名单用户")
        except ValueError:
            print("输入包含无效UID，已取消修改")

    # 配置是否自动添加白名单
    while True:
        print(f"\n!!!自动添加白名单!!!\n默认启用\n当前状态：{'是' if config.AUTO_ADD_IGNORE else '否'}")
        msg = input("是否要自动添加白名单？[y/n]：").strip().lower()
        
        if msg in {'n', 'no'}:
            config.AUTO_ADD_IGNORE = False
            break
        elif msg in {'y', 'yes'}:
            config.AUTO_ADD_IGNORE = True
            break
        else:
            print("输入无效，请输入 y(yes) 或 n(no)")
            continue

    # 配置不活跃阈值
    while True:
        try:
            new_threshold = int(input(f"\n请输入不活跃天数阈值（当前：{config.INACTIVE_THRESHOLD}）："))
            if new_threshold >= 0:
                config.INACTIVE_THRESHOLD = new_threshold
                break
            print("天数不能为负数")
        except ValueError:
            print("请输入有效的整数")

    # 配置跳过数量
    while True:
        try:
            new_skip = int(input(f"\n请输入要跳过的最近关注数（当前：{config.SKIP_NUM}）："))
            if new_skip >= 0:
                config.SKIP_NUM = new_skip
                break
            print("请输入非负数")
        except ValueError:
            print("请输入有效的整数")

    # 配置是否移除空动态用户
    while True:
        print(f"\n!!!移除无动态用户会直接取关没发过动态的用户!!!\n默认禁用\n当前状态：{'是' if config.REMOVE_EMPTY_DYNAMIC else '否'}")
        msg = input("是否要移除无动态用户？[y/n]：").strip().lower()
        
        if msg in {'n', 'no'}:
            config.REMOVE_EMPTY_DYNAMIC = False
            break
        elif msg in {'y', 'yes'}:
            config.REMOVE_EMPTY_DYNAMIC = True
            break
        else:
            print("输入无效，请输入 y(yes) 或 n(no)")
            continue

    # 配置是否移除已注销用户
    while True:
        print(f"\n!!!移除已注销用户会直接取关名为“账号已注销”的用户且无法找回!!!\n默认禁用\n当前状态：{'是' if config.REMOVE_DELETED_USER else '否'}")
        msg = input("是否要移除已注销用户？[y/n]：").strip().lower()
        
        if msg in {'n', 'no'}:
            config.REMOVE_DELETED_USER = False
            break
        elif msg in {'y', 'yes'}:
            config.REMOVE_DELETED_USER = True
            break
        else:
            print("输入无效，请输入 y(yes) 或 n(no)")
            continue

    # 配置延迟区间
    while True:
        print(f"\n当前随机请求延迟区间：{config.LAG_START}-{config.LAG_END}秒")
        print("注意：延迟过小可能触发-352风控。默认延迟基本不会触发风控（就是慢点）")
        if input("是否需要修改延迟？[y/n]：").lower() == 'y':
            try:
                
                new_start = int(input(f"\n请输入最小延迟秒数（当前：{config.LAG_START}）："))
                new_end = int(input("请输入最大延迟秒数（当前：{}）：".format(config.LAG_END)))
                if 0 <= new_start <= new_end:
                    config.LAG_START, config.LAG_END = new_start, new_end
                    break
                print("延迟范围无效（最小 <= 最大）")
            except ValueError:
                print("请输入有效的整数")
        else:
            break

    print("\n参数更新完成！")
    show_current_parameters()
    

async def is_in_special_group():
    try:
        print("\n正在自动添加白名单")
        credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
        
        special_sn = 1
        friends_list = []
        try:
            rel = await user.get_self_friends(credential)

        except Exception as e:
            print(f"获取互关用户失败：{str(e)}")
            logging.error(f"获取互关用户失败：{str(e)}")
            return

        rel_list = rel.get("list", [])

        if not rel_list:
            print("无互关用户")
        else:
            for iuser in rel_list:
                mid = iuser.get("mid")
                uname = iuser.get("uname")
                friends_list.append(mid)
                print(f"用户{uname}({mid})已互关，已自动添加至白名单。")
        special_list = []

        time.sleep(random.randint(config.LAG_START,config.LAG_END))

        while 1:
            rel_list = await user.get_self_special_followings(credential, pn=special_sn)
            if not rel_list:
                print("无特别关注用户")
                break
            elif rel_list[0] in special_list:
                print("获取特别关注完成")
                break
            else:
                for mid in rel_list:
                    special_list.append(mid)
                    print(f"用户({mid})已特殊关注，已自动添加至白名单。")
            special_sn += 1
            time.sleep(random.randint(config.LAG_START,config.LAG_END))

        unique_id = set()
        for u in friends_list + special_list:
            if u not in unique_id:
                unique_id.add(u)
                config.ignore_list.append(u)
        print("已完成自动添加白名单\n")
        return
    
    except Exception as e:
        print("出现错误:")
        print(str(e))
        logging.error(f"添加白名单失败：{str(e)}")
        raise

class FollowedUser:
    user_count = 0

    def __init__(self, mid, uname):
        self.mid = mid
        self.name = uname
        FollowedUser.user_count += 1

    def get_latest_dynamic(self, uid):
        # TODO: 固定API链接，待切换至bilibili_api接口
        api_url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
        
        try:
            params = {
                "host_mid": str(uid)
            }

            response = requests.get(
                api_url,
                params=params,
                headers=config.headers,
                cookies=config.cookies,
                timeout=10
            )
            resp = response.json()

            if resp["code"] != 0:
                print(resp)
                print(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
                logging.error(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
                if resp["code"] == -352:
                    raise APIExpection("账号可能被风控限制，请稍后重试", -352)
                return None

            items = resp["data"]["items"]
            if not items:
                logging.info("该用户暂无动态")
                return None
            dynamic1 = items[0]["modules"]["module_author"]["pub_ts"]
            if len(items) == 1:
                publish_time = dynamic1
            else:
                dynamic2 = items[1]["modules"]["module_author"]["pub_ts"]
                publish_time = dynamic1 if int(dynamic1) > int(dynamic2) else dynamic2
            self.timestamp = publish_time
            return publish_time
        except Exception as e:
            print(f"请求异常：{str(e)}")
            logging.error(f"请求异常：{str(e)}")
        return None
    
    async def get_latest_video(self):
        """异步获取用户最新视频"""
        try:
            credential = user.Credential(sessdata=config.cookies["SESSDATA"], 
                                        bili_jct=config.cookies["bili_jct"])
            u = user.User(self.mid, credential=credential)
            
            videos = await u.get_videos()
            videos_list = videos['list'].get('vlist', [])
            latest_video = videos_list[0]
            return latest_video
        except Exception as e:
            logging.error(f"获取用户视频异常：{str(e)}")
            return
    
    async def get_latest_audios(self):
        """异步获取用户最新音频"""
        try:
            credential = user.Credential(sessdata=config.cookies["SESSDATA"], 
                                        bili_jct=config.cookies["bili_jct"])
            u = user.User(self.mid, credential=credential)
            
            audios = await u.get_audios()
            audios_list = audios.get('data', [])
            latest_audio = audios_list[0]
            return latest_audio
        except Exception as e:
            logging.error(f"获取用户音频异常：{str(e)}")
            return
        
    async def get_latest_articles(self):
        """异步获取用户最新专栏"""
        try:
            credential = user.Credential(sessdata=config.cookies["SESSDATA"], 
                                        bili_jct=config.cookies["bili_jct"])
            u = user.User(self.mid, credential=credential)
            
            articles = await u.get_articles()
            articles_list = articles.get('articles', [])
            latest_article = articles_list[0]
            return latest_article
        except Exception as e:
            logging.error(f"获取用户专栏异常：{str(e)}")
            return
    
    async def get_latest_post_time(self):
        """异步获取用户最新投稿（视频/音频/专栏）时间戳"""
        try:
            latest_video = await self.get_latest_video()
            latest_audio = await self.get_latest_audios()
            latest_article = await self.get_latest_articles()

            timestamps = []
            
            # 处理视频时间戳
            if latest_video and 'created' in latest_video:
                video_time = latest_video['created']
                timestamps.append(video_time)
            
            # 处理音频时间戳
            if latest_audio and 'ctime' in latest_audio:
                audio_time = latest_audio['ctime'] / 1000  # 转换为秒
                timestamps.append(audio_time)
            
            # 处理专栏时间戳
            if latest_article and 'publish_time' in latest_article:
                article_time = latest_article['publish_time']
                timestamps.append(article_time)
            
            if not timestamps:
                return
            
            latest_timestamp = max(timestamps)
            
            return latest_timestamp     
        except Exception as e:
            logging.error(f"获取用户最新投稿异常：{str(e)}")
            return

async def unfollow_user(uid, name = None):
    try:
        credential = user.Credential(sessdata=config.cookies["SESSDATA"], bili_jct=config.cookies["bili_jct"])
        u = user.User(uid=uid, credential=credential)
        logging.info(f"尝试取关 {name} uid:{uid}.")
        await u.modify_relation(relation=user.RelationType.UNSUBSCRIBE)
        logging.info(f"取关成功：{uid}")
        return f"取关成功：{uid}"
    except Exception as e:
        raise

def get_follow_list():
    pn = 1
    followed_list = []
    has_more = True
    while has_more:
        # TODO: 固定API链接，待切换至bilibili_api接口
        uid = config.uid
        api_url = f"https://api.bilibili.com/x/relation/followings?vmid={uid}&pn={pn}&ps={config.ps}"

        try:
            headers = config.headers
            response = requests.get(api_url, headers=headers, cookies=config.cookies)
            resp = response.json()
            
            if resp["code"] != 0:
                print(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
                logging.error(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
                raise APIExpection("非零返回", -1)
                
            data = resp.get("data", {})
            user_list = data.get("list", [])
            
            if not user_list:
                has_more = False
                break

            for iuser in user_list:
                followed = FollowedUser(
                    mid=iuser.get("mid"), 
                    uname=iuser.get("uname")
                )
                followed_list.append(followed)

            total = data.get("total", 0)
            # if len(followed_list) >= total:
            #     has_more = False
            # else:
            pn += 1

        except Exception as e:
            print("出现错误，请查看日志")
            logging.error(f"请求异常：{str(e)}")
            break
        print(f"已爬取第{pn - 1}页{FollowedUser.user_count} 个关注用户")
        time.sleep(random.randint(config.LAG_START, config.LAG_END))

    print(f"共获取到 {FollowedUser.user_count} 个关注用户：")
    logging.info(f"共获取到 {FollowedUser.user_count} 个关注用户")
    return followed_list

async def handle_follow_list(followed_list):
    current_ts = time.time()
    unfollow_success_count = 0
    unfollow_fail_count = 0

    for i, iuser in enumerate(followed_list, 1):

        handle_user = FollowedUser(iuser.mid, iuser.name)

        # 跳过前SKIP_NUM个关注用户
        if i <= config.SKIP_NUM:
            print(f"跳过用户:{i}.\t 用户名：{iuser.name}\tUID：{iuser.mid}")
            logging.info(f"跳过用户:{i}.\t 用户名：{iuser.name}\tUID：{iuser.mid}")
            continue

        # 开始处理当前用户
        print(f"{i:3d}. UID: {iuser.mid}\t用户名: {iuser.name}")
        logging.info(f"{i:3d}. UID: {iuser.mid}\t用户名: {iuser.name}")

        if iuser.mid in config.ignore_list:
            print(f"用户{iuser.name}({iuser.mid})位于白名单，已忽略。")
            logging.info(f"用户{iuser.name}({iuser.mid})位于白名单，已忽略。")
            continue
        
        will_delete = False

        if iuser.name == "账号已注销" and config.REMOVE_DELETED_USER and not will_delete:
            print(f"用户{iuser.name}({iuser.mid})已注销，执行取关操作。")
            logging.info(f"用户{iuser.name}({iuser.mid})已注销，执行取关操作。")
            will_delete = True

        if config.DETECT_TYPE == 0 and not will_delete:
            # 通过动态检测不活跃
            last_active_ts = iuser.get_latest_dynamic(iuser.mid)
            if last_active_ts == -352:
                print("触发风控，已停止程序，请查看日志！")
                logging.error("风控！")
                exit

            if last_active_ts is None and not will_delete:
                if config.REMOVE_EMPTY_DYNAMIC:
                    print(f"用户{iuser.name}({iuser.mid})没发过动态，执行取关操作。")
                    will_delete = True
                else:
                    print(f"用户{iuser.name}({iuser.mid})没发过动态，已忽略。")
                    continue
            else:
                timeArray = time.localtime(last_active_ts)
                past_days = int((current_ts - last_active_ts) / 86400)
                print(f"上次发动态时间：{time.strftime('%Y-%m-%d %H:%M:%S', timeArray)}，{past_days}天前。")

                if past_days > config.INACTIVE_THRESHOLD:
                    print(f"超过设定天数（{config.INACTIVE_THRESHOLD}），执行取关操作")
                    will_delete = True
        else:
            # 通过投稿检测不活跃
            last_active_ts = await handle_user.get_latest_post_time()
            if last_active_ts is None and not will_delete:
                if config.REMOVE_EMPTY_DYNAMIC:
                    print(f"用户{iuser.name}({iuser.mid})没发过投稿，执行取关操作。")
                    will_delete = True
                else:
                    print(f"用户{iuser.name}({iuser.mid})没发过投稿，已忽略。")
                    continue
            else:
                timeArray = time.localtime(last_active_ts)
                past_days = int((current_ts - last_active_ts) / 86400)
                print(f"上次投稿时间：{time.strftime('%Y-%m-%d %H:%M:%S', timeArray)}，{past_days}天前。")

                if past_days > config.INACTIVE_THRESHOLD:
                    print(f"超过设定天数（{config.INACTIVE_THRESHOLD}），执行取关操作")
                    will_delete = True
        
        if will_delete:
            try:
                message = sync(unfollow_user(iuser.mid, iuser.name))
                # message = f"[测试]用户{iuser.name}({iuser.mid})已被取关"
                print(message)
                logging.info(f"用户{iuser.name}({iuser.mid})已被取关")
                unfollow_success_count += 1
            except Exception as e:
                print(f"取关 {iuser.name}（{iuser.mid}） 失败：{str(e)}")
                logging.error(f"取关 {iuser.name}（{iuser.mid}） 失败：{str(e)}")
                unfollow_fail_count += 1
    
        time.sleep(random.randint(config.LAG_START,config.LAG_END))

    print(f"取关成功{unfollow_success_count}个，失败{unfollow_fail_count}个！")
    logging.info(f"取关成功{unfollow_success_count}个，失败{unfollow_fail_count}个！")

if __name__ == '__main__':

    try:
        start_ts = time.time()
        config = Config()
        sync(login())

        set_parameter()
        print("3s后开始执行取关脚本, CTRL+C终止程序：")
        for i in range(3, 0, -1):
            print(f"倒计时:{i}")
            time.sleep(1)
        if config.AUTO_ADD_IGNORE :
            sync(is_in_special_group())
        followed_list = get_follow_list()

        print("开始处理...\n")
        sync(handle_follow_list(followed_list))

    except KeyboardInterrupt as e:
        print("已手动终止程序。")
    except APIExpection as e:
        print(f"程序调用API异常返回：{e.message}")
        logging.error(e)
    except Exception as e:
        print("程序异常终止，请查看日志。")
        logging.error(e)
    used_time = timedelta(seconds=time.time()-start_ts)
    print(f"总耗时：{used_time}")