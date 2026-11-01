import os
import sqlite3


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'users.db')


def main():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        columns = {
            row[1] for row in conn.execute('PRAGMA table_info(products)').fetchall()
        }
        if not columns:
            raise RuntimeError('Không tìm thấy bảng products trong users.db.')
        if 'extra_specs' not in columns:
            conn.execute(
                "ALTER TABLE products ADD COLUMN extra_specs TEXT NOT NULL DEFAULT '{}'"
            )
            conn.commit()
            print('Added products.extra_specs; existing product rows were preserved.')
        else:
            print('products.extra_specs already exists; no migration needed.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
