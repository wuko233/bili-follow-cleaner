import json
import logging
import random
import time
from pathlib import Path

import requests
from bilibili_api import login_v2, sync, user


# 初始化参数
ps = 50  # 一次爬取的用户数
ignore_list = [] # 手动白名单
INACTIVE_THRESHOLD = 365 # 不活跃天数阈值
SKIP_NUM = 0 # 跳过最近关注的n位用户
LAG_START = 5
LAG_END = 20
AUTO_ADD_IGNORE = True
logging.basicConfig(filename='unfollow.log', level=logging.INFO)


async def login() -> None:
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

def show_current_parameters():
    """显示当前参数配置"""
    print("\n当前参数配置：")
    print(f"1. 每页爬取数量：{ps}")
    print(f"2. 白名单用户数：{len(ignore_list)}")
    print(f"3. 自动添加白名单（互关/特关）：{'是' if AUTO_ADD_IGNORE else '否'}")
    print(f"4. 不活跃天数阈值：{INACTIVE_THRESHOLD}天")
    print(f"5. 跳过最近关注数：{SKIP_NUM}")
    print(f"6. 请求延迟区间：{LAG_START}-{LAG_END}秒")
    
def set_parameter():
    """交互式参数配置入口"""
    global ps, INACTIVE_THRESHOLD, SKIP_NUM, LAG_START, LAG_END, AUTO_ADD_IGNORE
    
    while True:
        show_current_parameters()
        msg = input("\n是否要修改参数？[y/n]：").strip().lower()
        
        if msg in {'n', 'no'}:
            return
        elif msg in {'y', 'yes'}:
            break
        else:
            print("输入无效，请输入 y(yes) 或 n(no)")
            continue

    # 配置每页数量
    while True:
        try:
            new_ps = int(input(f"\n请输入每页爬取数量（当前：{ps}）："))
            if 1 <= new_ps <= 50:
                ps = new_ps
                break
            print("请输入1-50之间的整数")
        except ValueError:
            print("请输入有效的数字")

    # 配置白名单
    if input("\n是否需要修改白名单？[y/n]：").lower() == 'y':
        print("\n当前白名单用户：", ignore_list)
        try:
            new_list = list(map(int, 
                input("请输入要添加的UID（多个用空格分隔，留空取消）：").split()))
            ignore_list.extend(new_list)
            print(f"已添加{len(new_list)}个白名单用户")
        except ValueError:
            print("输入包含无效UID，已取消修改")

    # 配置不活跃阈值
    while True:
        try:
            new_threshold = int(input(f"\n请输入不活跃天数阈值（当前：{INACTIVE_THRESHOLD}）："))
            if new_threshold >= 0:
                INACTIVE_THRESHOLD = new_threshold
                break
            print("天数不能为负数")
        except ValueError:
            print("请输入有效的整数")

    # 配置跳过数量
    while True:
        try:
            new_skip = int(input(f"\n请输入要跳过的最近关注数（当前：{SKIP_NUM}）："))
            if new_skip >= 0:
                SKIP_NUM = new_skip
                break
            print("请输入非负数")
        except ValueError:
            print("请输入有效的整数")

    # 配置延迟区间
    while True:
        print(f"当前随机请求延迟区间：{LAG_START}-{LAG_END}秒")
        print("注意：延迟过小可能触发-352风控。默认延迟基本不会触发风控（就是慢点）")
        if input("\n是否需要修改延迟？[y/n]：").lower() == 'y':
            try:
                
                new_start = int(input(f"\n请输入最小延迟秒数（当前：{LAG_START}）："))
                new_end = int(input("请输入最大延迟秒数（当前：{}）：".format(LAG_END)))
                if 0 <= new_start <= new_end:
                    LAG_START, LAG_END = new_start, new_end
                    break
                print("延迟范围无效（最小 <= 最大）")
            except ValueError:
                print("请输入有效的整数")

    print("\n参数更新完成！")
    show_current_parameters()
    

async def is_in_special_group():
    try:
        print("正在自动添加白名单")
        credential = user.Credential(sessdata=cookies["SESSDATA"], bili_jct=cookies["bili_jct"])
        special_sn = 1
        friends_list = []
        rel = await user.get_self_friends(credential)
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

        unique_id = set()
        for u in friends_list + special_list:
            if u not in unique_id:
                unique_id.add(u)
                ignore_list.append(u)
        print("已完成自动添加白名单")
        return
    except Exception as e:
        print("出现错误，请查看日志")
        print(str(e))
        logging.error(f"添加白名单失败：{str(e)}")
        exit
        return False

if __name__ == '__main__':
    sync(login())
    set_parameter()
    if AUTO_ADD_IGNORE :
        success = sync(is_in_special_group())
    print("3s后开始执行取关脚本, CTRL+C终止程序：")
    for i in range(3, 0):
        print(i)
        time.sleep(1)


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
                if resp["code"] == -352:
                    return -352
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
    time.sleep(random.randint(LAG_START, LAG_END))

print(f"共获取到 {FollowedUser.user_count} 个关注用户：")
logging.info(f"共获取到 {FollowedUser.user_count} 个关注用户")



current_ts = time.time()
unfollow_success_count = 0
unfollow_fail_count = 0
for i, iuser in enumerate(followed_list, 1):
    if i < SKIP_NUM:
        print(f"skip:.{i}")
        continue
    print(f"{i:3d}. UID: {iuser.mid}\t用户名: {iuser.name}")
    last_active_ts = iuser.get_latest_dynamic(iuser.mid)
    if last_active_ts == -352:
        print("触发风控，已停止程序，请查看日志！")
        logging.error("风控！")
        exit
    if last_active_ts is None:
        print(f"用户{iuser.name}({iuser.mid})没发过动态，已忽略。")
        continue
    timeArray = time.localtime(last_active_ts)
    past_days = int((current_ts - last_active_ts) / 86400)
    print(f"上次发动态时间：{time.strftime('%Y-%m-%d %H:%M:%S', timeArray)}，{past_days}天前。")
    if past_days > INACTIVE_THRESHOLD:
        if iuser.mid in ignore_list:
            print(f"用户{iuser.name}({iuser.mid})位于白名单，已忽略。")
        else:
            status, message = sync(unfollow_user(iuser.mid, iuser.name))
            # status, message = True, f"用户{iuser.name}({iuser.mid})已被虚拟取关"
            if status:
                print(message)
                unfollow_success_count += 1
            else: 
                print(message)
                unfollow_fail_count += 1
    time.sleep(random.randint(LAG_START,LAG_END))

print(f"取关成功{unfollow_success_count}个，失败{unfollow_fail_count}个！")
logging.info(f"取关成功{unfollow_success_count}个，失败{unfollow_fail_count}个！")