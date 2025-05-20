import json
from bilibili_api import login_v2, sync, user
from pathlib import Path
import logging
logging.basicConfig(filename='unfollow.log', level=logging.INFO)

import time
import requests


# 初始化参数
ps = 50  # 一次爬取的用户数
ignore_list = [] # 手动白名单
INACTIVE_THRESHOLD = 180 # 不活跃天数阈值



async def main() -> None:
    global cookies, uid
    cookie_file = Path("cookies.json")
    if cookie_file.exists():
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            try:
                uid = cookies["DedeUserID"]
                u = user.User(uid,credential=user.Credential.from_cookies(cookies))
                await u.get_user_info() 
                print("检测到有效cookies，自动登录成功")
                return True, cookies
            except Exception as e:
                print(f"cookies已失效：{str(e)}")          
        except (json.JSONDecodeError, KeyError) as e:
            print(f"cookies文件损坏：{str(e)}")
    print("无有效cookies，开始扫码登录...")
    qr = login_v2.QrCodeLogin(platform=login_v2.QrCodeLoginChannel.WEB) # 生成二维码登录实例，平台选择网页端
    await qr.generate_qrcode()                                          # 生成二维码
    print(qr.get_qrcode_terminal())                                     # 生成终端二维码文本，打印
    while not qr.has_done():                                            # 在完成扫描前轮询
        status = await qr.check_state()
        if (str(status) != "QrCodeLoginEvents.SCAN"):
            print(status)
        time.sleep(1)     
    cookies = qr.get_credential().get_cookies()
    uid = cookies["DedeUserID"]
    with open(cookie_file, 'w', encoding='utf-8') as f:
        json.dump(cookies, f, ensure_ascii=False, indent=2)
    print("登录成功，已保存Cookies")

async def is_in_special_group():
        try:
            credential = user.Credential(sessdata=cookies["SESSDATA"], bili_jct=cookies["bili_jct"])
            rel = await user.get_self_friends(credential) # TODO: 当前仅获取前50个，待添加遍历
            rel_list = rel.get("list", [])
            if not rel_list:
                print("无互关用户")
            else:
                for iuser in rel_list:
                    mid = iuser.get("mid")
                    uname = iuser.get("uname")
                    ignore_list.append(mid)
                    print(f"用户{uname}({mid})已互关，已自动添加至白名单。")
            rel_list = await user.get_self_special_followings(credential) # TODO: 当前仅获取前50个，待添加遍历
            if not rel_list:
                print("无特别关注用户")
            else:
                for mid in rel_list:
                    print(f"用户({mid})已特殊关注，已自动添加至白名单。")
            return True
        except Exception as e:
            print("出现错误，请查看日志")
            print(str(e))
            logging.error(f"检查互关状态失败：{str(e)}")
            return False

if __name__ == '__main__':
    sync(main())

    print("正在自动添加白名单")
    success = sync(is_in_special_group())
    print("已完成自动添加白名单" if success else "白名单添加失败")

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
                headers=headers,
                cookies=cookies,
                timeout=10
            )
            resp = response.json()

            if resp["code"] != 0:
                print(resp)
                print("出现错误，请查看日志")
                logging.error(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
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
            print("出现错误，请查看日志")
            logging.error(f"请求异常：{str(e)}")
        return None

async def unfollow_user(uid, name = None):
    try:
        credential = user.Credential(sessdata=cookies["SESSDATA"], bili_jct=cookies["bili_jct"])
        u = user.User(uid=uid, credential=credential)
        logging.info(f"Removing {name}, uid:{uid}.")
        await u.modify_relation(relation=user.RelationType.UNSUBSCRIBE)
        return True, f"取关成功：{uid}"
    except Exception as e:
        return False, f"取关失败：{str(e)}"



pn = 1
has_more = True
followed_list = []


headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": f"https://space.bilibili.com/{uid}/"
    }

while has_more:

    # TODO: 固定API链接，待切换至bilibili_api接口
    api_url = f"https://api.bilibili.com/x/relation/followings?vmid={uid}&pn={pn}&ps={ps}"

    try:
        response = requests.get(api_url, headers=headers, cookies=cookies)
        resp = response.json()
        
        if resp["code"] != 0:
            print("出现错误，请查看日志")
            logging.error(f"请求失败，错误代码：{resp['code']}，信息：{resp.get('message', '未知错误')}")
            break
            
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
    time.sleep(1)

print(f"共获取到 {FollowedUser.user_count} 个关注用户：")



current_ts = time.time()
unfollow_success_count = 0
unfollow_fail_count = 0
for i, iuser in enumerate(followed_list, 1):
    print(f"{i:3d}. UID: {iuser.mid}\t用户名: {iuser.name}")
    last_active_ts = iuser.get_latest_dynamic(iuser.mid)
    if last_active_ts == None:
        print(f"用户{iuser.name}({iuser.mid})没发过动态，已忽略。")
        continue
    timeArray = time.localtime(last_active_ts)
    past_days = int((current_ts - last_active_ts) / 86400)
    print(f"上次发动态时间：{time.strftime("%Y-%m-%d %H:%M:%S", timeArray)}，{past_days}天前。")
    if past_days > INACTIVE_THRESHOLD:
        if iuser.mid in ignore_list:
            print(f"用户{iuser.name}({iuser.mid})位于白名单，已忽略。")
        else:
            # status, message = sync(unfollow_user(iuser.mid, iuser.name))
            status, message = True, f"用户{iuser.name}({iuser.mid})已被虚拟取关"
            if status:
                print(message)
                unfollow_success_count += 1
            else: 
                print(message)
                unfollow_fail_count += 1
    time.sleep(1)

print(f"取关成功{unfollow_success_count}个，失败{unfollow_fail_count}个！")
