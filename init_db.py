import sqlite3
import hashlib
import uuid
from datetime import datetime

from werkzeug.security import generate_password_hash


def hash_password(password):
    # Salted hash (khớp với app.hash_password). Tài khoản cũ dùng SHA-256 vẫn đăng nhập được.
    return generate_password_hash(password)


# Phai trung voi ten file DB ma app.py dang dung (get_db_connection)
DB_PATH = 'users.db'

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("PRAGMA foreign_keys = ON;")

# 1. Xoa bang cu neu da ton tai de cap nhat cau truc moi
c.execute("DROP TABLE IF EXISTS customers")
c.execute("DROP TABLE IF EXISTS order_items")
c.execute("DROP TABLE IF EXISTS orders")
c.execute("DROP TABLE IF EXISTS giao_hang")
c.execute("DROP TABLE IF EXISTS products")
c.execute("DROP TABLE IF EXISTS users")

# 2. Tao lai bang users voi DAY DU cac cot
c.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    phone TEXT,
    password TEXT NOT NULL,
    avatar TEXT,
    dob TEXT,
    address TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    role TEXT DEFAULT 'user'
)
""")

# 3. Chen tai khoan Admin
try:
    c.execute("""
        INSERT INTO users
        (username, email, phone, password, avatar, dob, address, role)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        'admin',
        'admin@gmail.com',
        '0901234567',
        hash_password('admin123'),
        None,
        None,
        '123 Duong Admin, Quan 1, TP.HCM',
        'admin'
    ))
    print("Admin created: admin / admin123")
except sqlite3.IntegrityError:
    print("Admin already exists")

# 4. Tao bang products voi day du cot thong so (co stock, description)
c.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    brand TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER DEFAULT 0,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    image TEXT,
    cpu TEXT,
    display TEXT,
    ram TEXT,
    storage TEXT,
    gpu TEXT,
    battery TEXT,
    camera TEXT,
    chip TEXT,
    sensor TEXT,
    water_resistance TEXT,
    ports TEXT,
    wifi TEXT,
    cooling TEXT,
    capacity TEXT,
    type TEXT,
    cooling_tech TEXT,
    energy_rating TEXT,
    motor TEXT,
    technology TEXT,
    warranty TEXT,
    shelves TEXT,
    power TEXT,
    speed_levels TEXT,
    control_type TEXT,
    oscillation TEXT,
    timer TEXT,
    size TEXT,
    blade_type TEXT,
    filter TEXT,
    zones TEXT,
    burners TEXT,
    grates TEXT,
    safety TEXT,
    ignition TEXT,
    extra_specs TEXT NOT NULL DEFAULT '{}'
)
""")

# 5. Bang customers (tham chieu toi users - hien thi trong so do quan he)
c.execute("""
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_name TEXT,
    email TEXT,
    phone TEXT,
    address TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# 6. Bang dia chi giao hang
c.execute("""
CREATE TABLE IF NOT EXISTS giao_hang (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ten TEXT NOT NULL,
    so_dien_thoai TEXT NOT NULL,
    dia_chi TEXT NOT NULL,
    mac_dinh INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# 7. Bang orders
c.execute("""
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    total_price REAL NOT NULL,
    status TEXT DEFAULT 'pending',
    address TEXT NOT NULL,
    phone TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

# 8. Bang order_items
c.execute("""
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT NOT NULL,
    product_id INTEGER,
    product_name TEXT NOT NULL,
    price REAL NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
)
""")

# Du lieu san pham: (product_id, name, category, brand, price, image,
#   cpu, display, ram, storage, gpu, battery, camera, chip, sensor, water_resistance,
#   ports, wifi, cooling, capacity, type, cooling_tech, energy_rating, motor, technology,
#   warranty, shelves, power, speed_levels, control_type, oscillation, timer, size,
#   blade_type, filter, zones, burners, grates, safety, ignition)
# Du lieu san pham: moi san pham la 1 dict, chi khai bao cot co gia tri.
# Cac cot khong khai bao se nhan None / gia tri mac dinh cua bang.
products = [
    # ---- Phones (dienthoai) ----
    dict(name='iPhone 15 Pro', category='dienthoai', brand='Apple', price=29990000,
         image='iphone15.jpg', cpu='A17 Pro', display='6.1 inch OLED', ram='8GB',
         storage='256GB', battery='3274 mAh', camera='48MP'),
    dict(name='Galaxy S24 Ultra', category='dienthoai', brand='Samsung', price=27990000,
         image='galaxy_s24.jpg', cpu='Snapdragon 8 Gen 3', display='6.8 inch AMOLED',
         ram='12GB', storage='512GB', battery='5000 mAh', camera='200MP'),
    dict(name='Xiaomi 14 Pro', category='dienthoai', brand='Xiaomi', price=18990000,
         image='xiaomi14.jpg', cpu='Snapdragon 8 Gen 3', display='6.73 inch AMOLED',
         ram='12GB', storage='256GB', battery='4880 mAh', camera='50MP'),
    dict(name='OPPO Find X7', category='dienthoai', brand='OPPO', price=16990000,
         image='oppo_findx7.jpg', cpu='Dimensity 9300', display='6.78 inch AMOLED',
         ram='16GB', storage='512GB', battery='5000 mAh', camera='50MP'),

    # ---- Watches (dongho) ----
    dict(name='Apple Watch Series 9', category='dongho', brand='Apple', price=10990000,
         image='apple_watch9.jpg', display='1.9 inch OLED', storage='64GB',
         battery='18 hours', chip='S9 SiP', sensor='ECG + Blood O2', water_resistance='50m'),
    dict(name='Samsung Galaxy Watch 6', category='dongho', brand='Samsung', price=7990000,
         image='galaxy_watch6.jpg', display='1.5 inch AMOLED', storage='16GB',
         battery='40 hours', chip='Exynos W930', sensor='BioActive', water_resistance='5ATM'),
    dict(name='Xiaomi Watch S2', category='dongho', brand='Xiaomi', price=4990000,
         image='xiaomi_watch_s2.jpg', display='1.43 inch AMOLED', storage='4GB',
         battery='12 days', chip='Proprietary', sensor='Heart Rate + SpO2', water_resistance='5ATM'),
    dict(name='Garmin Forerunner 265', category='dongho', brand='Garmin', price=12990000,
         image='garmin_265.jpg', display='1.3 inch AMOLED', storage='8GB',
         battery='13 days', chip='Proprietary', sensor='GPS + Heart Rate', water_resistance='5ATM'),

    # ---- Laptops ----
    dict(name='MacBook Pro 14 M3', category='laptop', brand='Apple', price=45990000,
         image='macbook_pro14.jpg', cpu='Apple M3', display='14 inch Liquid Retina XDR',
         ram='16GB', storage='512GB SSD', gpu='M3 10-core', battery='17 hours'),
    dict(name='Dell XPS 15', category='laptop', brand='Dell', price=35990000,
         image='dell_xps15.jpg', cpu='Intel i7-13700H', display='15.6 inch FHD+',
         ram='16GB DDR5', storage='512GB SSD', gpu='RTX 4050', battery='86 Wh'),
    dict(name='Asus ROG Strix G16', category='laptop', brand='Asus', price=32990000,
         image='asus_rog_g16.jpg', cpu='Intel i7-13650HX', display='16 inch FHD+ 165Hz',
         ram='16GB DDR5', storage='1TB SSD', gpu='RTX 4060', battery='90 Wh'),
    dict(name='HP Pavilion 15', category='laptop', brand='HP', price=18990000,
         image='hp_pavilion15.jpg', cpu='AMD Ryzen 5 7530U', display='15.6 inch FHD',
         ram='8GB DDR4', storage='512GB SSD', gpu='Radeon Graphics', battery='41 Wh'),

    # ---- Desktops (maytinhbanpc) ----
    dict(name='iMac 24 M3', category='maytinhbanpc', brand='Apple', price=38990000,
         image='imac24.jpg', cpu='Apple M3', display='24 inch 4.5K Retina',
         ram='8GB', storage='256GB SSD', gpu='M3 8-core', ports='4x Thunderbolt'),
    dict(name='Dell Inspiron Desktop', category='maytinhbanpc', brand='Dell', price=15990000,
         image='dell_inspiron_desktop.jpg', cpu='Intel i5-12400', ram='8GB DDR4',
         storage='512GB SSD', gpu='Intel UHD 730', ports='USB 3.2 + HDMI', wifi='Wi-Fi 6'),
    dict(name='HP Pavilion Gaming Desktop', category='maytinhbanpc', brand='HP', price=22990000,
         image='hp_gaming_desktop.jpg', cpu='AMD Ryzen 5 5600G', ram='16GB DDR4',
         storage='512GB SSD', gpu='RTX 3060', ports='USB 3.2 + HDMI 2.1', wifi='Wi-Fi 6'),
    dict(name='Asus ROG Desktop', category='maytinhbanpc', brand='Asus', price=42990000,
         image='asus_rog_desktop.jpg', cpu='Intel i7-13700K', ram='32GB DDR5',
         storage='1TB SSD', gpu='RTX 4070', ports='USB 3.2 + DP + HDMI',
         wifi='Wi-Fi 6E', cooling='Liquid Cooling'),

    # ---- Refrigerators (tulanh) ----
    dict(name='Samsung Inverter 360L', category='tulanh', brand='Samsung', price=12990000,
         image='samsung_fridge_360.jpg', capacity='360L', type='Inverter',
         cooling_tech='Multi Air Flow', energy_rating='4.5 stars',
         warranty='12 years compressor', shelves='Tempered Glass'),
    dict(name='LG Inverter 475L', category='tulanh', brand='LG', price=15990000,
         image='lg_fridge_475.jpg', capacity='475L', type='Linear Inverter',
         cooling_tech='DoorCooling+', energy_rating='5 stars',
         warranty='10 years compressor', shelves='Tempered Glass'),
    dict(name='Panasonic Inverter 326L', category='tulanh', brand='Panasonic', price=10990000,
         image='panasonic_fridge_326.jpg', capacity='326L', type='Inverter',
         cooling_tech='Prime Fresh+', energy_rating='4 stars',
         warranty='12 years compressor', shelves='Tempered Glass'),
    dict(name='Toshiba Inverter 409L', category='tulanh', brand='Toshiba', price=13990000,
         image='toshiba_fridge_409.jpg', capacity='409L', type='Origin Inverter',
         cooling_tech='Hybrid Bio', energy_rating='4.5 stars',
         warranty='12 years compressor', shelves='Tempered Glass'),

    # ---- Fans (quat) ----
    dict(name='Panasonic Tower Fan', category='quat', brand='Panasonic', price=2490000,
         image='panasonic_tower_fan.jpg', type='Tower Fan', power='45W',
         speed_levels='3 levels', control_type='Remote', oscillation='80',
         timer='7.5 hours'),
    dict(name='Senko Stand Fan', category='quat', brand='Senko', price=890000,
         image='senko_stand_fan.jpg', type='Stand Fan', power='65W',
         speed_levels='3 levels', oscillation='90', size='16 inch', blade_type='Metal'),
    dict(name='Dyson Pure Cool', category='quat', brand='Dyson', price=15990000,
         image='dyson_pure_cool.jpg', type='Air Purifier Fan', power='40W',
         control_type='Remote + App', oscillation='350', filter='HEPA + Carbon'),
    dict(name='Mitsubishi Ceiling Fan', category='quat', brand='Mitsubishi', price=3990000,
         image='mitsubishi_ceiling_fan.jpg', type='Ceiling Fan', power='75W',
         speed_levels='6 levels', control_type='Remote', size='56 inch'),

    # ---- Washing Machines (maygiatsay) ----
    dict(name='Samsung Inverter 9kg', category='maygiatsay', brand='Samsung', price=8990000,
         image='samsung_washer_9kg.jpg', capacity='9kg', type='Front Load',
         energy_rating='5 stars', motor='Digital Inverter', technology='Eco Bubble',
         warranty='11 years motor'),
    dict(name='LG TurboWash 10kg', category='maygiatsay', brand='LG', price=11990000,
         image='lg_turbowash_10kg.jpg', capacity='10kg', type='Front Load',
         energy_rating='5 stars', motor='AI DD', technology='TurboWash 360',
         warranty='10 years motor'),
    dict(name='Electrolux UltimateCare 8kg', category='maygiatsay', brand='Electrolux',
         price=9990000, image='electrolux_8kg.jpg', capacity='8kg', type='Front Load',
         energy_rating='4.5 stars', motor='Inverter', technology='UltraMix + Vapour',
         warranty='10 years motor'),
    dict(name='Panasonic Inverter 9.5kg', category='maygiatsay', brand='Panasonic',
         price=10490000, image='panasonic_washer_95kg.jpg', capacity='9.5kg',
         type='Top Load', energy_rating='4 stars', motor='Inverter',
         technology='Econavi + StainMaster', warranty='12 years motor'),

    # ---- Stoves (beptu) ----
    dict(name='Sunhouse Induction Cooker', category='beptu', brand='Sunhouse',
         price=1290000, image='sunhouse_induction.jpg', type='Induction',
         power='2000W', speed_levels='7 power levels', control_type='Touch',
         timer='Yes', zones='1 zone'),
    dict(name='Electrolux Built-in Hob', category='beptu', brand='Electrolux',
         price=8990000, image='electrolux_hob.jpg', type='Induction', power='7400W',
         control_type='Touch', timer='Yes', zones='4 zones', safety='Child Lock'),
    dict(name='Bosch Gas Stove', category='beptu', brand='Bosch', price=12990000,
         image='bosch_gas_stove.jpg', type='Gas', power='10.5 kW',
         burners='4 burners', grates='Cast Iron', safety='Flame Failure',
         ignition='Auto'),
    dict(name='Kangaroo Infrared Cooker', category='beptu', brand='Kangaroo',
         price=990000, image='kangaroo_infrared.jpg', type='Infrared', power='2200W',
         speed_levels='8 power levels', control_type='Touch', timer='Yes', zones='1 zone'),
]

# Sinh product_id tu dong cho tung san pham va insert theo dict
for item in products:
    data = dict(item)
    data['product_id'] = str(uuid.uuid4())[:8].upper()
    data.setdefault('stock', 20)
    data.setdefault('description', 'San pham chinh hang, bao hanh day du')

    cols = ', '.join(data.keys())
    placeholders = ', '.join(['?'] * len(data))
    try:
        c.execute(
            f"INSERT INTO products ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        print(f"[OK] Added: {data['name']}")
    except sqlite3.IntegrityError as e:
        print(f"[ERR] Error adding {data['name']}: {e}")

conn.commit()

# Add default shipping address for admin
try:
    admin_id = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    c.execute("""
        INSERT INTO giao_hang (user_id, ten, so_dien_thoai, dia_chi, mac_dinh)
        VALUES (?, ?, ?, ?, 1)
    """, (admin_id, 'Quan Tri Vien', '0901234567', '123 Duong Admin, Quan 1, TP.HCM'))
    print("[OK] Dia chi giao hang mau da them cho admin")
except Exception:
    pass

# Them ban ghi customers cho admin (de so do quan he co du lieu)
try:
    admin_id = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    c.execute("""
        INSERT INTO customers (user_id, full_name, email, phone, address)
        VALUES (?, ?, ?, ?, ?)
    """, (admin_id, 'Quan Tri Vien', 'admin@gmail.com', '0901234567', '123 Duong Admin, Quan 1, TP.HCM'))
    print("[OK] Ban ghi customers da them cho admin")
except Exception:
    pass

# Create sample order
try:
    admin_id = c.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    sample_order_id = "ORD-" + str(uuid.uuid4())[:8].upper()

    c.execute("""
        INSERT INTO orders
        (order_id, user_id, total_price, status, address, phone)
        VALUES (?, ?, ?, 'pending', ?, ?)
    """, (
        sample_order_id,
        admin_id,
        48980000.0,
        '123 Duong Admin, Quan 1, TP.HCM',
        '0901234567'
    ))

    iphone_id = c.execute("SELECT id FROM products WHERE name LIKE '%iPhone 15 Pro%'").fetchone()[0]
    laptop_id = c.execute("SELECT id FROM products WHERE name LIKE '%HP Pavilion 15%'").fetchone()[0]

    c.execute("""
        INSERT INTO order_items
        (order_id, product_id, product_name, price, quantity)
        VALUES (?, ?, ?, ?, ?)
    """, (sample_order_id, iphone_id, 'iPhone 15 Pro', 29990000, 1))

    c.execute("""
        INSERT INTO order_items
        (order_id, product_id, product_name, price, quantity)
        VALUES (?, ?, ?, ?, ?)
    """, (sample_order_id, laptop_id, 'HP Pavilion 15', 18990000, 1))

    print("[OK] Don hang mau da them thanh cong (iPhone 15 Pro + HP Pavilion 15)")
except Exception as e:
    print("[ERR] Loi khi them don hang mau:", e)

conn.commit()
conn.close()

print("\n" + "=" * 60)
print("DATABASE INITIALIZED SUCCESSFULLY!")
print("=" * 60)
print("\nDatabase Structure:")
print("   - users          (admin + khach hang)")
print("   - customers      (tham chieu users)")
print("   - products       (co stock, description)")
print("   - orders         (tham chieu users)")
print("   - order_items    (tham chieu orders + products)")
print("   - giao_hang      (tham chieu users)")
print("\nAdmin Account:")
print("   Username: admin")
print("   Password: admin123")
print("\nProducts Added: 32 items")
print("\n" + "=" * 60)
print("Ready to run Flask app!")
print("=" * 60)