"""Prepare the project-local Windows environment, using the user's configured pip index."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import struct
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from startup_report import record, failure

ROOT=Path(__file__).resolve().parents[1]
VENV=ROOT/".venv"
VENV_PYTHON=VENV/"Scripts"/"python.exe"
REQUIREMENTS=ROOT/"requirements.txt"


def ready():
    from importlib import metadata
    try:
        from PIL import Image
        from lxml import html
        if Path(sys.prefix).resolve()!=VENV or sys.implementation.name!="cpython" or sys.version_info[:2] not in {(3,12),(3,13)} or struct.calcsize("P")!=8:return False
        return all(metadata.version(name)==ver for name,ver in
                   (line.strip().split("==") for line in REQUIREMENTS.read_text("ascii").splitlines() if line.strip()))
    except (ImportError,OSError,ValueError):return False


@contextmanager
def setup_lock():
    import msvcrt
    if VENV.is_symlink():raise RuntimeError("Use a private .venv folder inside this project.")
    VENV.mkdir(exist_ok=True)
    with (VENV/".setup.lock").open("a+b") as stream:
        if stream.tell()==0:stream.write(b"1");stream.flush()
        until=time.monotonic()+150
        while True:
            try:
                stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:
                if time.monotonic()>=until:raise RuntimeError("Another installer is still working. Try Start Assistant again after it finishes.")
                time.sleep(.3)
        try:yield
        finally:
            stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


def verify():
    return VENV_PYTHON.is_file() and subprocess.run([str(VENV_PYTHON),"-I","-B",__file__,"--verify"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0


def install(command, default_code):
    result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding="utf-8",errors="replace")
    if result.returncode==0:return
    output=result.stdout.casefold()
    code=default_code
    if "certificate_verify_failed" in output or "certificate verify failed" in output:code="CERTIFICATE"
    elif any(text in output for text in ("proxyerror","connection","timed out","network is unreachable","temporary failure","getaddrinfo")):code="NETWORK"
    elif "no matching distribution" in output or "could not find a version" in output:code="PACKAGE"
    elif "access is denied" in output or "permission denied" in output:code="ACCESS"
    record(code,"exit="+str(result.returncode))
    raise RuntimeError("STARTUP_STEP_FAILED")


def main():
    if sys.argv[1:]==["--verify"]:return 0 if ready() else 1
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from launch import arguments, open_existing
    args=arguments()
    record("START",sys.implementation.name+" "+sys.version.split()[0]+" "+str(struct.calcsize("P")*8)+"-bit",reset=True)
    required=("index.html","data/catalog.js","backend/server.py","tools/launch.py","requirements.txt")
    if any(not (ROOT/name).is_file() for name in required):
        record("FILES");return 1
    already=open_existing(args)
    if already is not None:
        if args.install_dependencies:record("BUSY");return 2
        return already
    if not args.install_dependencies:
        complete=verify()
        record("READY" if complete else "BASIC")
        interpreter=str(VENV_PYTHON) if complete else sys.executable
        return subprocess.run([interpreter,"-I","-B",str(ROOT/"tools"/"launch.py"),*sys.argv[1:]],cwd=ROOT).returncode
    try:
        with setup_lock():
            if not verify():
                probe=[str(VENV_PYTHON),"-I","-c","import sys,struct;sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) and struct.calcsize('P')==8 else 1)"]
                usable=VENV_PYTHON.is_file() and subprocess.run(probe,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
                if not usable:
                    record("VENV")
                    install([sys.executable,"-I","-B","-m","venv",str(VENV)],"PYTHON")
                has_pip=subprocess.run([str(VENV_PYTHON),"-I","-B","-c","import pip"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
                if not has_pip:
                    record("PIP_REPAIR")
                    install([str(VENV_PYTHON),"-I","-B","-m","ensurepip","--upgrade"],"PYTHON")
                record("PACKAGES")
                install([str(VENV_PYTHON),"-I","-B","-m","pip","--disable-pip-version-check","install","--only-binary=:all:","--force-reinstall","--retries","2","--timeout","25","-r",str(REQUIREMENTS)],"PACKAGE")
                if not verify():raise RuntimeError("Python could not import the installed packages. Check your Python installation and try again.")
        record("READY")
        return subprocess.run([str(VENV_PYTHON),"-I","-B",str(ROOT/"tools"/"launch.py"),*sys.argv[1:]],cwd=ROOT).returncode
    except (subprocess.CalledProcessError,OSError,RuntimeError) as exc:
        failure(exc,"ACCESS" if isinstance(exc,PermissionError) else "FAILED")
        return 1


if __name__=="__main__":
    try:raise SystemExit(main())
    except (OSError,ValueError,RuntimeError) as exc:
        failure(exc,"ACCESS" if isinstance(exc,PermissionError) else "FAILED")
        raise SystemExit(1) from None
