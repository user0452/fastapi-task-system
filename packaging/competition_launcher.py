from __future__ import annotations

import argparse
import os
import re
import secrets
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

APP_TITLE = "A3 学习 AI"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8010


def bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


ROOT = bundle_root()
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def required_database_env_present() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("DATABASE_HOST", "DATABASE_USER", "DATABASE_NAME", "SECRET_KEY")
    )


def configure_database() -> bool:
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title(f"{APP_TITLE} - 首次运行配置")
    root.geometry("520x390")
    root.resizable(False, False)

    values = {
        "DATABASE_HOST": tk.StringVar(value="127.0.0.1"),
        "DATABASE_PORT": tk.StringVar(value="3306"),
        "DATABASE_USER": tk.StringVar(value="root"),
        "DATABASE_PASSWORD": tk.StringVar(value=""),
        "DATABASE_NAME": tk.StringVar(value="task_db2"),
    }
    labels = [
        ("DATABASE_HOST", "MySQL 地址"),
        ("DATABASE_PORT", "MySQL 端口"),
        ("DATABASE_USER", "MySQL 用户"),
        ("DATABASE_PASSWORD", "MySQL 密码"),
        ("DATABASE_NAME", "数据库名称"),
    ]

    tk.Label(root, text="A3 学习 AI", font=("Microsoft YaHei UI", 20, "bold")).pack(pady=(20, 4))
    tk.Label(
        root,
        text="首次运行需要连接本机 MySQL 8.x。API Key 请在登录后的设置页填写。",
        font=("Microsoft YaHei UI", 10),
    ).pack(pady=(0, 16))

    form = tk.Frame(root)
    form.pack(fill="x", padx=44)
    for row, (key, label) in enumerate(labels):
        tk.Label(form, text=label, width=14, anchor="e").grid(row=row, column=0, padx=8, pady=7)
        entry = tk.Entry(form, textvariable=values[key], width=34)
        if key == "DATABASE_PASSWORD":
            entry.configure(show="*")
        entry.grid(row=row, column=1, pady=7)

    saved = {"ok": False}

    def save() -> None:
        database_name = values["DATABASE_NAME"].get().strip()
        try:
            port = int(values["DATABASE_PORT"].get().strip())
        except ValueError:
            messagebox.showerror(APP_TITLE, "MySQL 端口必须是数字。")
            return
        if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
            messagebox.showerror(APP_TITLE, "数据库名称只能包含字母、数字和下划线。")
            return
        if not values["DATABASE_HOST"].get().strip() or not values["DATABASE_USER"].get().strip():
            messagebox.showerror(APP_TITLE, "MySQL 地址和用户不能为空。")
            return
        if not 1 <= port <= 65535:
            messagebox.showerror(APP_TITLE, "MySQL 端口范围必须为 1-65535。")
            return

        lines = [
            "APP_ENV=development",
            "ENABLE_LEGACY_ROUTES=false",
            f"DATABASE_HOST={values['DATABASE_HOST'].get().strip()}",
            f"DATABASE_PORT={port}",
            f"DATABASE_USER={values['DATABASE_USER'].get().strip()}",
            f"DATABASE_PASSWORD={values['DATABASE_PASSWORD'].get()}",
            f"DATABASE_NAME={database_name}",
            f"SECRET_KEY={secrets.token_urlsafe(48)}",
            "DEEPSEEK_API_KEY=",
            "DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "DEEPSEEK_MODEL=deepseek-v4-flash",
            "A3_MOCK_LLM=false",
            "A3_MOCK_EMBEDDING=false",
            "RAG_CHUNK_TARGET_TOKENS=96",
            "RAG_CHUNK_MAX_TOKENS=120",
            "RAG_CHUNK_OVERLAP_TOKENS=20",
            "LEARNING_MEMORY_WORKER_ENABLED=true",
        ]
        (ROOT / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
        for line in lines:
            key, value = line.split("=", 1)
            os.environ[key] = value
        saved["ok"] = True
        root.destroy()

    buttons = tk.Frame(root)
    buttons.pack(pady=20)
    tk.Button(buttons, text="保存并启动", width=16, command=save).pack(side="left", padx=8)
    tk.Button(buttons, text="取消", width=10, command=root.destroy).pack(side="left", padx=8)
    root.mainloop()
    return saved["ok"]


def show_error(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        from tkinter import messagebox

        messagebox.showerror(APP_TITLE, message)
    except Exception:
        pass


def create_database_if_needed() -> None:
    import pymysql

    database_name = os.environ["DATABASE_NAME"].strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", database_name):
        raise RuntimeError("DATABASE_NAME 只能包含字母、数字和下划线")
    connection = pymysql.connect(
        host=os.environ.get("DATABASE_HOST", "127.0.0.1"),
        port=int(os.environ.get("DATABASE_PORT", "3306")),
        user=os.environ.get("DATABASE_USER", "root"),
        password=os.environ.get("DATABASE_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def run_migrations() -> None:
    from alembic.config import Config

    from alembic import command

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(config, "head")


def open_browser_when_ready(host: str, port: int) -> None:
    for _ in range(120):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                webbrowser.open(f"http://{host}:{port}/")
                return
        except OSError:
            time.sleep(0.25)


def bundle_check() -> int:
    required = [
        ROOT / "static" / "vue" / "index.html",
        ROOT / "alembic.ini",
        ROOT / "alembic" / "env.py",
        ROOT / "sql" / "migrations" / "0001_baseline.sql",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        print("BUNDLE_CHECK_FAILED missing=" + ",".join(missing))
        return 1
    import faiss  # noqa: F401
    import fastapi  # noqa: F401
    import pymupdf  # noqa: F401
    import sentence_transformers  # noqa: F401
    import uvicorn  # noqa: F401

    from app.main import app as packaged_app

    if packaged_app is None:
        print("BUNDLE_CHECK_FAILED app_import")
        return 1

    print("BUNDLE_CHECK_OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--check", action="store_true", help="只检查打包完整性")
    parser.add_argument("--port", type=int, default=int(os.getenv("A3_PORT", DEFAULT_PORT)))
    args = parser.parse_args()

    if args.check:
        return bundle_check()

    load_env_file(ROOT / ".env")
    os.environ.setdefault("ENABLE_LEGACY_ROUTES", "false")
    if not required_database_env_present() and not configure_database():
        return 1

    try:
        create_database_if_needed()
        run_migrations()
        import uvicorn

        from app.main import app

        opener = threading.Thread(
            target=open_browser_when_ready,
            args=(DEFAULT_HOST, args.port),
            daemon=True,
        )
        opener.start()
        print(f"{APP_TITLE} 已启动：http://{DEFAULT_HOST}:{args.port}/")
        print("请保持此窗口运行；按 Ctrl+C 可停止服务。")
        uvicorn.run(app, host=DEFAULT_HOST, port=args.port, log_level="info")
        return 0
    except Exception as exc:
        traceback.print_exc()
        show_error(
            "启动失败："
            + str(exc)
            + "\n\n请确认 MySQL 8.x 已启动，配置正确且当前用户拥有建库权限。"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
