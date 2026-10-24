"""Show an understandable startup failure even without a console."""
import ctypes
import traceback
from pathlib import Path

try:
    from app import main
    main()
except Exception:
    report=Path(__file__).resolve().parents[1]/'启动错误.txt'
    report.write_text(traceback.format_exc(),encoding='utf-8-sig')
    ctypes.windll.user32.MessageBoxW(None,'工具启动失败。请将工具目录中的“启动错误.txt”交给 AI 排查。','明日方舟数据研究工具',0x10)
