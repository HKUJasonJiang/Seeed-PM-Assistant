"""Prepare the project-local Windows environment, using the user's configured pip index."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import struct
import sys
import time

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


def main():
    if sys.argv[1:]==["--verify"]:return 0 if ready() else 1
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from launch import arguments, open_existing
    args=arguments()
    already=open_existing(args)
    if already is not None:return already
    try:
        with setup_lock():
            if not verify():
                probe=[str(VENV_PYTHON),"-I","-c","import sys,struct;sys.exit(0 if sys.version_info[:2] in ((3,12),(3,13)) and struct.calcsize('P')==8 else 1)"]
                usable=VENV_PYTHON.is_file() and subprocess.run(probe,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
                if not usable:
                    print("Setting up this project's Python environment...",flush=True)
                    subprocess.run([sys.executable,"-I","-B","-m","venv",str(VENV)],check=True)
                print("Installing the two required packages from your configured Python package source...",flush=True)
                subprocess.run([str(VENV_PYTHON),"-I","-B","-m","pip","--disable-pip-version-check","install","--only-binary=:all:","--force-reinstall","-r",str(REQUIREMENTS)],check=True)
                if not verify():raise RuntimeError("Python could not import the installed packages. Check your Python installation and try again.")
        return subprocess.run([str(VENV_PYTHON),"-I","-B",str(ROOT/"tools"/"launch.py"),*sys.argv[1:]],cwd=ROOT).returncode
    except (subprocess.CalledProcessError,OSError,RuntimeError) as exc:
        print("Setup could not finish. Check write access to this folder, Python 3.12/3.13, and access to your approved package source.",file=sys.stderr)
        if isinstance(exc,RuntimeError):print(str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":raise SystemExit(main())
