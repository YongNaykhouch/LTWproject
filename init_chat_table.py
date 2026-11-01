import sqlite3

DB_PATH = 'users.db'

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS chat_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_key TEXT    NOT NULL,              -- mã phiên làm việc của khách
    user_id     INTEGER,                       -- NULL nếu khách chưa đăng nhập
    username    TEXT,                          -- lưu lại tên lúc chat
    role        TEXT    NOT NULL,              -- 'user' = khách hỏi, 'bot' = trả lời
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_key);
CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created_at);
"""


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(CREATE_SQL)
        conn.commit()
        count = conn.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0]
        print(f'OK: bảng chat_messages đã sẵn sàng ({count} tin nhắn hiện có).')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
