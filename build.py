import PyInstaller.__main__
import os
import shutil
import streamlit
import sys
from PyInstaller.utils.hooks import collect_all

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

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
COMMON_HIDDEN_IMPORTS = [
    '--hidden-import=bilibili_api',
    '--hidden-import=httpx',
    '--hidden-import=aiohttp',
    '--hidden-import=tqdm',
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
        '--noconsole',
        '--distpath=dist',
        f'--add-data={datas[0]}',
        f'--add-data={datas[1]}',
        f'--add-data={datas[2]}',
        '--copy-metadata=streamlit',
        '--hidden-import=streamlit',
    ]
    
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
        import importlib.util
        if not (importlib.util.find_spec("httpx") or importlib.util.find_spec("aiohttp")):
            print("Warning: httpx or aiohttp not found.")
        
        build_terminal()
        print("-" * 30)
        build_webui()
        print("-" * 30)
        print("Build Finished Successfully!")
    except Exception as e:
        print(f"Build Failed: {e}")
