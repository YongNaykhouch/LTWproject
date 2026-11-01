"""Quét toàn bộ template tìm lỗi mojibake (chuỗi UTF-8 bị đọc nhầm bảng mã Windows-1252/CP1252).

Cách dùng:  python check_encoding.py
"""
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Các ký tự "đánh dấu" của lỗi CP1252: khi UTF-8 bị giải mã sai,
# các byte dấu tiếng Việt thường biến thành những ký tự này.
MARKERS = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›¢£§"

# Ký tự Việt hợp lệ đứng ngay trước marker (dấu hiệu chắc chắn)
VN = "àáảãạăâđêôơưÀÁẢÃẠĂÂĐÊÔƠƯèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ"

PATTERN = re.compile(rf"[{VN}{''.join(MARKERS)}][{''.join(MARKERS)}]")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def scan(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        print(f"[ KHÔNG PHẢI UTF-8 ] {path}")
        return 0
    hits = 0
    for no, line in enumerate(lines, 1):
        if PATTERN.search(line):
            hits += 1
            print(f"{os.path.relpath(path, ROOT)}:{no}: {line.strip()[:140]}")
    return hits


total = 0
for base, _dirs, files in os.walk(ROOT):
    for name in files:
        if name.endswith((".html", ".htm", ".js", ".css")):
            total += scan(os.path.join(base, name))

print(f"\n=> Tổng số dòng nghi lỗi encoding: {total}")
