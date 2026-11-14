"""Small, non-sensitive startup report for a fully extracted local copy."""
from datetime import datetime
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"startup-diagnostic.txt"
MESSAGES={
    "START":("开始检查启动环境", "Checking the startup environment"),
    "VENV":("正在准备项目独立 Python 环境", "Preparing this project's Python environment"),
    "PIP_REPAIR":("正在修复未完成的依赖安装工具", "Repairing an interrupted pip setup"),
    "PACKAGES":("正在通过已配置的软件源安装依赖", "Installing dependencies from the configured package source"),
    "READY":("Python 和依赖已就绪", "Python and dependencies are ready"),
    "BASIC":("本机工作台可以启动；首次更新官网资料或替换图片前，请运行“准备更新工具.cmd”", "The workbench can start. Run Prepare Data Tools.cmd before the first store update or image replacement"),
    "SERVICE":("正在启动本机工作台", "Starting the local workbench"),
    "STARTING":("工作台进程仍在启动，请稍候后重新打开同一启动入口以连接；首次启动可能受磁盘扫描影响", "The workbench process is still starting. Wait, then reopen the same launcher to connect; disk scanning can delay first launch"),
    "OPEN":("工作台已启动，可打开下方网址", "Workbench ready; open the address below"),
    "BROWSER":("浏览器未自动打开，请复制上方网址到浏览器", "Browser did not open; copy the address above into your browser"),
    "PORT":("指定端口已被占用，请使用普通启动入口自动选择端口", "The requested port is busy; use Start Assistant without --port"),
    "BUSY":("本资料目录已有服务，请先完成工作并使用停止入口", "This data folder is already in use; finish its work and use Stop Assistant"),
    "FILES":("应用文件不完整，请将整个 ZIP 全部解压到新文件夹", "Application files are missing; extract the entire ZIP into a new folder"),
    "ACCESS":("文件夹无法写入，请解压到个人有写入权限的目录后重试", "This folder is not writable; extract into a folder you can write to"),
    "NETWORK":("依赖下载失败，请由 IT 检查公司允许的软件源和网络代理，修复后重新启动", "Package download failed; ask IT to check the approved package source and proxy, then retry"),
    "CERTIFICATE":("软件下载证书校验失败，请由 IT 配置公司认可的证书，修复后重试", "Package certificate validation failed; ask IT to configure the approved certificates, then retry"),
    "PACKAGE":("软件源未提供所需版本的依赖，请由 IT 检查 requirements.txt 中的固定版本", "The package source did not provide the required versions; ask IT to check requirements.txt"),
    "PYTHON":("Python 环境创建失败，请修复 64 位 Python 3.12 或 3.13 安装后重试", "Python environment setup failed; repair 64-bit Python 3.12 or 3.13 and retry"),
    "FAILED":("工作台未启动，请把 startup-diagnostic.txt 发给维护人员；现在可打开 index.html 查询商品", "Startup failed; share startup-diagnostic.txt with support. Open index.html to browse products now"),
}


def console():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,"reconfigure"):stream.reconfigure(encoding="utf-8",errors="replace")


def record(code, detail="", reset=False):
    """Detail must be a code/version selected by the caller, never raw exceptions or output."""
    console()
    zh,en=MESSAGES[code]
    line=f"[{code}] {zh} / {en}"+(" ("+detail+")" if detail else "")
    print(line,flush=True)
    try:
        with REPORT.open("w" if reset else "a",encoding="utf-8") as stream:
            stream.write(datetime.now().isoformat(timespec="seconds")+" "+line+"\n")
    except OSError:pass


def failure(exc, code="FAILED"):
    number=getattr(exc,"winerror",None) or getattr(exc,"errno",None)
    detail=type(exc).__name__+(f" error={number}" if isinstance(number,int) else "")
    record(code,detail)
