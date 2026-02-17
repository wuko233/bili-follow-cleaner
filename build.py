import PyInstaller.__main__
import os
import shutil
import streamlit
import sys
from PyInstaller.utils.hooks import collect_all

# === 配置 ===
WEB_SCRIPT_NAME = "app.py"
TERMINAL_SCRIPT_NAME = "main.py"
WEB_EXE_NAME = "BiliCleaner_WebUI"
TERMINAL_EXE_NAME = "BiliCleaner_Terminal"

def get_streamlit_path():
    """获取 streamlit 库的安装路径"""
    return os.path.dirname(streamlit.__file__)

def create_web_runner():
    """创建一个引导脚本来启动 Streamlit"""
    code = f"""
import sys
import os
from streamlit.web import cli as stcli

def resolve_path(path):
    if getattr(sys, '_MEIPASS', False):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.getcwd(), path)

if __name__ == '__main__':
    # 强制设置 Python 路径以确保能找到依赖
    sys.path.append(os.getcwd())
    
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("{WEB_SCRIPT_NAME}"),
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())
"""
    with open("web_runner.py", "w", encoding="utf-8") as f:
        f.write(code)

# 定义通用的隐式导入，解决 bilibili_api 找不到请求库的问题
# 这些库是 bilibili_api 底层依赖的，PyInstaller 经常漏掉
COMMON_HIDDEN_IMPORTS = [
    '--hidden-import=bilibili_api',
    '--hidden-import=httpx',
    '--hidden-import=aiohttp',
    '--hidden-import=tqdm',
    # 如果你安装了 curl_cffi，bilibili_api 会优先用它，必须强制收集
    '--collect-all=curl_cffi',
    '--collect-all=bilibili_api',
]

def build_terminal():
    print(f">>> 正在构建终端版程序 [{TERMINAL_EXE_NAME}]...")
    
    args = [
        TERMINAL_SCRIPT_NAME,
        f'--name={TERMINAL_EXE_NAME}',
        '--onefile',
        '--clean',
        '--console',
        '--distpath=dist',
    ]
    
    # 加入通用依赖修复
    args.extend(COMMON_HIDDEN_IMPORTS)
    
    PyInstaller.__main__.run(args)
    print(">>> 终端版构建完成。")

def build_webui():
    print(f">>> 正在构建 WebUI 版程序 [{WEB_EXE_NAME}]...")
    
    create_web_runner()
    st_path = get_streamlit_path()
    sep = ';' if os.name == 'nt' else ':'
    
    datas = [
        f"{WEB_SCRIPT_NAME}{sep}.",
        f"{os.path.join(st_path, 'static')}{sep}streamlit/static",
        f"{os.path.join(st_path, 'runtime')}{sep}streamlit/runtime",
    ]

    args = [
        'web_runner.py',
        f'--name={WEB_EXE_NAME}',
        '--onefile',
        '--clean',
        '--noconsole', # 如果调试可以改为 --console
        '--distpath=dist',
        f'--add-data={datas[0]}',
        f'--add-data={datas[1]}',
        f'--add-data={datas[2]}',
        '--copy-metadata=streamlit',
        '--hidden-import=streamlit',
    ]
    
    # 加入通用依赖修复
    args.extend(COMMON_HIDDEN_IMPORTS)

    PyInstaller.__main__.run(args)
    
    if os.path.exists("web_runner.py"):
        os.remove("web_runner.py")
        
    print(">>> WebUI 版构建完成。")

if __name__ == "__main__":
    if os.path.exists("build"):
        shutil.rmtree("build")
    if os.path.exists("dist"):
        shutil.rmtree("dist")

    try:
        # 1. 确保环境里至少安装了一个请求库
        import importlib.util
        if not (importlib.util.find_spec("httpx") or importlib.util.find_spec("aiohttp")):
            print("⚠️ 警告: 检测到环境中未安装 httpx 或 aiohttp。")
            print("请先运行: pip install httpx aiohttp")
            # 不退出，尝试继续
        
        build_terminal()
        print("-" * 30)
        build_webui()
        print("-" * 30)
        print("✅ 构建全部完成！")
    except Exception as e:
        print(f"❌ 构建失败: {e}")
