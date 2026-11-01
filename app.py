from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import hashlib
import uuid
import os
import secrets
import time
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
from product_extra_specs import (
    EXTRA_SPEC_FIELDS,
    EXTRA_SPEC_ICONS,
    EXTRA_SPEC_LABELS,
    extra_specs_from_form,
    parse_extra_specs,
    serialize_extra_specs,
)

app = Flask(__name__)
# Secret key lấy từ biến môi trường. Nếu không có (máy dev) thì dùng 'static/dev_secret.key'
# - file này được tạo tự động và KHÔNG nên commit lên git.
_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'dev_secret.key')

def _load_secret_key():
    key = os.environ.get('FLASK_SECRET_KEY')
    if key:
        return key
    try:
        if os.path.exists(_SECRET_FILE):
            with open(_SECRET_FILE, 'r', encoding='utf-8') as fh:
                key = fh.read().strip()
                if key:
                    return key
        key = secrets.token_hex(32)
        os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
        with open(_SECRET_FILE, 'w', encoding='utf-8') as fh:
            fh.write(key)
        return key
    except OSError:
        # Không ghi được file -> vẫn tạo key ngẫu nhiên cho phiên chạy này
        return secrets.token_hex(32)

app.secret_key = _load_secret_key()
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Web API REST (CRUD) - xem api.py và API_DOCS.md
from api import api_bp
app.register_blueprint(api_bp)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def redirect_back_or_index():
    referrer = request.referrer
    if referrer and referrer.startswith(request.host_url):
        return redirect(referrer)
    return redirect(url_for('index'))


def hash_password(password):
    """Hash mật khẩu mới: salted (werkzeug scrypt). dB cũ SHA-256 vẫn kiểm tra được."""
    return generate_password_hash(password)


def verify_password(stored_hash, password):
    """Kiểm tra mật khẩu với cả hash mới (salted) và hash SHA-256 cũ."""
    if not stored_hash:
        return False
    # Hash werkzeug có dạng: scrypt:32768:8:1$salt$hash (hoặc pbkdf2:...)
    if '$' in stored_hash:
        try:
            return check_password_hash(stored_hash, password)
        except (ValueError, TypeError):
            return False
    # Hash SHA-256 cũ (64 ký tự hex) -> nâng cấp dần khi người dùng đăng nhập
    return stored_hash == hashlib.sha256(password.encode()).hexdigest()


def is_legacy_hash(stored_hash):
    return bool(stored_hash) and '$' not in stored_hash

# Đường dẫn DB luôn tính theo thư mục chứa app.py.
# Trước đây dùng 'users.db' (đường dẫn tương đối) nên nếu chạy app từ
# thư mục khác (vd. `python FLASK\app.py` ở d:\flask\Website_bh) thì SQLite
# tạo/ mở NHẦM file rỗng ở đó -> lỗi "no such table: products".
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'users.db')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
@app.template_filter('format_currency')
def format_currency(value):
    try:
        return f"{int(value):,} ₫"
    except:
        return "0 ₫"

@app.route('/')
def index():
    conn = get_db_connection()

    # Get all products with detailed specs - select all relevant columns
    all_products = conn.execute("""
        SELECT id, product_id, name, category, brand, price, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
        ORDER BY id DESC
        LIMIT 8
    """).fetchall()

    # Get all products for category sections
    products = conn.execute("""
        SELECT id, product_id, name, category, brand, price, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
        ORDER BY id DESC
    """).fetchall()
    conn.close()

    # Group products by category
    categories = defaultdict(list)
    for product in products:
        categories[product['category']].append(product)

    return render_template(
        'index.html',
        all_products=all_products,
        categories=categories
    )

# Helper function to get product specs based on category
def get_product_specs(product):
    """
    Returns a list of spec dictionaries for display
    Each dict has: {'icon': 'fa-icon-class', 'icon_type': 'cpu/ram/etc', 'value': 'spec value'}
    """
    specs = []
    category = product['category']

    # Phones (dienthoai)
    if category == 'dienthoai':
        if product['cpu']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'cpu', 'value': product['cpu']})
        if product['display']:
            specs.append({'icon': 'fa-desktop', 'icon_type': 'display', 'value': product['display']})
        if product['ram']:
            specs.append({'icon': 'fa-memory', 'icon_type': 'ram', 'value': product['ram']})
        if product['storage']:
            specs.append({'icon': 'fa-hard-drive', 'icon_type': 'storage', 'value': product['storage']})
        if product['camera']:
            specs.append({'icon': 'fa-camera', 'icon_type': 'camera', 'value': product['camera']})
        if product['battery']:
            specs.append({'icon': 'fa-battery-full', 'icon_type': 'battery', 'value': product['battery']})

    # Watches (dongho)
    elif category == 'dongho':
        if product['chip']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'chip', 'value': product['chip']})
        if product['display']:
            specs.append({'icon': 'fa-desktop', 'icon_type': 'display', 'value': product['display']})
        if product['sensor']:
            specs.append({'icon': 'fa-heartbeat', 'icon_type': 'sensor', 'value': product['sensor']})
        if product['battery']:
            specs.append({'icon': 'fa-battery-full', 'icon_type': 'battery', 'value': product['battery']})
        if product['water_resistance']:
            specs.append({'icon': 'fa-droplet', 'icon_type': 'water', 'value': product['water_resistance']})
        if product['storage']:
            specs.append({'icon': 'fa-hard-drive', 'icon_type': 'storage', 'value': product['storage']})

    # Laptops
    elif category == 'laptop':
        if product['cpu']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'cpu', 'value': product['cpu']})
        if product['display']:
            specs.append({'icon': 'fa-desktop', 'icon_type': 'display', 'value': product['display']})
        if product['ram']:
            specs.append({'icon': 'fa-memory', 'icon_type': 'ram', 'value': product['ram']})
        if product['storage']:
            specs.append({'icon': 'fa-hard-drive', 'icon_type': 'storage', 'value': product['storage']})
        if product['gpu']:
            specs.append({'icon': 'fa-display', 'icon_type': 'gpu', 'value': product['gpu']})
        if product['battery']:
            specs.append({'icon': 'fa-battery-full', 'icon_type': 'battery', 'value': product['battery']})

    # Desktops (maytinhbanpc)
    elif category == 'maytinhbanpc':
        if product['cpu']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'cpu', 'value': product['cpu']})
        if product['ram']:
            specs.append({'icon': 'fa-memory', 'icon_type': 'ram', 'value': product['ram']})
        if product['storage']:
            specs.append({'icon': 'fa-hard-drive', 'icon_type': 'storage', 'value': product['storage']})
        if product['gpu']:
            specs.append({'icon': 'fa-display', 'icon_type': 'gpu', 'value': product['gpu']})
        if product['ports']:
            specs.append({'icon': 'fa-plug', 'icon_type': 'ports', 'value': product['ports']})
        if product['wifi']:
            specs.append({'icon': 'fa-wifi', 'icon_type': 'wifi', 'value': product['wifi']})

    # Refrigerators (tulanh)
    elif category == 'tulanh':
        if product['capacity']:
            specs.append({'icon': 'fa-box', 'icon_type': 'capacity', 'value': product['capacity']})
        if product['type']:
            specs.append({'icon': 'fa-bolt', 'icon_type': 'type', 'value': product['type']})
        if product['cooling_tech']:
            specs.append({'icon': 'fa-snowflake', 'icon_type': 'cooling', 'value': product['cooling_tech']})
        if product['energy_rating']:
            specs.append({'icon': 'fa-star', 'icon_type': 'energy', 'value': product['energy_rating']})
        if product['warranty']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'warranty', 'value': product['warranty']})
        if product['shelves']:
            specs.append({'icon': 'fa-table-cells', 'icon_type': 'shelves', 'value': product['shelves']})

    # Fans (quat)
    elif category == 'quat':
        if product['type']:
            specs.append({'icon': 'fa-fan', 'icon_type': 'type', 'value': product['type']})
        if product['power']:
            specs.append({'icon': 'fa-bolt', 'icon_type': 'power', 'value': product['power']})
        if product['speed_levels']:
            specs.append({'icon': 'fa-gauge-high', 'icon_type': 'speed', 'value': product['speed_levels']})
        if product['control_type']:
            specs.append({'icon': 'fa-mobile', 'icon_type': 'control', 'value': product['control_type']})
        if product['oscillation']:
            specs.append({'icon': 'fa-rotate', 'icon_type': 'oscillation', 'value': product['oscillation']})
        if product['timer']:
            specs.append({'icon': 'fa-clock', 'icon_type': 'timer', 'value': product['timer']})

    # Washing Machines (maygiatsay)
    elif category == 'maygiatsay':
        if product['capacity']:
            specs.append({'icon': 'fa-box', 'icon_type': 'capacity', 'value': product['capacity']})
        if product['type']:
            specs.append({'icon': 'fa-door-open', 'icon_type': 'type', 'value': product['type']})
        if product['motor']:
            specs.append({'icon': 'fa-gear', 'icon_type': 'motor', 'value': product['motor']})
        if product['technology']:
            specs.append({'icon': 'fa-sparkles', 'icon_type': 'technology', 'value': product['technology']})
        if product['energy_rating']:
            specs.append({'icon': 'fa-star', 'icon_type': 'energy', 'value': product['energy_rating']})
        if product['warranty']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'warranty', 'value': product['warranty']})

    # Stoves (beptu)
    elif category == 'beptu':
        if product['type']:
            specs.append({'icon': 'fa-fire', 'icon_type': 'type', 'value': product['type']})
        if product['power']:
            specs.append({'icon': 'fa-bolt', 'icon_type': 'power', 'value': product['power']})
        if product['zones']:
            specs.append({'icon': 'fa-circle-dot', 'icon_type': 'zones', 'value': product['zones']})
        if product['burners']:
            specs.append({'icon': 'fa-fire-burner', 'icon_type': 'burners', 'value': product['burners']})
        if product['control_type']:
            specs.append({'icon': 'fa-hand-pointer', 'icon_type': 'control', 'value': product['control_type']})
        if product['safety']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'safety', 'value': product['safety']})

    # Headphones (tainghe)
    elif category == 'tainghe':
        if product['wifi']:
            specs.append({'icon': 'fa-bluetooth-b', 'icon_type': 'wifi', 'value': product['wifi']})
        if product['battery']:
            specs.append({'icon': 'fa-battery-full', 'icon_type': 'battery', 'value': product['battery']})
        if product['chip']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'chip', 'value': product['chip']})
        if product['technology']:
            specs.append({'icon': 'fa-sparkles', 'icon_type': 'technology', 'value': product['technology']})
        if product['water_resistance']:
            specs.append({'icon': 'fa-droplet', 'icon_type': 'water', 'value': product['water_resistance']})
        if product['warranty']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'warranty', 'value': product['warranty']})

    # Cameras (mayanh)
    elif category == 'mayanh':
        if product['camera']:
            specs.append({'icon': 'fa-camera', 'icon_type': 'camera', 'value': product['camera']})
        if product['chip']:
            specs.append({'icon': 'fa-microchip', 'icon_type': 'chip', 'value': product['chip']})
        if product['display']:
            specs.append({'icon': 'fa-desktop', 'icon_type': 'display', 'value': product['display']})
        if product['storage']:
            specs.append({'icon': 'fa-hard-drive', 'icon_type': 'storage', 'value': product['storage']})
        if product['battery']:
            specs.append({'icon': 'fa-battery-full', 'icon_type': 'battery', 'value': product['battery']})
        if product['warranty']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'warranty', 'value': product['warranty']})

    # Air conditioners (dieuhoa)
    elif category == 'dieuhoa':
        if product['capacity']:
            specs.append({'icon': 'fa-box', 'icon_type': 'capacity', 'value': product['capacity']})
        if product['type']:
            specs.append({'icon': 'fa-wind', 'icon_type': 'type', 'value': product['type']})
        if product['cooling_tech']:
            specs.append({'icon': 'fa-snowflake', 'icon_type': 'cooling', 'value': product['cooling_tech']})
        if product['energy_rating']:
            specs.append({'icon': 'fa-star', 'icon_type': 'energy', 'value': product['energy_rating']})
        if product['power']:
            specs.append({'icon': 'fa-bolt', 'icon_type': 'power', 'value': product['power']})
        if product['warranty']:
            specs.append({'icon': 'fa-shield', 'icon_type': 'warranty', 'value': product['warranty']})

    # Sản phẩm thuộc danh mục chưa có bộ thông số riêng: hiện những gì có
    else:
        fallback = [
            ('cpu', 'fa-microchip'), ('display', 'fa-desktop'), ('ram', 'fa-memory'),
            ('storage', 'fa-hard-drive'), ('gpu', 'fa-display'), ('battery', 'fa-battery-full'),
            ('camera', 'fa-camera'), ('capacity', 'fa-box'), ('power', 'fa-bolt'),
            ('warranty', 'fa-shield'),
        ]
        for key, icon in fallback:
            if product.get(key):
                specs.append({'icon': icon, 'icon_type': key, 'value': product[key]})

    available_keys = product.keys()
    extra_specs = parse_extra_specs(
        product['extra_specs'] if 'extra_specs' in available_keys else None
    )
    for key, value in extra_specs.items():
        specs.append({
            'icon': EXTRA_SPEC_ICONS.get(key, 'fa-circle-info'),
            'icon_type': key,
            'value': value,
        })

    return specs

# Register the helper function as a Jinja2 filter
@app.template_filter('get_specs')
def get_specs_filter(product):
    return get_product_specs(dict(product))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip().lower()
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        dob = request.form.get('dob')
        address = request.form.get('address')
        avatar = request.files.get('avatar')

        # ❌ Reserved username
        if username.lower() == 'admin':
            flash('Username "admin" is reserved.', 'error')
            return render_template('register.html')

        # ❌ Gmail only
        if not email.endswith('@gmail.com'):
            flash('Chỉ cho phép đăng ký bằng Gmail!', 'error')
            return render_template('register.html')

        # ❌ Password mismatch
        if password != confirm_password:
            flash('Mật khẩu xác nhận không khớp!', 'error')
            return render_template('register.html')

        # 🔐 Hash password
        hashed_password = hash_password(password)

        # 🖼 Avatar upload
        avatar_filename = None
        if avatar and allowed_file(avatar.filename):
            safe_name = secure_filename(avatar.filename)
            avatar_filename = f"{username}_{safe_name}"
            avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

        conn = None
        try:
            conn = get_db_connection()
            conn.execute("""
                INSERT INTO users
                (username, email, phone, password, avatar, dob, address, role)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'user')
            """, (
                username,
                email,
                phone,
                hashed_password,
                avatar_filename,
                dob,
                address
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            flash('Tên đăng nhập hoặc Email đã tồn tại!', 'error')
            return render_template('register.html')
        except sqlite3.OperationalError:
            app.logger.exception('Database error during registration')
            flash('Cơ sở dữ liệu đang bận. Vui lòng thử lại sau!', 'error')
            return render_template('register.html')
        finally:
            if conn is not None:
                conn.close()

        flash('🎉 Đăng ký thành công! Vui lòng đăng nhập.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_or_email = request.form['username'].strip().lower()
        password = request.form['password']

        conn = get_db_connection()
        # KHÔNG so sánh password trong SQL: lấy user theo tên/email rồi kiểm tra hash trong Python
        user = conn.execute("""
            SELECT * FROM users
            WHERE username = ? OR email = ?
        """, (username_or_email, username_or_email)).fetchone()

        if user and verify_password(user['password'], password):
            # Nâng cấp dần tài khoản còn dùng hash SHA-256 cũ sang hash có salt
            if is_legacy_hash(user['password']):
                try:
                    conn.execute('UPDATE users SET password = ? WHERE id = ?',
                                 (hash_password(password), user['id']))
                    conn.commit()
                except sqlite3.Error as exc:
                    app.logger.warning('Không nâng cấp được hash mật khẩu: %s', exc)
            conn.close()

            session.clear()
            session['user_id'] = user['id']
            session['customer_id'] = user['id']   # for cart JS
            session['username'] = user['username']
            session['role'] = user['role']

            flash('Đăng nhập thành công!', 'success')
            return redirect(url_for('index'))

        conn.close()
        flash('Sai tài khoản hoặc mật khẩu!', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Đã đăng xuất.', 'info')
    return redirect(url_for('login'))

@app.route('/products')
def products():
    """Customer product listing page - requires login"""
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để xem danh sách sản phẩm!', 'warning')
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        flash('Admin nên sử dụng trang quản trị.', 'info')
        return redirect(url_for('admin_products'))

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 12
    search = request.args.get('search', '').strip()

    conn = get_db_connection()

    base_query = """
        SELECT id, product_id, name, category, brand, price, stock, description, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
    """

    if search:
        where_clause = "WHERE name LIKE ? OR brand LIKE ? OR category LIKE ?"
        params = (f'%{search}%', f'%{search}%', f'%{search}%')
        count_query = "SELECT COUNT(*) FROM products " + where_clause
        total = conn.execute(count_query, params).fetchone()[0]
        query = base_query + where_clause + " ORDER BY id DESC LIMIT ? OFFSET ?"
        params += (per_page, (page - 1) * per_page)
        products = conn.execute(query, params).fetchall()
    else:
        total = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        query = base_query + " ORDER BY id DESC LIMIT ? OFFSET ?"
        products = conn.execute(query, (per_page, (page - 1) * per_page)).fetchall()

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('products.html',
                           products=products,
                           page=page,
                           total_pages=total_pages,
                           search=search,
                           get_specs=get_product_specs)  # Pass helper directly if needed in template


@app.route('/admin_dashboard')
def admin_dashboard():
    """Admin main dashboard"""
    if session.get('role') != 'admin':
        flash('Chỉ admin mới có quyền truy cập!', 'danger')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Bảng users mặc định role = 'user' (không phải 'customer')
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'").fetchone()[0]
    total_admins = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
    processing_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'processing'").fetchone()[0]
    completed_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'").fetchone()[0]

    revenue_result = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'").fetchone()
    total_revenue = revenue_result[0]

    # ===== DOANH THU ĐÃ BÁN ĐƯỢC (mọi đơn trừ đơn hủy) =====
    sold_stats = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END), 0) AS sold,
            COALESCE(SUM(CASE WHEN status = 'completed' THEN total_price ELSE 0 END), 0) AS realized,
            COUNT(CASE WHEN status != 'cancelled' THEN 1 END) AS sold_orders,
            COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelled_orders
        FROM orders
    """).fetchone()

    # So sánh với tháng trước để biết tăng/giảm
    today = datetime.now()
    month_start = today.replace(day=1).strftime('%Y-%m-%d')
    prev_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1).strftime('%Y-%m-%d')

    this_month = conn.execute("""
        SELECT COALESCE(SUM(total_price), 0) FROM orders
        WHERE status != 'cancelled' AND DATE(created_at) >= ?
    """, (month_start,)).fetchone()[0]
    prev_month = conn.execute("""
        SELECT COALESCE(SUM(total_price), 0) FROM orders
        WHERE status != 'cancelled' AND DATE(created_at) >= ? AND DATE(created_at) < ?
    """, (prev_start, month_start)).fetchone()[0]

    if prev_month > 0:
        growth_percent = round((this_month - prev_month) / prev_month * 100, 1)
    else:
        growth_percent = None  # chưa có dữ liệu tháng trước

    # Recent users
    recent_users = conn.execute("""
        SELECT id, username, email, role
        FROM users
        ORDER BY id DESC LIMIT 10
    """).fetchall()

    # Recent orders
    recent_orders = conn.execute("""
        SELECT o.id,  o.total_price, o.status, o.created_at, u.username
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.id DESC LIMIT 10
    """).fetchall()

    conn.close()

    return render_template('admin_dashboard.html',
                           page='dashboard',
                           total_users=total_users,
                           total_admins=total_admins,
                           total_products=total_products,
                           pending_orders=pending_orders,
                           processing_orders=processing_orders,
                           completed_orders=completed_orders,
                           total_revenue=total_revenue,
                           sold_revenue=sold_stats['sold'],
                           realized_revenue=sold_stats['realized'],
                           sold_orders=sold_stats['sold_orders'],
                           cancelled_orders=sold_stats['cancelled_orders'],
                           this_month_revenue=this_month,
                           prev_month_revenue=prev_month,
                           growth_percent=growth_percent,
                           recent_users=recent_users,
                           recent_orders=recent_orders)


@app.route('/admin/products')
def admin_products():
    """Admin product management page"""
    if session.get('role') != 'admin':
        flash('Chỉ admin mới có quyền truy cập!', 'danger')
        return redirect(url_for('index'))

    # Search & Pagination
    # Hiển thị TẤT CẢ sản phẩm trên một trang (không giới hạn 15 như trước)
    page = 1
    per_page = 100000
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()

    conn = get_db_connection()

    where_conditions = []
    params = []

    if search:
        where_conditions.append("(name LIKE ? OR brand LIKE ? OR product_id LIKE ?)")
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])

    if category_filter:
        where_conditions.append("category = ?")
        params.append(category_filter)

    where_clause = " AND ".join(where_conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    # Count total
    count_query = f"SELECT COUNT(*) FROM products {where_clause}"
    total = conn.execute(count_query, params).fetchone()[0]

    # Fetch products
    query = f"""
        SELECT id, product_id, name, category, brand, price, stock, description, image, created_at
        FROM products
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    params.extend([per_page, (page - 1) * per_page])
    products = conn.execute(query, params).fetchall()

    # Get categories for filter dropdown
    categories = conn.execute("SELECT DISTINCT category FROM products ORDER BY category").fetchall()
    categories = [row['category'] for row in categories]

    # Stats for sidebar/cards
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role != 'admin'").fetchone()[0]
    pending_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'").fetchone()[0]

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('admin_dashboard.html',
                           page='products',
                           products=products,
                           total_products=total,
                           page_num=page,
                           total_pages=total_pages,
                           search=search,
                           category_filter=category_filter,
                           categories=categories,
                           total_users=total_users,
                           pending_orders=pending_orders,
                           total_revenue=total_revenue)

@app.route('/admin/add_product')
def admin_add_product():
    """Main menu: Show category selection buttons"""
    if session.get('role') != 'admin':
        flash('Admin access only!', 'error')
        return redirect(url_for('index'))

    return render_template('add_product.html')  # The page with big category buttons


@app.route('/admin/add_product/<category>', methods=['GET', 'POST'])
def admin_add_product_category(category):
    """Add product for a specific category with tailored fields"""
    if session.get('role') != 'admin':
        flash('Admin access only!', 'error')
        return redirect(url_for('index'))

    # Validate category (dùng chung VALID_CATEGORIES để không lệch với trang danh mục)
    valid_categories = set(VALID_CATEGORIES.keys())
    if category not in valid_categories:
        flash('Danh mục không hợp lệ!', 'error')
        return redirect(url_for('admin_add_product'))

    # Human-readable names and icons for template
    category_info = {
        'dienthoai': ('Điện Thoại', 'fa-mobile-alt'),
        'dongho': ('Đồng Hồ Thông Minh', 'fa-watch'),
        'laptop': ('Laptop', 'fa-laptop'),
        'maytinhbanpc': ('Máy Tính Bàn / PC', 'fa-desktop'),
        'tulanh': ('Tủ Lạnh', 'fa-snowflake'),
        'quat': ('Quạt', 'fa-fan'),
        'maygiatsay': ('Máy Giặt & Sấy', 'fa-tshirt'),
        'beptu': ('Bếp Từ', 'fa-fire-burner'),
        'tainghe': ('Tai Nghe', 'fa-headphones'),
        'mayanh': ('Máy Ảnh', 'fa-camera'),
        'dieuhoa': ('Điều Hòa', 'fa-wind'),
    }
    category_name, icon_class = category_info[category]

    if request.method == 'POST':
        # Common fields
        name = request.form.get('name')
        brand = request.form.get('brand')
        price_str = request.form.get('price')
        stock_str = request.form.get('stock')
        description = request.form.get('description')

        # Validation
        if not name or not price_str:
            flash('Tên sản phẩm và giá là bắt buộc!', 'error')
            return redirect(request.url)

        try:
            price = float(price_str)
            if price < 0:
                raise ValueError
        except ValueError:
            flash('Giá phải là số dương hợp lệ!', 'error')
            return redirect(request.url)

        # Stock (số lượng) - mặc định 0 nếu bỏ trống
        try:
            stock = int(stock_str) if stock_str else 0
            if stock < 0:
                stock = 0
        except (TypeError, ValueError):
            stock = 0

        # Image upload
        if 'image' not in request.files:
            flash('Vui lòng chọn hình ảnh!', 'error')
            return redirect(request.url)

        file = request.files['image']
        if file.filename == '':
            flash('Chưa chọn file ảnh!', 'error')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('Định dạng ảnh không hợp lệ! Chỉ chấp nhận: PNG, JPG, JPEG, GIF.', 'error')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(filepath)

        # Generate unique product_id (visible code)
        product_id = str(uuid.uuid4())[:8].upper()

        # Category-specific fields (only get if submitted)
        spec_fields = [
            'cpu', 'display', 'ram', 'storage', 'gpu', 'battery', 'camera',
            'chip', 'sensor', 'water_resistance',
            'ports', 'wifi', 'cooling',
            'capacity', 'type', 'cooling_tech', 'energy_rating', 'motor',
            'technology', 'warranty', 'shelves',
            'power', 'speed_levels', 'control_type', 'oscillation', 'timer',
            'size', 'blade_type', 'filter',
            'zones', 'burners', 'grates', 'safety', 'ignition'
        ]

        specs = {field: request.form.get(field) or None for field in spec_fields}
        extra_specs = serialize_extra_specs(
            extra_specs_from_form(request.form, category), category
        )

        try:
            conn = get_db_connection()

            # Full INSERT with all possible columns
            conn.execute('''
                INSERT INTO products (
                    product_id, name, category, brand, price, stock, description, image,
                    cpu, display, ram, storage, gpu, battery, camera,
                    chip, sensor, water_resistance,
                    ports, wifi, cooling,
                    capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
                    power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
                    zones, burners, grates, safety, ignition, extra_specs
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )

            ''', (
                product_id, name, category, brand, price, stock, description, unique_filename,
                specs['cpu'], specs['display'], specs['ram'], specs['storage'], specs['gpu'], specs['battery'], specs['camera'],
                specs['chip'], specs['sensor'], specs['water_resistance'],
                specs['ports'], specs['wifi'], specs['cooling'],
                specs['capacity'], specs['type'], specs['cooling_tech'], specs['energy_rating'], specs['motor'],
                specs['technology'], specs['warranty'], specs['shelves'],
                specs['power'], specs['speed_levels'], specs['control_type'], specs['oscillation'], specs['timer'],
                specs['size'], specs['blade_type'], specs['filter'],
                specs['zones'], specs['burners'], specs['grates'], specs['safety'], specs['ignition'],
                extra_specs
            ))

            conn.commit()
            conn.close()

            flash(f'Thêm sản phẩm "{name}" thành công!', 'success')
            return redirect(url_for('admin_products'))

        except Exception as e:
            # Log error if needed: print(e)
            flash('Đã xảy ra lỗi khi thêm sản phẩm. Vui lòng thử lại.', 'error')
            if os.path.exists(filepath):
                os.remove(filepath)
            return redirect(request.url)

    # GET: Show the form
    return render_template('add_product_form.html',
                           category=category,
                           category_name=category_name,
                           icon=icon_class,
                           extra_spec_fields=EXTRA_SPEC_FIELDS.get(category, []))

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
def admin_edit_product(product_id):
    if session.get('role') != 'admin':
        flash('Admin access only!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Fetch product using dictionary access
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()

    if product is None:
        flash('Sản phẩm không tồn tại!', 'error')
        conn.close()
        return redirect(url_for('admin_products'))

    # URL quay về form khi validate thất bại.
    # KHÔNG dùng request.url vì route nhận <int:product_id> nhưng product['id'] là
    # khoá chính (int) - dùng url_for cho chắc chắn đúng và không bị 404.
    form_url = url_for('admin_edit_product', product_id=product['id'])

    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        brand = request.form.get('brand')
        price_str = request.form.get('price')
        stock_str = request.form.get('stock')
        description = request.form.get('description')

        if not all([name, category, brand, price_str]):
            flash('Vui lòng điền đầy đủ thông tin!', 'error')
            conn.close()
            return redirect(form_url)

        # Danh mục phải nằm trong danh sách chuẩn (tránh lưu mã lạ làm mất thông số)
        if category not in VALID_CATEGORIES:
            flash('Danh mục không hợp lệ! Vui lòng chọn lại từ danh sách.', 'error')
            conn.close()
            return redirect(form_url)

        try:
            price = float(price_str)
            if price < 0:
                raise ValueError
        except ValueError:
            flash('Giá phải là số dương hợp lệ!', 'error')
            conn.close()
            return redirect(form_url)

        # Stock (số lượng) - mặc định 0 nếu bỏ trống
        try:
            stock = int(stock_str) if stock_str else 0
            if stock < 0:
                stock = 0
        except (TypeError, ValueError):
            stock = 0

        # Handle image update (optional)
        image_filename = product['image']  # ← Fixed: use ['image']
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                if not allowed_file(file.filename):
                    flash('Định dạng file không hợp lệ! Chỉ chấp nhận PNG, JPG, JPEG, GIF.', 'error')
                    conn.close()
                    return redirect(form_url)

                # Delete old image
                if image_filename:
                    old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)

                # Save new image
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(filepath)
                image_filename = unique_filename

        # Update database
        conn.execute('''
            UPDATE products
            SET name = ?, category = ?, brand = ?, price = ?, stock = ?, description = ?, image = ?,
                extra_specs = ?
            WHERE id = ?
        ''', (
            name, category, brand, price, stock, description, image_filename,
            serialize_extra_specs(
                extra_specs_from_form(request.form, category), category
            ),
            product['id'],
        ))
        conn.commit()
        conn.close()

        flash('Cập nhật sản phẩm thành công!', 'success')
        return redirect(url_for('admin_products'))

    # GET request: show form
    conn.close()
    extra_specs = parse_extra_specs(product['extra_specs'])
    return render_template('edit_product.html',
                           product=product,
                           categories=VALID_CATEGORIES,
                           extra_spec_groups=[
                               {'category': key, 'fields': fields}
                               for key, fields in EXTRA_SPEC_FIELDS.items()
                           ],
                           extra_specs=extra_specs)

@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
def admin_delete_product(product_id):
    if session.get('role') != 'admin':
        flash('Admin access only!', 'error')
        return redirect(url_for('index'))

    # 1. Lấy image
    with get_db_connection() as conn:
        product = conn.execute(
            'SELECT image FROM products WHERE id = ?',
            (product_id,)
        ).fetchone()

    if not product:
        flash('Sản phẩm không tồn tại!', 'error')
        return redirect(url_for('admin_products'))

    image_filename = product['image']

    # 2. Xóa file ảnh
    if image_filename:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        if os.path.exists(filepath):
            os.remove(filepath)

    # 3. Xóa order_items trước, rồi mới xóa product
    # LƯU Ý: `with get_db_connection() as conn` chỉ đóng connection, KHÔNG tự commit.
    # Thiếu conn.commit() thì lệnh DELETE bị rollback khi đóng -> sản phẩm không bị xóa.
    conn = get_db_connection()
    try:
        conn.execute(
            'DELETE FROM order_items WHERE product_id = ?',
            (product_id,)
        )
        conn.execute(
            'DELETE FROM products WHERE id = ?',
            (product_id,)
        )
        conn.commit()
    finally:
        conn.close()

    flash('Xóa sản phẩm thành công!', 'success')
    return redirect(url_for('admin_products'))




@app.template_filter('strftime')
def _jinja2_filter_strftime(date_str, fmt):
    if not date_str:
        return ""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        return date.strftime(fmt)
    except:
        return date_str  # nếu lỗi thì trả về nguyên bản




@app.route('/admin/orders')
def admin_orders():
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Lấy tham số filter từ URL: ?status=pending&q=...
    status_filter = request.args.get('status')  # None hoặc 'pending', 'processing',...
    keyword = request.args.get('q', '').strip()

    # ================== THỐNG KÊ SỐ LƯỢNG THEO TRẠNG THÁI ==================
    counts = {
        'all': conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        'pending': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
        'processing': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'processing'").fetchone()[0],
        'shipped': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'shipped'").fetchone()[0],
        'completed': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'").fetchone()[0],
        'cancelled': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'").fetchone()[0],
    }

    # ================== LẤY DANH SÁCH ĐƠN HÀNG (lọc trạng thái + tìm kiếm) ==================
    where_conditions = []
    params = []

    if status_filter in ('pending', 'processing', 'shipped', 'completed', 'cancelled'):
        where_conditions.append("o.status = ?")
        params.append(status_filter)

    if keyword:
        where_conditions.append(
            "(o.order_id LIKE ? OR u.username LIKE ? OR o.phone LIKE ? OR u.email LIKE ?)"
        )
        like = f'%{keyword}%'
        params.extend([like, like, like, like])

    where_clause = ("WHERE " + " AND ".join(where_conditions)) if where_conditions else ""

    orders_raw = conn.execute(f"""
        SELECT
            o.id,
            o.order_id,
            o.total_price,
            o.status,
            o.address,
            o.phone,
            o.created_at,
            u.username,
            u.email
        FROM orders o
        JOIN users u ON o.user_id = u.id
        {where_clause}
        ORDER BY o.created_at DESC
    """, params).fetchall()

    # ================== XỬ LÝ created_at → datetime object (giữ nguyên fix tốt của mày) ==================
    orders = []
    for order in orders_raw:
        order_dict = dict(order)
        if order_dict['created_at']:
            created_at_str = order_dict['created_at']
            try:
                if '.' in created_at_str:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Fallback an toàn: bỏ phần microsecond nếu lỗi
                order_dict['created_at'] = datetime.strptime(created_at_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        orders.append(order_dict)

    # ================== THỐNG KÊ KHÁC CHO DASHBOARD ==================
    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'"
    ).fetchone()[0]

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    conn.close()

    return render_template(
        'admin_dashboard.html',  # hoặc 'admin/orders.html' nếu tách riêng
        page='orders',
        orders=orders,
        counts=counts,              # ← Quan trọng: truyền counts để hiển thị badge
        status=status_filter,       # ← Để highlight nút đang chọn
        keyword=keyword,            # ← Giữ từ khoá trên ô tìm kiếm
        pending_count=counts['pending'],
        total_revenue=total_revenue,
        total_users=total_users,
        total_products=total_products
    )


# =====================================================================
# TRANG "ĐƠN HÀNG" (tra cứu / lịch sử) - KHÁC với "Quản Lý Đơn Hàng"
# - /admin/orders      : XỬ LÝ đơn (xác nhận, đổi trạng thái, xóa)
# - /admin/order-list  : TRA CỨU hóa đơn (tìm kiếm, lọc ngày, in/xem chi tiết)
# =====================================================================
@app.route('/admin/order-list')
def admin_order_list():
    """Trang tra cứu hóa đơn (chỉ đọc, không sửa/xóa)."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    # ================== THAM SỐ TÌM KIẾM / SẮP XẾP / PHÂN TRANG ==================
    keyword = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    sort = request.args.get('sort', 'newest').strip()
    page = request.args.get('page', 1, type=int)
    if page < 1:
        page = 1
    per_page = 15

    VALID_STATUS = ['pending', 'processing', 'shipped', 'completed', 'cancelled']
    if status_filter not in VALID_STATUS:
        status_filter = ''

    # Chỉ cho phép các kiểu sắp xếp an toàn (tránh SQL injection)
    SORT_OPTIONS = {
        'newest': 'o.created_at DESC',
        'oldest': 'o.created_at ASC',
        'price_desc': 'o.total_price DESC',
        'price_asc': 'o.total_price ASC',
    }
    order_by = SORT_OPTIONS.get(sort, SORT_OPTIONS['newest'])

    conn = get_db_connection()

    # ================== ĐIỀU KIỆN WHERE ==================
    where_conditions = []
    params = []

    if keyword:
        where_conditions.append(
            "(o.order_id LIKE ? OR u.username LIKE ? OR u.email LIKE ? OR o.phone LIKE ?)"
        )
        like = f'%{keyword}%'
        params.extend([like, like, like, like])

    if status_filter:
        where_conditions.append("o.status = ?")
        params.append(status_filter)

    if date_from:
        where_conditions.append("DATE(o.created_at) >= DATE(?)")
        params.append(date_from)

    if date_to:
        where_conditions.append("DATE(o.created_at) <= DATE(?)")
        params.append(date_to)

    where_clause = ("WHERE " + " AND ".join(where_conditions)) if where_conditions else ""

    # ================== TỔNG SỐ KẾT QUẢ & TỔNG TIỀN ==================
    totals = conn.execute(f"""
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(o.total_price), 0) AS amount
        FROM orders o
        JOIN users u ON o.user_id = u.id
        {where_clause}
    """, params).fetchone()
    total = totals['cnt']
    filtered_amount = totals['amount']

    # ================== LẤY DỮ LIỆU TRANG HIỆN TẠI ==================
    orders_raw = conn.execute(f"""
        SELECT
            o.id,
            o.order_id,
            o.total_price,
            o.status,
            o.address,
            o.phone,
            o.created_at,
            u.username,
            u.email,
            (SELECT COALESCE(SUM(oi.quantity), 0)
             FROM order_items oi
             WHERE oi.order_id = o.order_id) AS item_count
        FROM orders o
        JOIN users u ON o.user_id = u.id
        {where_clause}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()

    # ================== created_at (string) → datetime ==================
    orders = []
    for order in orders_raw:
        order_dict = dict(order)
        if order_dict['created_at']:
            created_at_str = order_dict['created_at']
            try:
                if '.' in created_at_str:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                order_dict['created_at'] = datetime.strptime(created_at_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        orders.append(order_dict)

    # ================== THỐNG KÊ THEO TRẠNG THÁI (toàn hệ thống) ==================
    summary = {
        'total': conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        'pending': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
        'processing': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'processing'").fetchone()[0],
        'shipped': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'shipped'").fetchone()[0],
        'completed': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed'").fetchone()[0],
        'cancelled': conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'").fetchone()[0],
    }

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'"
    ).fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template(
        'admin_dashboard.html',
        page='order_list',
        orders=orders,
        summary=summary,
        keyword=keyword,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        page_num=page,
        per_page=per_page,
        total_pages=total_pages,
        total_results=total,
        filtered_amount=filtered_amount,
        pending_count=summary['pending'],
        total_revenue=total_revenue,
        total_users=total_users,
        total_products=total_products
    )


@app.route('/admin/order_detail/<string:order_id>')
def admin_order_detail(order_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # Get order info
    order = conn.execute("""
        SELECT
            o.*,
            u.username,
            u.email,
            u.phone AS user_phone,
            u.address AS user_address
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.order_id = ?
    """, (order_id,)).fetchone()

    if not order:
        flash('Đơn hàng không tồn tại!', 'error')
        conn.close()
        return redirect(url_for('admin_orders'))

    # Get order items
    items = conn.execute("""
        SELECT
            product_name,
            price,
            quantity,
            (price * quantity) AS subtotal
        FROM order_items
        WHERE order_id = ?
    """, (order_id,)).fetchall()

    conn.close()

    return render_template('admin_order_detail.html',
                          order=order,
                          items=items)

def _restore_stock(conn, order_id):
    """Cộng lại tồn kho cho tất cả sản phẩm của đơn (khi đơn bị hủy/xóa)."""
    items = conn.execute(
        'SELECT product_id, quantity FROM order_items WHERE order_id = ?',
        (order_id,)
    ).fetchall()
    for it in items:
        if it['product_id'] is None:
            continue  # sản phẩm đã bị xóa khỏi hệ thống
        conn.execute(
            'UPDATE products SET stock = COALESCE(stock, 0) + ? WHERE id = ?',
            (it['quantity'], it['product_id'])
        )
    return sum(it['quantity'] for it in items if it['product_id'] is not None)


# =====================================================================
# THỜI GIAN ĐƠN HÀNG (giống Shopee / TikTok Shop)
# - orders.expected_delivery : ngày giao dự kiến (cột tự thêm khi khởi động)
# - order_status_history     : lịch sử đổi trạng thái + thời điểm thực tế
# =====================================================================
SHIPPING_DAYS = 3  # giao dự kiến sau N ngày kể từ lúc đặt


def _ensure_order_time_schema():
    """Thêm cột / bảng cần thiết nếu DB cũ chưa có (chạy an toàn nhiều lần)."""
    conn = get_db_connection()
    try:
        cols = {row['name'] for row in conn.execute('PRAGMA table_info(orders)').fetchall()}
        if 'expected_delivery' not in cols:
            conn.execute('ALTER TABLE orders ADD COLUMN expected_delivery DATE')
            if 'created_at' in cols:
                # Đơn cũ: coi như giao dự kiến = ngày đặt + SHIPPING_DAYS
                conn.execute(
                    'UPDATE orders SET expected_delivery = DATE(created_at, ?) '
                    'WHERE expected_delivery IS NULL',
                    (f'+{SHIPPING_DAYS} days',)
                )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                status TEXT NOT NULL,
                note TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_order_status_history_order '
            'ON order_status_history(order_id)'
        )
        conn.commit()
    except Exception as exc:
        app.logger.warning('Không khởi tạo được thời gian đơn hàng: %s', exc)
    finally:
        conn.close()


def _log_order_status(conn, order_id, status, note=None):
    """Ghi 1 dòng lịch sử trạng thái (không commit - gọi bên ngoài)."""
    try:
        conn.execute(
            'INSERT INTO order_status_history (order_id, status, note) VALUES (?, ?, ?)',
            (order_id, status, note)
        )
    except sqlite3.Error as exc:
        app.logger.warning('Không ghi được lịch sử trạng thái: %s', exc)


def _parse_dt(value):
    """String datetime của SQLite -> datetime (giữ nguyên nếu không parse được)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value)
    for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return datetime.strptime(s.split('.')[0], fmt)
        except ValueError:
            continue
    return None


def _parse_date(value):
    d = _parse_dt(value)
    return d.date() if d else None


def _expected_delivery(order):
    """Ngày giao dự kiến (YYYY-MM-DD). Nếu cột trống thì tự tính từ ngày đặt."""
    keys = order.keys() if hasattr(order, 'keys') else order
    exp = _parse_date(order['expected_delivery']) if 'expected_delivery' in keys else None
    if exp:
        return exp.strftime('%Y-%m-%d')
    placed = _parse_date(order['created_at']) if order['created_at'] else None
    if not placed:
        return None
    return (placed + timedelta(days=SHIPPING_DAYS)).strftime('%Y-%m-%d')


def _status_display(order, expected_date) -> dict:
    """Thông tin hiển thị có thời gian: nhãn trạng thái + ngày dự kiến."""
    status = order['status']
    today = datetime.now().date()
    exp = _parse_date(expected_date)
    late_days = (today - exp).days if (exp and status != 'completed' and status != 'cancelled') else 0

    info = {'late_days': late_days if late_days > 0 else 0, 'expected': expected_date}

    if status == 'pending':
        info['text'] = 'Đang chờ người bán xác nhận'
    elif status == 'processing':
        info['text'] = f'Dự kiến giao trước {exp.strftime("%d/%m")}' if exp else 'Người bán đang đóng gói'
    elif status == 'shipped':
        if info['late_days']:
            info['text'] = f'Dự kiến giao {exp.strftime("%d/%m")} · Đang giao trễ {info["late_days"]} ngày'
        else:
            info['text'] = f'Dự kiến giao trước {exp.strftime("%d/%m")}' if exp else 'Đang trên đường tới bạn'
    elif status == 'completed':
        info['text'] = 'Giao hàng thành công'
    elif status == 'cancelled':
        info['text'] = 'Đơn hàng đã hủy'
    else:
        info['text'] = status
    return info


@app.route('/admin/order/edit/<string:order_id>', methods=['GET', 'POST'])
def admin_edit_order(order_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    if request.method == 'POST':
        new_status = (request.form.get('status') or '').strip()
        VALID_STATUS = ('pending', 'processing', 'shipped', 'completed', 'cancelled')

        if new_status not in VALID_STATUS:
            conn.close()
            flash('Trạng thái không hợp lệ!', 'error')
            return redirect(url_for('admin_orders'))

        current = conn.execute('SELECT status FROM orders WHERE order_id = ?',
                               (order_id,)).fetchone()
        if current is None:
            conn.close()
            flash('Đơn hàng không tồn tại!', 'error')
            return redirect(url_for('admin_orders'))

        old_status = current['status']

        # Đơn đã giao thì không cho hủy (tránh cộng kho khống)
        if new_status == 'cancelled' and old_status == 'completed':
            conn.close()
            flash('Đơn đã giao không thể hủy. Hãy xử lý qua chính sách đổi trả.', 'error')
            return redirect(url_for('admin_orders'))

        # Admin có thể chỉnh ngày giao dự kiến (để trống = giữ nguyên)
        new_expected = (request.form.get('expected_delivery') or '').strip()
        parsed_expected = _parse_date(new_expected)

        if parsed_expected:
            conn.execute('UPDATE orders SET status = ?, expected_delivery = ? WHERE order_id = ?',
                         (new_status, parsed_expected.strftime('%Y-%m-%d'), order_id))
        else:
            conn.execute('UPDATE orders SET status = ? WHERE order_id = ?',
                         (new_status, order_id))

        # Ghi lịch sử ngay khi trạng thái thực sự thay đổi
        if new_status != old_status:
            _log_order_status(conn, order_id, new_status)

        restored = 0
        if new_status == 'cancelled' and old_status != 'cancelled':
            # Hủy đơn -> trả hàng về kho
            restored = _restore_stock(conn, order_id)

        conn.commit()
        conn.close()

        status_label = {
            'pending': 'Chờ xác nhận',
            'processing': 'Đang xử lý',
            'shipped': 'Đang giao',
            'completed': 'Đã giao',
            'cancelled': 'Đã hủy',
        }[new_status]

        msg = f'Đã chuyển đơn #{order_id[:10]} sang "{status_label}".'
        if restored:
            msg += f' Đã hoàn {restored} sản phẩm về kho.'
        flash(msg, 'success')
        return redirect(url_for('admin_orders'))

    order = conn.execute("""
        SELECT order_id, status, created_at, expected_delivery
        FROM orders
        WHERE order_id = ?
    """, (order_id,)).fetchone()

    conn.close()

    if not order:
        flash('Đơn hàng không tồn tại!', 'error')
        return redirect(url_for('admin_orders'))

    return render_template(
        'admin_edit_order.html',
        order=order,
        expected_delivery=_expected_delivery(order),
        shipping_days=SHIPPING_DAYS
    )
@app.route('/admin/order/delete/<string:order_id>', methods=['POST'])
def admin_delete_order(order_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    order = conn.execute('SELECT status FROM orders WHERE order_id = ?',
                         (order_id,)).fetchone()
    if order is None:
        conn.close()
        flash('Đơn hàng không tồn tại!', 'error')
        return redirect(url_for('admin_orders'))

    # Xóa đơn chưa giao -> trả hàng về kho (đơn đã hủy thì kho đã được hoàn trước đó)
    restored = 0
    if order['status'] not in ('completed', 'cancelled'):
        restored = _restore_stock(conn, order_id)

    conn.execute("DELETE FROM order_status_history WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    conn.commit()
    conn.close()

    msg = 'Đã xóa đơn hàng thành công!'
    if restored:
        msg += f' Đã hoàn {restored} sản phẩm về kho.'
    flash(msg, 'success')
    return redirect(url_for('admin_orders'))



from datetime import datetime, timedelta

@app.route('/admin/reports')
def admin_reports():
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # ===== BỘ LỌC THỜI GIAN: tháng này / ngày / tháng / năm / khoảng ngày =====
    # 'all' = toàn bộ đơn đã bán (mọi đơn trừ hủy), không lọc theo ngày hoàn thành
    period = (request.args.get('period') or 'all').strip()
    if period not in ('all', 'day', 'month', 'year', 'range'):
        period = 'all'

    # Hỗ trợ ?day=rỗng (form gửi ô ngày ẩn) -> không vỡ
    today = datetime.now().date()
    try:
        sel_day = datetime.strptime((request.args.get('day') or '').strip(),
                                    '%Y-%m-%d').date()
    except ValueError:
        sel_day = today

    sel_month = request.args.get('month', type=int) or today.month
    sel_year = request.args.get('year', type=int) or today.year

    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Mặc định ('all' = toàn bộ đã bán) nên là CẢ THÁNG hiện tại,
    # vì "doanh thu theo 1 ngày" rất dễ ra 0 khi hôm đó không có đơn hoàn thành.
    if period == 'all':
        start_date = datetime(today.year, today.month, 1).date()
        end_date = today
    elif period == 'day':
        start_date = end_date = sel_day
    elif period == 'month':
        start_date = datetime(sel_year, sel_month, 1).date()
        end_date = (datetime(sel_year + (sel_month == 12),
                             (sel_month % 12) + 1, 1) - timedelta(days=1)).date()
    elif period == 'year':
        start_date = datetime(sel_year, 1, 1).date()
        end_date = datetime(sel_year, 12, 31).date()
    else:  # range
        def _parse(d, fallback):
            try:
                return datetime.strptime(d, '%Y-%m-%d').date()
            except ValueError:
                return fallback
        start_date = _parse(date_from, today - timedelta(days=29))
        end_date = _parse(date_to, today)
        if start_date > end_date:
            start_date, end_date = end_date, start_date

    range_start = start_date.strftime('%Y-%m-%d')
    range_end = end_date.strftime('%Y-%m-%d')

    # ===== THỐNG KÊ CƠ BẢN =====
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

    total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]

    # ===== DOANH THU BÁN ĐƯỢC (toàn hệ thống) =====
    sold_stats = conn.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END), 0) AS sold,
            COALESCE(SUM(CASE WHEN status = 'completed' THEN total_price ELSE 0 END), 0) AS realized,
            COUNT(CASE WHEN status != 'cancelled' THEN 1 END) AS sold_orders,
            COUNT(CASE WHEN status = 'cancelled' THEN 1 END) AS cancelled_orders
        FROM orders
    """).fetchone()

    _today = datetime.now()
    _month_start = _today.replace(day=1)
    _prev_start = (_month_start - timedelta(days=1)).replace(day=1)
    this_month = conn.execute("""
        SELECT COALESCE(SUM(total_price), 0) FROM orders
        WHERE status != 'cancelled' AND DATE(created_at) >= ?
    """, (_month_start.strftime('%Y-%m-%d'),)).fetchone()[0]
    prev_month = conn.execute("""
        SELECT COALESCE(SUM(total_price), 0) FROM orders
        WHERE status != 'cancelled' AND DATE(created_at) >= ? AND DATE(created_at) < ?
    """, (_prev_start.strftime('%Y-%m-%d'), _month_start.strftime('%Y-%m-%d'))).fetchone()[0]
    growth_percent = round((this_month - prev_month) / prev_month * 100, 1) if prev_month > 0 else None

    # Các con số dưới đây tính TRONG KHOẢNG THỜI GIAN đã chọn.
    # - 'all'  : MỌI đơn trừ đơn hủy (đúng "doanh thu đã bán được")
    # - còn lại: đơn đã giao (hoàn thành) trong khoảng ngày
    if period == 'all':
        range_stats = conn.execute("""
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE status != 'cancelled'
        """).fetchone()
    else:
        range_stats = conn.execute("""
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE status = 'completed'
              AND DATE(created_at) BETWEEN ? AND ?
        """, (range_start, range_end)).fetchone()

    range_order_count = range_stats['order_count']
    total_revenue = range_stats['revenue']

    if period == 'all':
        products_sold = conn.execute("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status != 'cancelled'
        """).fetchone()[0]
    else:
        products_sold = conn.execute("""
            SELECT COALESCE(SUM(quantity), 0)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            WHERE o.status = 'completed'
              AND DATE(o.created_at) BETWEEN ? AND ?
        """, (range_start, range_end)).fetchone()[0]

    # ===== TRẠNG THÁI ĐƠN HÀNG (CHO DOUGHNUT CHART) =====
    order_status_stats = conn.execute("""
        SELECT
            status,
            COUNT(*) as count,
            CASE status
                WHEN 'pending' THEN 'Chờ xác nhận'
                WHEN 'processing' THEN 'Đang xử lý'
                WHEN 'shipped' THEN 'Đang giao'
                WHEN 'completed' THEN 'Đã giao'
                WHEN 'cancelled' THEN 'Đã hủy'
                ELSE status
            END as label
        FROM orders
        GROUP BY status
    """).fetchall()

    status_labels = [row['label'] for row in order_status_stats]
    status_counts = [row['count'] for row in order_status_stats]

    # Màu sắc đẹp cho chart (tương thích dark/light mode)
    status_colors = ['#0c06cd', '#0dcaf0', '#0d6efd', '#198754', '#dc3545']

    # ===== BIỂU ĐỒ DOANH THU THEO KHOẢNG THỜI GIAN =====
    if period == 'all':
        revenue_rows = conn.execute("""
            SELECT DATE(created_at) as day,
                   COALESCE(SUM(total_price), 0) as revenue
            FROM orders
            WHERE status != 'cancelled'
            GROUP BY DATE(created_at)
            ORDER BY day
        """).fetchall()
    else:
        revenue_rows = conn.execute("""
            SELECT DATE(created_at) as day,
                   COALESCE(SUM(total_price), 0) as revenue
            FROM orders
            WHERE status = 'completed'
              AND DATE(created_at) BETWEEN ? AND ?
            GROUP BY DATE(created_at)
            ORDER BY day
        """, (range_start, range_end)).fetchall()

    # Gom nhóm: theo tháng nếu khoảng > 62 ngày, ngược lại theo ngày
    revenue_by_day = {row['day']: float(row['revenue']) for row in revenue_rows}
    revenue_labels, revenue_data = [], []

    span_days = (end_date - start_date).days
    if span_days > 62:
        monthly = {}
        for d, val in revenue_by_day.items():
            key = d[:7]  # YYYY-MM
            monthly[key] = monthly.get(key, 0) + val
        cursor = datetime(start_date.year, start_date.month, 1).date()
        while cursor <= end_date:
            key = cursor.strftime('%Y-%m')
            revenue_labels.append(cursor.strftime('%m/%Y'))
            revenue_data.append(monthly.get(key, 0))
            cursor = (datetime(cursor.year + (cursor.month == 12),
                               (cursor.month % 12) + 1, 1)).date()
    else:
        cursor = start_date
        while cursor <= end_date:
            key = cursor.strftime('%Y-%m-%d')
            revenue_labels.append(cursor.strftime('%d/%m'))
            revenue_data.append(revenue_by_day.get(key, 0))
            cursor += timedelta(days=1)

    revenue_chart_title = {
        'all': 'Doanh Thu Bán Được (mọi đơn trừ đơn hủy)',
        'day': 'Doanh Thu Ngày {}'.format(sel_day.strftime('%d/%m/%Y')),
        'month': 'Doanh Thu Tháng {}/{}'.format(sel_month, sel_year),
        'year': 'Doanh Thu Năm {}'.format(sel_year),
        'range': 'Doanh Thu {} → {}'.format(start_date.strftime('%d/%m/%Y'),
                                            end_date.strftime('%d/%m/%Y')),
    }[period]

    # ===== TOP 5 SẢN PHẨM BÁN CHẠY =====
    if period == 'all':
        top_products = conn.execute("""
            SELECT p.name,
                   COALESCE(SUM(oi.quantity), 0) as quantity,
                   COALESCE(SUM(oi.price * oi.quantity), 0) as revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status != 'cancelled'
            GROUP BY p.id, p.name
            ORDER BY quantity DESC
            LIMIT 5
        """).fetchall()
    else:
        top_products = conn.execute("""
            SELECT p.name,
                   COALESCE(SUM(oi.quantity), 0) as quantity,
                   COALESCE(SUM(oi.price * oi.quantity), 0) as revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status = 'completed'
              AND DATE(o.created_at) BETWEEN ? AND ?
            GROUP BY p.id, p.name
            ORDER BY quantity DESC
            LIMIT 5
        """, (range_start, range_end)).fetchall()

    # ===== TOP 5 SẢN PHẨM TỒN KHO NHIỀU NHẤT =====
    top_stock = conn.execute("""
        SELECT id, name, category, brand, price, stock
        FROM products
        ORDER BY COALESCE(stock, 0) DESC, id DESC
        LIMIT 5
    """).fetchall()

    # ===== SẢN PHẨM SẮP HẾT HÀNG (<= 5) =====
    low_stock_count = conn.execute(
        "SELECT COUNT(*) FROM products WHERE COALESCE(stock, 0) <= 5"
    ).fetchone()[0]

    # ===== TOP 5 KHÁCH HÀNG THÂN THIẾT =====
    top_customers = conn.execute("""
        SELECT
            u.username as name,
            COUNT(o.order_id) as orders,
            COALESCE(SUM(o.total_price), 0) as total
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.status = 'completed'
        GROUP BY u.id, u.username
        ORDER BY total DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        'admin_dashboard.html',
        page='reports',
        # Stats
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        pending_count=pending_count,
        total_revenue=total_revenue,
        products_sold=products_sold,
        range_order_count=range_order_count,
        low_stock_count=low_stock_count,
        top_stock=top_stock,
        # Tên tiếng Việt của danh mục (bảng tồn kho hiện mã thô -> dịch ra)
        category_labels=VALID_CATEGORIES,
        # Doanh thu bán được
        sold_revenue=sold_stats['sold'],
        realized_revenue=sold_stats['realized'],
        sold_orders=sold_stats['sold_orders'],
        cancelled_orders=sold_stats['cancelled_orders'],
        this_month_revenue=this_month,
        prev_month_revenue=prev_month,
        growth_percent=growth_percent,
        # Filter
        period=period,
        now_year=datetime.now().year,
        sel_day=sel_day.strftime('%Y-%m-%d'),
        sel_month=sel_month,
        sel_year=sel_year,
        date_from=date_from or start_date.strftime('%Y-%m-%d'),
        date_to=date_to or end_date.strftime('%Y-%m-%d'),
        range_label='{} → {}'.format(start_date.strftime('%d/%m/%Y'),
                                     end_date.strftime('%d/%m/%Y')),
        revenue_chart_title=revenue_chart_title,
        # Charts
        status_labels=status_labels,
        status_counts=status_counts,
        status_colors=status_colors,
        revenue_labels=revenue_labels,
        revenue_data=revenue_data,
        # Tables
        top_products=top_products,
        top_customers=top_customers
    )

# ================== ĐẢM BẢO FORMAT_CURRENCY CÓ SẴN TRONG MỌI TEMPLATE ==================
@app.template_filter('category_name')
def category_name_filter(value):
    """Mã danh mục -> tên tiếng Việt (dienthoai -> Điện Thoại)."""
    if not value:
        return '—'
    return VALID_CATEGORIES.get(value, value)


@app.context_processor
def inject_format_currency():
    def format_currency(value):
        try:
            return f"{int(float(value)):,} ₫"
        except (ValueError, TypeError):
            return "0 ₫"
    return dict(format_currency=format_currency, category_labels=VALID_CATEGORIES)


# === ADMIN: QUẢN LÝ KHÁCH HÀNG ===
@app.route('/admin/customers')
def admin_customers():
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    # ===== USERS =====
    customers = conn.execute("""
        SELECT
            id,
            username AS name,
            email,
            phone,
            address,
            avatar
        FROM users
        ORDER BY id DESC
    """).fetchall()

    # ===== ENRICH CUSTOMERS =====
    enriched_customers = []
    for customer in customers:
        order_stats = conn.execute("""
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(total_price), 0) AS total_spent
            FROM orders
            WHERE user_id = ? AND status = 'completed'
        """, (customer['id'],)).fetchone()

        enriched_customers.append({
            'id': customer['id'],
            'name': customer['name'],
            'email': customer['email'],
            'phone': customer['phone'] or 'Chưa cập nhật',
            'address': customer['address'] or 'Chưa cập nhật',
            'avatar': customer['avatar'],
            'order_count': order_stats['order_count'],
            'total_spent': order_stats['total_spent']
        })

    # ===== STATS FOR CARDS =====
    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    total_products = conn.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status = 'pending'"
    ).fetchone()[0]

    total_revenue = conn.execute("""
        SELECT COALESCE(SUM(total_price), 0)
        FROM orders
        WHERE status = 'completed'
    """).fetchone()[0]

    conn.close()

    return render_template(
        'admin_dashboard.html',
        page='customers',
        customers=enriched_customers,
        total_users=total_users,
        total_products=total_products,
        pending_count=pending_count,
        total_revenue=total_revenue
    )

@app.route('/admin/customer/add', methods=['POST'])
def admin_add_customer():
    """Admin tạo tài khoản khách hàng mới (mặc định mật khẩu 123456 nếu bỏ trống)."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    phone = (request.form.get('phone') or '').strip()
    address = (request.form.get('address') or '').strip()
    password = request.form.get('password') or '123456'

    if not username or not email:
        flash('Tên đăng nhập và email là bắt buộc!', 'error')
        return redirect(url_for('admin_customers'))

    if username.lower() == 'admin':
        flash('Không được dùng tên "admin"!', 'error')
        return redirect(url_for('admin_customers'))

    # Validate avatar (nếu có)
    avatar_filename = None
    avatar = request.files.get('avatar')
    if avatar and avatar.filename:
        if not allowed_file(avatar.filename):
            flash('File không hợp lệ! Chỉ chấp nhận PNG, JPG, JPEG, GIF.', 'error')
            return redirect(url_for('admin_customers'))
        safe_name = secure_filename(avatar.filename)
        avatar_filename = f"admin_{uuid.uuid4().hex}_{safe_name}"
        avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (username, email, phone, password, avatar, address, role)
            VALUES (?, ?, ?, ?, ?, ?, 'user')
        """, (username, email, phone, hash_password(password), avatar_filename, address))
        conn.commit()
        flash(f'Đã thêm khách hàng "{username}" thành công!', 'success')
    except sqlite3.IntegrityError:
        flash('Tên đăng nhập hoặc email đã tồn tại!', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_customers'))


@app.route('/admin/customer/<int:customer_id>')
def admin_view_customer(customer_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    customer = conn.execute("""
        SELECT id, username, email, phone, address, avatar, dob
        FROM users
        WHERE id = ? AND role = 'user'
    """, (customer_id,)).fetchone()

    if not customer:
        flash('Khách hàng không tồn tại!', 'error')
        conn.close()
        return redirect(url_for('admin_customers'))

    # Thống kê đơn hàng
    stats = conn.execute("""
        SELECT
            COUNT(*) AS order_count,
            COALESCE(SUM(total_price), 0) AS total_spent
        FROM orders
        WHERE user_id = ? AND status = 'completed'
    """, (customer_id,)).fetchone()

    # 5 đơn hàng gần nhất + FIX created_at
    recent_orders_raw = conn.execute("""
        SELECT order_id, total_price, status, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (customer_id,)).fetchall()

    # CHUYỂN STRING → DATETIME (giống admin_orders)
    recent_orders = []
    for order in recent_orders_raw:
        order_dict = dict(order)
        if order_dict['created_at']:
            created_at_str = order_dict['created_at']
            try:
                if '.' in created_at_str:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S.%f')
                else:
                    order_dict['created_at'] = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                order_dict['created_at'] = datetime.strptime(created_at_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        recent_orders.append(order_dict)

    # Stats cho dashboard cards
    total_users = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'user'").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'").fetchone()[0]

    conn.close()

    return render_template('admin_customer_detail.html',
                          page='customer_detail',  # Để hiển thị stats cards nếu cần
                          customer=customer,
                          stats=stats,
                          recent_orders=recent_orders,
                          total_users=total_users,
                          total_products=total_products,
                          pending_count=pending_count,
                          total_revenue=total_revenue)

@app.route('/admin/customer/edit/<int:customer_id>', methods=['GET', 'POST'])
def admin_edit_customer(customer_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    customer = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'user'", (customer_id,)).fetchone()

    if not customer:
        flash('Khách hàng không tồn tại!', 'error')
        conn.close()
        return redirect(url_for('admin_customers'))

    if request.method == 'POST':
        username = request.form.get('username').strip()
        email = request.form.get('email').strip().lower()
        phone = request.form.get('phone')
        address = request.form.get('address')
        dob = request.form.get('dob')

        if username.lower() == 'admin':
            flash('Không được dùng tên "admin"!', 'error')
            conn.close()
            return redirect(request.url)

        # Xử lý avatar
        avatar_filename = customer['avatar']
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file.filename != '':
                if not allowed_file(file.filename):
                    flash('File không hợp lệ! Chỉ chấp nhận PNG, JPG, JPEG, GIF.', 'error')
                    conn.close()
                    return redirect(request.url)

                # Xóa avatar cũ
                if avatar_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)

                # Lưu avatar mới
                safe_name = secure_filename(file.filename)
                new_filename = f"user_{customer_id}_{uuid.uuid4().hex}_{safe_name}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], new_filename))
                avatar_filename = new_filename

        try:
            conn.execute("""
                UPDATE users
                SET username = ?, email = ?, phone = ?, address = ?, dob = ?, avatar = ?
                WHERE id = ?
            """, (username, email, phone, address, dob, avatar_filename, customer_id))
            conn.commit()
            flash('Cập nhật thông tin khách hàng thành công!', 'success')
        except sqlite3.IntegrityError:
            flash('Email hoặc tên đăng nhập đã tồn tại!', 'error')

        conn.close()
        return redirect(url_for('admin_customers'))

    conn.close()
    return render_template('admin_edit_customer.html', customer=customer)


@app.route('/admin/customer/delete/<int:customer_id>', methods=['POST'])
def admin_delete_customer(customer_id):
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()

    customer = conn.execute("SELECT id, avatar, role FROM users WHERE id = ?", (customer_id,)).fetchone()
    if not customer:
        flash('Khách hàng không tồn tại!', 'error')
        conn.close()
        return redirect(url_for('admin_customers'))

    # Không cho xóa tài khoản admin qua trang khách hàng
    if customer['role'] == 'admin':
        conn.close()
        flash('Đây là tài khoản quản trị. Hãy dùng trang Quản lý tài khoản.', 'error')
        return redirect(url_for('admin_customers'))

    # Xóa avatar
    if customer['avatar']:
        path = os.path.join(app.config['UPLOAD_FOLDER'], customer['avatar'])
        if os.path.exists(path):
            os.remove(path)

    # Xóa lịch sử trạng thái + dữ liệu liên quan (an toàn với foreign key)
    conn.execute(
        "DELETE FROM order_status_history WHERE order_id IN "
        "(SELECT order_id FROM orders WHERE user_id = ?)", (customer_id,))
    conn.execute("DELETE FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE user_id = ?)", (customer_id,))
    conn.execute("DELETE FROM orders WHERE user_id = ?", (customer_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()

    flash('Đã xóa khách hàng và toàn bộ đơn hàng liên quan!', 'success')
    return redirect(url_for('admin_customers'))

@app.route('/cart', strict_slashes=False, methods=['GET', 'POST'])
def view_cart():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để xem giỏ hàng!', 'warning')
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        flash('Admin không thể truy cập giỏ hàng khách hàng!', 'danger')
        return redirect(url_for('admin_dashboard'))

    cart = session.get('cart', {})
    cart_items = list(cart.values())
    total = sum(item['price'] * item['quantity'] for item in cart_items)

    conn = get_db_connection()

    # Lấy thông tin user
    user = conn.execute("SELECT username, email, phone, address FROM users WHERE id = ?",
                        (session['user_id'],)).fetchone()

    # Lấy lịch sử đơn hàng
    orders = conn.execute("""
        SELECT o.order_id, o.total_price, o.status, o.address, o.phone, o.created_at,
               COUNT(oi.id) AS item_count
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.user_id = ?
        GROUP BY o.order_id
        ORDER BY o.created_at DESC
        LIMIT 20
    """, (session['user_id'],)).fetchall()
    conn.close()

    user_info = {
        'username': user['username'] if user else 'Khách hàng',
        'email': user['email'] if user else '',
        'phone': user['phone'] or '',
        'address': user['address'] or ''
    }

    if request.method == 'POST':
        address = request.form.get('address', '').strip()
        phone = request.form.get('phone', '').strip()
        note = request.form.get('note', '').strip()  # Có thể để trống

        if not address or not phone:
            flash('Vui lòng nhập đầy đủ địa chỉ và số điện thoại!', 'danger')
            return redirect(url_for('view_cart'))

        if not cart_items:
            flash('Giỏ hàng của bạn đang trống!', 'warning')
            return redirect(url_for('view_cart'))

        try:
            conn = get_db_connection()
            order_id = str(uuid.uuid4())[:12].upper()
            now = datetime.now()
            created_at = now.strftime('%Y-%m-%d %H:%M:%S')  # Định dạng chuỗi an toàn
            expected_delivery = (now + timedelta(days=SHIPPING_DAYS)).strftime('%Y-%m-%d')

            # === KIỂM TRA TỒN KHO TRƯỚC KHI TẠO ĐƠN ===
            # Đọc lại giá + tồn kho từ DB (không tin dữ liệu trong session)
            stock_errors = []
            for item in cart_items:
                row = conn.execute('SELECT name, price, stock FROM products WHERE id = ?',
                                   (item['id'],)).fetchone()
                if row is None:
                    stock_errors.append(f'Sản phẩm "{item["name"]}" không còn trong hệ thống.')
                elif row['stock'] is not None and item['quantity'] > row['stock']:
                    stock_errors.append(
                        f'"{row["name"]}" chỉ còn {row["stock"]} trong kho (bạn đặt {item["quantity"]}).')

            if stock_errors:
                conn.close()
                for msg in stock_errors:
                    flash(msg, 'warning')
                return redirect(url_for('view_cart'))

            # === KIỂM TRA VÀ CHÈN AN TOÀN ==="
            cursor = conn.cursor()

            # Kiểm tra xem cột note có tồn tại không
            cursor.execute("PRAGMA table_info(orders)")
            columns = [col[1] for col in cursor.fetchall()]

            extra_cols, extra_vals = [], []
            if 'note' in columns:
                extra_cols.append('note')
                extra_vals.append(note)
            if 'created_at' in columns:
                extra_cols.append('created_at')
                extra_vals.append(created_at)
            if 'expected_delivery' in columns:
                extra_cols.append('expected_delivery')
                extra_vals.append(expected_delivery)

            base_cols = ['order_id', 'user_id', 'total_price', 'status', 'address', 'phone']
            all_cols = base_cols + extra_cols
            placeholders = ', '.join(['?'] * len(all_cols))
            conn.execute(
                f"INSERT INTO orders ({', '.join(all_cols)}) VALUES ({placeholders})",
                (order_id, session['user_id'], total, 'pending', address, phone) + tuple(extra_vals)
            )
            # Mốc đầu tiên của dòng thời gian
            _log_order_status(conn, order_id, 'pending')

            # Thêm các sản phẩm vào order_items + TRỪ TỒN KHO
            for item in cart_items:
                conn.execute("""
                    INSERT INTO order_items
                    (order_id, product_id, product_name, price, quantity)
                    VALUES (?, ?, ?, ?, ?)
                """, (order_id, item['id'], item['name'], item['price'], item['quantity']))

                # Trừ kho ngay khi đặt hàng (cùng transaction với INSERT đơn)
                conn.execute(
                    'UPDATE products SET stock = MAX(COALESCE(stock, 0) - ?, 0) WHERE id = ?',
                    (item['quantity'], item['id'])
                )

            conn.commit()
            conn.close()

            # Cập nhật thông tin giao hàng cho user
            try:
                conn = get_db_connection()
                conn.execute("UPDATE users SET phone = ?, address = ? WHERE id = ?",
                             (phone, address, session['user_id']))
                conn.commit()
            except Exception as e:
                print(f"Lỗi cập nhật thông tin user: {e}")
            finally:
                conn.close()

            # Xóa giỏ hàng
            session.pop('cart', None)
            session.modified = True

            flash(f'Đặt hàng thành công! Mã đơn: #{order_id}', 'success')
            return redirect(url_for('view_cart'))

        except Exception as e:
            print(f"[LỖI ĐẶT HÀNG] {e}")  # In ra console để bạn xem lỗi thật
            flash('Có lỗi xảy ra khi đặt hàng. Vui lòng thử lại sau!', 'danger')
            return redirect(url_for('view_cart'))

    return render_template('cart.html',
                           cart=cart_items,
                           total=total,
                           user=user_info,
                           orders=orders)
@app.route('/my/order/<string:order_id>')
def my_order_detail(order_id):
    """Khách xem chi tiết đơn của chính mình (JOIN Order + OrderDetail + Product)."""
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để xem đơn hàng!', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    order = conn.execute("""
        SELECT o.*, u.username, u.email
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.order_id = ? AND o.user_id = ?
    """, (order_id, session['user_id'])).fetchone()

    if not order:
        conn.close()
        flash('Không tìm thấy đơn hàng!', 'error')
        return redirect(url_for('view_cart'))

    # JOIN chi tiết đơn + thông tin sản phẩm hiện tại
    items = conn.execute("""
        SELECT oi.id, oi.product_id, oi.product_name, oi.price, oi.quantity,
               (oi.price * oi.quantity) AS subtotal,
               p.name AS current_name, p.image AS image, p.brand AS brand
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
    """, (order_id,)).fetchall()
    conn.close()

    return render_template('my_order_detail.html',
                           order=order,
                           items=items,
                           auto_print=request.args.get('print') == '1')


# =====================================================================
# TRANG THEO DÕI ĐƠN HÀNG (khách hàng)
# - Xem tiến trình: Chờ xác nhận -> Đang xử lý -> Đang giao -> Đã giao
# - Tra cứu 1 đơn theo mã đơn
# - Tự động cập nhật trạng thái mỗi 30 giây (AJAX)
# =====================================================================
STATUS_INFO = {
    'pending':    {'label': 'Chờ xác nhận', 'icon': 'fa-clock',       'color': '#ffc107', 'step': 1},
    'processing': {'label': 'Đang xử lý',    'icon': 'fa-box',         'color': '#0dcaf0', 'step': 2},
    'shipped':    {'label': 'Đang giao',     'icon': 'fa-truck',       'color': '#0d6efd', 'step': 3},
    'completed':  {'label': 'Đã giao',       'icon': 'fa-check',       'color': '#198754', 'step': 4},
    'cancelled':  {'label': 'Đã hủy',        'icon': 'fa-xmark',          'color': '#dc3545', 'step': 0},
}
TRACKING_STEPS = [
    ('pending', 'Chờ xác nhận'),
    ('processing', 'Đang xử lý'),
    ('shipped', 'Đang giao'),
    ('completed', 'Đã giao'),
]


def _tracking_orders(conn, user_id):
    """Lấy danh sách đơn của 1 khách kèm số sản phẩm (mới nhất trước)."""
    return conn.execute("""
        SELECT o.order_id, o.total_price, o.status, o.address, o.phone, o.created_at,
               o.expected_delivery,
               COUNT(oi.id) AS item_count,
               COALESCE(SUM(oi.quantity), 0) AS total_qty
        FROM orders o
        LEFT JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.user_id = ?
        GROUP BY o.order_id
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT 50
    """, (user_id,)).fetchall()


@app.route('/my/orders')
def my_orders():
    """Trang Theo dõi đơn hàng của khách (danh sách + tra cứu theo mã)."""
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để theo dõi đơn hàng!', 'warning')
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        flash('Admin vui lòng dùng trang Quản lý đơn hàng.', 'info')
        return redirect(url_for('admin_orders'))

    keyword = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '').strip()
    if status_filter not in STATUS_INFO:
        status_filter = ''

    conn = get_db_connection()
    rows = _tracking_orders(conn, session['user_id'])

    # Lịch sử trạng thái: {order_id: {status: 'YYYY-MM-DD HH:MM'}}
    history = {}
    try:
        for h in conn.execute("""
            SELECT order_id, status, MIN(created_at) AS at
            FROM order_status_history
            GROUP BY order_id, status
        """).fetchall():
            history.setdefault(h['order_id'], {})[h['status']] = (h['at'] or '')[:16]
    except sqlite3.Error as exc:
        app.logger.warning('Không đọc được lịch sử trạng thái: %s', exc)

    # Thống kê nhanh theo trạng thái (trên toàn bộ đơn của khách)
    counts = {'all': len(rows)}
    for row in rows:
        counts[row['status']] = counts.get(row['status'], 0) + 1

    # Lọc theo từ khoá / trạng thái (lọc trong Python, danh sách đã bị giới hạn 50 đơn)
    orders = []
    for row in rows:
        if status_filter and row['status'] != status_filter:
            continue
        if keyword and keyword.lower() not in (row['order_id'] or '').lower():
            continue
        orders.append(row)

    conn.close()

    # Gắn ngày giao dự kiến + ngày thực tế của từng bước vào từng đơn
    enriched_orders = []
    for row in orders:
        d = dict(row)
        d['expected_delivery'] = _expected_delivery(row)
        d['display'] = _status_display(row, d['expected_delivery'])
        d['history'] = history.get(row['order_id'], {})
        # Ngày đặt hiển thị dạng dd/mm/yyyy HH:MM
        placed = _parse_dt(row['created_at'])
        d['placed_at'] = placed.strftime('%d/%m/%Y %H:%M') if placed else (row['created_at'] or '—')
        d['expected_at'] = (_parse_date(d['expected_delivery']).strftime('%d/%m/%Y')
                            if d['expected_delivery'] else None)
        enriched_orders.append(d)

    return render_template('my_orders.html',
                           orders=enriched_orders,
                           counts=counts,
                           status=status_filter,
                           keyword=keyword,
                           status_info=STATUS_INFO,
                           tracking_steps=TRACKING_STEPS)


@app.route('/my/order/<string:order_id>/status')
def my_order_status(order_id):
    """API JSON nhỏ để trang theo dõi tự cập nhật trạng thái."""
    if 'user_id' not in session:
        return jsonify({'ok': False, 'error': 'auth'}), 401

    conn = get_db_connection()
    row = conn.execute(
        'SELECT status FROM orders WHERE order_id = ? AND user_id = ?',
        (order_id, session['user_id'])
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404

    info = STATUS_INFO.get(row['status'], {'label': row['status'], 'icon': 'fa-question', 'color': '#6c757d', 'step': 0})
    return jsonify({
        'ok': True,
        'order_id': order_id,
        'status': row['status'],
        'label': info['label'],
        'step': info['step'],
        'color': info['color'],
    })


@app.route('/add_to_cart/<int:product_id>')
@app.route('/add_to_cart/<int:product_id>/<int:quantity>')
def add_to_cart(product_id, quantity=1):
    ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if 'user_id' not in session or session.get('role') == 'admin':
        message = 'Chỉ khách hàng mới được thêm vào giỏ!'
        if ajax:
            return jsonify({'ok': False, 'error': message, 'redirect': url_for('login')}), 401
        flash(message, 'error')
        return redirect_back_or_index()

    conn = get_db_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()

    if not product:
        message = 'Sản phẩm không tồn tại!'
        if ajax:
            return jsonify({'ok': False, 'error': message}), 404
        flash(message, 'error')
        return redirect_back_or_index()

    cart = session.get('cart', {})
    key = str(product_id)
    current_quantity = cart.get(key, {}).get('quantity', 0)
    stock = product['stock'] or 0
    if stock <= 0:
        message = f'Sản phẩm "{product["name"]}" hiện đã hết hàng.'
        if ajax:
            return jsonify({'ok': False, 'error': message}), 400
        flash(message, 'warning')
        return redirect_back_or_index()

    if current_quantity + quantity > stock:
        available = max(stock - current_quantity, 0)
        if available:
            message = f'Chỉ có thể thêm tối đa {available} sản phẩm "{product["name"]}" vào giỏ.'
        else:
            message = f'Bạn đã thêm đủ số lượng tồn kho của "{product["name"]}" vào giỏ.'
        if ajax:
            return jsonify({'ok': False, 'error': message}), 400
        flash(message, 'warning')
        return redirect_back_or_index()

    if key in cart:
        cart[key]['quantity'] = current_quantity + quantity
    else:
        cart[key] = {
            'id': product['id'],
            'name': product['name'],
            'price': product['price'],
            'image': product['image'],
            'quantity': quantity
        }

    session['cart'] = cart
    session.modified = True
    cart_count = sum(item.get('quantity', 0) for item in cart.values())
    message = f'Đã thêm {quantity} sản phẩm "{product["name"]}" vào giỏ hàng!'
    if ajax:
        return jsonify({'ok': True, 'message': message, 'cart_count': cart_count})
    flash(message, 'success')
    return redirect_back_or_index()

@app.route('/update_cart/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập!', 'error')
        return redirect(url_for('login'))

    quantity = request.form.get('quantity', type=int)

    cart = session.get('cart', {})
    key = str(product_id)

    if quantity is None or quantity < 0:
        flash('Số lượng không hợp lệ!', 'error')
    elif key not in cart:
        flash('Sản phẩm không tồn tại trong giỏ!', 'error')
    elif quantity == 0:
        # Quy ước: nhập 0/cột trống = xóa dòng khỏi giỏ
        del cart[key]
        session['cart'] = cart
        session.modified = True
        flash('Đã xóa sản phẩm khỏi giỏ hàng!', 'info')
    else:
        # Không cho vượt quá tồn kho thực tế
        conn = get_db_connection()
        row = conn.execute('SELECT name, stock FROM products WHERE id = ?', (product_id,)).fetchone()
        conn.close()
        if row and row['stock'] is not None and quantity > row['stock']:
            quantity = row['stock']
            flash(f'Chỉ còn {row["stock"]} sản phẩm "{row["name"]}" trong kho!', 'warning')
        else:
            flash('Cập nhật số lượng thành công!', 'success')

        cart[key]['quantity'] = quantity
        session['cart'] = cart
        session.modified = True

    return redirect(url_for('view_cart'))


@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để thao tác giỏ hàng!', 'error')
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        flash('Admin không thể thao tác giỏ hàng!', 'error')
        return redirect(url_for('index'))

    cart = session.get('cart', {})
    key = str(product_id)

    if key in cart:
        del cart[key]
        session['cart'] = cart
        flash('Đã xóa sản phẩm khỏi giỏ hàng!', 'success')
    else:
        flash('Sản phẩm không tồn tại trong giỏ hàng!', 'info')

    return redirect(url_for('view_cart'))








@app.route('/buy_now/<int:product_id>')
def buy_now(product_id):
    # Thêm vào giỏ trước
    add_to_cart(product_id, quantity=1)
    return redirect(url_for('view_cart'))  # Đi thẳng đến trang giỏ để đặt hàng


@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    flash('Đã xóa giỏ hàng!', 'info')
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập để xem hồ sơ!', 'error')
        return redirect(url_for('login'))
    conn = get_db_connection()
    try:
        user = conn.execute("""
            SELECT
                id,
                username,
                email,
                phone,
                dob,
                address,
                role,
                avatar
            FROM users
            WHERE id = ?
        """, (session['user_id'],)).fetchone()

        if user is None:
            flash('Không tìm thấy thông tin người dùng.', 'error')
            conn.close()
            return redirect(url_for('logout'))

        # Chuyển sqlite3.Row thành dict để dễ dùng trong template hơn (tùy chọn)
        user_dict = dict(user)

    except Exception as e:
        flash('Lỗi tải thông tin hồ sơ.', 'error')
        conn.close()
        return redirect(url_for('index'))
    finally:
        conn.close()
    return render_template('profile.html', user=user_dict)
@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        flash('Vui lòng đăng nhập!', 'error')
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        phone = request.form.get('phone').strip()
        dob = request.form.get('dob')
        address = request.form.get('address').strip()
        avatar_file = request.files.get('avatar')

        # Handle avatar upload
        avatar_filename = None
        old_avatar = conn.execute('SELECT avatar FROM users WHERE id = ?',
                                  (session['user_id'],)).fetchone()['avatar']

        if avatar_file and allowed_file(avatar_file.filename):
            safe_name = secure_filename(avatar_file.filename)
            avatar_filename = f"{session['username']}_{uuid.uuid4().hex}_{safe_name}"
            avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_filename))

            # Delete old avatar if exists and is not the default/placeholder
            if old_avatar:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_avatar)
                if os.path.exists(old_path):
                    os.remove(old_path)
        else:
            avatar_filename = old_avatar  # keep old avatar if no new file

        # Update user info
        try:
            conn.execute("""
                UPDATE users
                SET phone = ?, dob = ?, address = ?, avatar = ?
                WHERE id = ?
            """, (phone, dob, address, avatar_filename, session['user_id']))
            conn.commit()
            flash('Cập nhật hồ sơ thành công!', 'success')

            # Update session username if needed (in case you want to use it elsewhere)
            # session['username'] remains the same because username cannot be changed here

            return redirect(url_for('profile'))

        except Exception as e:
            flash('Có lỗi xảy ra khi cập nhật hồ sơ.', 'error')
            print(e)
        finally:
            conn.close()
        # POST lỗi -> quay lại form; KHÔNG chạy tiếp xuống phần GET bên dưới
        return redirect(url_for('edit_profile'))

    # GET request → show edit form
    user = conn.execute("""
        SELECT username, email, phone, dob, address, avatar, role
        FROM users WHERE id = ?
    """, (session['user_id'],)).fetchone()
    conn.close()

    if user is None:
        flash('Không tìm thấy người dùng.', 'error')
        return redirect(url_for('logout'))

    return render_template('edit_profile.html', user=user)
# Routes category
# Các route này PHẢI render template, không được return string.
# Template đang gọi url_for('dienthoai'), url_for('laptop')... nên endpoint phải tồn tại
# và phải hiển thị trang sản phẩm theo danh mục.
CATEGORY_ENDPOINTS = {
    'dienthoai': 'dienthoai',
    'tulanh':    'tulanh',
    'dongho':    'dongho',
    'laptop':    'laptop',
    'mayanh':    'mayanh',
    'dieuhoa':   'dieuhoa',
    'tainghe':   'tainghe',
}
# Nhãn hiển thị cho từng cột thông số, theo danh mục (dùng ở trang chi tiết)
SPEC_LABELS = {
    'cpu': 'CPU', 'display': 'Màn hình', 'ram': 'RAM', 'storage': 'Bộ nhớ',
    'gpu': 'Card đồ họa', 'battery': 'Pin', 'camera': 'Camera',
    'chip': 'Chip', 'sensor': 'Cảm biến', 'water_resistance': 'Chống nước',
    'wifi': 'Kết nối', 'power': 'Công suất', 'energy': 'Tiết kiệm năng lượng',
    'ports': 'Cổng kết nối', 'wifi': 'Wi-Fi', 'cooling': 'Công nghệ làm lạnh',
    'capacity': 'Dung tích', 'type': 'Kiểu', 'cooling_tech': 'Công nghệ làm lạnh',
    'energy_rating': 'Tiết kiệm năng lượng', 'motor': 'Động cơ',
    'technology': 'Công nghệ', 'warranty': 'Bảo hành', 'shelves': 'Số ngăn',
    'power': 'Công suất', 'speed_levels': 'Cấp tốc độ',
    'control_type': 'Điều khiển', 'oscillation': 'Đảo gió', 'timer': 'Hẹn giờ',
    'size': 'Kích thước', 'blade_type': 'Kiểu cánh', 'filter': 'Bộ lọc',
    'zones': 'Vùng nấu', 'burners': 'Số bếp', 'grates': 'Mặt bếp',
    'safety': 'An toàn', 'ignition': 'Đánh lửa',
}
SPEC_LABELS.update(EXTRA_SPEC_LABELS)

VALID_CATEGORIES = {
    'dienthoai': 'Điện Thoại',
    'dongho': 'Đồng Hồ Thông Minh',
    'laptop': 'Laptop',
    'maytinhbanpc': 'Máy Tính Bàn / PC',
    'tulanh': 'Tủ Lạnh',
    'quat': 'Quạt',
    'maygiatsay': 'Máy Giặt & Sấy',
    'beptu': 'Bếp Từ',
    'tainghe': 'Tai Nghe',
    'mayanh': 'Máy Ảnh',
    'dieuhoa': 'Điều Hòa',
}


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Trang xem chi tiết sản phẩm (mọi người đều xem được)."""
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()

    if product is None:
        conn.close()
        flash('Sản phẩm không tồn tại hoặc đã bị xóa!', 'error')
        return redirect(url_for('index'))

    product = dict(product)

    # Toàn bộ thông số kỹ thuật (không chỉ 4 dòng như trang danh mục)
    specs = []
    for item in get_product_specs(product):
        label = SPEC_LABELS.get(item['icon_type'])
        if label:
            specs.append({'label': label, 'value': item['value'], 'icon': item['icon']})

    # Sản phẩm cùng danh mục (gợi ý)
    related = conn.execute("""
        SELECT id, name, brand, price, image
        FROM products
        WHERE category = ? AND id != ?
        ORDER BY id DESC
        LIMIT 4
    """, (product['category'], product_id)).fetchall()

    conn.close()

    return render_template('product_detail.html',
                           product=product,
                           specs=specs,
                           related=related,
                           category_name=VALID_CATEGORIES.get(product['category'], product['category']),
                           category_key=product['category'])


def _render_category(category):
    """Render trang danh mục dùng chung cho mọi alias route bên dưới."""
    page = request.args.get('page', 1, type=int)
    per_page = 12

    conn = get_db_connection()
    total = conn.execute(
        "SELECT COUNT(*) FROM products WHERE category = ?",
        (category,)
    ).fetchone()[0]

    products = conn.execute("""
        SELECT id, product_id, name, category, brand, price, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
        WHERE category = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (category, per_page, (page - 1) * per_page)).fetchall()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('category.html',
                           products=products,
                           category_name=VALID_CATEGORIES.get(category, category),
                           category_key=category,
                           page=page,
                           total_pages=total_pages,
                           total_products=total)


@app.route('/dienthoai')
def dienthoai():
    return _render_category('dienthoai')

@app.route('/tulanh')
def tulanh():
    return _render_category('tulanh')

@app.route('/dongho')
def dongho():
    return _render_category('dongho')

@app.route('/laptop')
def laptop():
    return _render_category('laptop')

@app.route('/mayanh')
def mayanh():
    return _render_category('mayanh')

@app.route('/dieuhoa')
def dieuhoa():
    return _render_category('dieuhoa')

@app.route('/tainghe')
def tainghe():
    return _render_category('tainghe')

@app.route('/maytinh')
def man_hinh_may_tinh():
    return _render_category('maytinhbanpc')


@app.route('/category/<category>')
def category_products(category):
    """Hiển thị sản phẩm theo danh mục"""
    # Danh sách danh mục hợp lệ (dùng chung hằng số VALID_CATEGORIES)
    valid_categories = VALID_CATEGORIES

    if category not in valid_categories:
        flash('Danh mục không tồn tại!', 'danger')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    per_page = 12  # Số sản phẩm mỗi trang

    conn = get_db_connection()

    # Đếm tổng sản phẩm trong danh mục
    total = conn.execute(
        "SELECT COUNT(*) FROM products WHERE category = ?",
        (category,)
    ).fetchone()[0]

    # Lấy sản phẩm cho trang hiện tại + tất cả specs để hiển thị
    products = conn.execute("""
        SELECT id, product_id, name, category, brand, price, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
        WHERE category = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """, (category, per_page, (page - 1) * per_page)).fetchall()

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('category.html',
                           products=products,
                           category_name=valid_categories[category],
                           category_key=category,
                           page=page,
                           total_pages=total_pages,
                           total_products=total)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()

    if not query:
        flash('Vui lòng nhập từ khóa tìm kiếm!', 'warning')
        return redirect(url_for('index'))

    page = request.args.get('page', 1, type=int)
    per_page = 12

    conn = get_db_connection()

    # Tìm kiếm trong tên sản phẩm, thương hiệu, và các thông số phổ biến
    search_pattern = f"%{query}%"
    products = conn.execute("""
        SELECT id, product_id, name, category, brand, price, image,
               cpu, display, ram, storage, gpu, battery, camera,
               chip, sensor, water_resistance,
               ports, wifi, cooling,
               capacity, type, cooling_tech, energy_rating, motor, technology, warranty, shelves,
               power, speed_levels, control_type, oscillation, timer, size, blade_type, filter,
               zones, burners, grates, safety, ignition
        FROM products
        WHERE name LIKE ?
           OR brand LIKE ?
           OR cpu LIKE ?
           OR display LIKE ?
           OR ram LIKE ?
           OR storage LIKE ?
           OR camera LIKE ?
           OR capacity LIKE ?
        ORDER BY
            CASE
                WHEN name LIKE ? THEN 1
                WHEN brand LIKE ? THEN 2
                ELSE 3
            END,
            name
        LIMIT ? OFFSET ?
    """, (search_pattern, search_pattern, search_pattern, search_pattern,
          search_pattern, search_pattern, search_pattern, search_pattern,
          search_pattern, search_pattern,
          per_page, (page - 1) * per_page)).fetchall()

    # Đếm tổng kết quả
    total = conn.execute("""
        SELECT COUNT(*) FROM products
        WHERE name LIKE ?
           OR brand LIKE ?
           OR cpu LIKE ?
           OR display LIKE ?
           OR ram LIKE ?
           OR storage LIKE ?
           OR camera LIKE ?
           OR capacity LIKE ?
    """, (search_pattern, search_pattern, search_pattern, search_pattern,
          search_pattern, search_pattern, search_pattern, search_pattern)).fetchone()[0]

    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('search_results.html',
                           products=products,
                           query=query,
                           total_products=total,
                           page=page,
                           total_pages=total_pages)


def _chat_session_key():
    """Mã phiên chat: dùng user_id nếu đã đăng nhập, ngược lại tạo mã ngẫu nhiên."""
    if 'user_id' in session:
        return f"user-{session['user_id']}"
    if '_chat_sid' not in session:
        session['_chat_sid'] = uuid.uuid4().hex[:12]
    return f"guest-{session['_chat_sid']}"


def _save_chat_message(role, content):
    """INSERT 1 tin nhắn vào bảng chat_messages (dùng trong báo cáo)."""
    try:
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO chat_messages (session_key, user_id, username, role, content)
            VALUES (?, ?, ?, ?, ?)
        """, (_chat_session_key(), session.get('user_id'), session.get('username'),
              role, content))
        conn.commit()
        conn.close()
    except Exception as exc:  # bảng chưa tạo / DB bận -> không làm hỏng trang
        app.logger.warning('Không lưu được chat: %s', exc)


@app.route('/chatbot', methods=['POST'])
def chatbot_api():
    """API JSON cho widget chat."""
    from chatbot import get_bot_reply

    # Chặn spam: tối đa 20 tin / 60 giây cho mỗi phiên
    now = time.time()
    bucket = session.get('_chat_bucket', [])
    bucket = [t for t in bucket if now - t < 60]
    if len(bucket) >= 20:
        return jsonify({
            'reply': 'Bạn đang gửi yêu cầu quá nhanh. Vui lòng chờ vài giây rồi thử lại.',
            'links': [],
        }), 429
    bucket.append(now)
    session['_chat_bucket'] = bucket

    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({'reply': 'Bạn muốn hỏi gì ạ?', 'links': []})

    # Lưu câu hỏi của khách
    _save_chat_message('user', message)

    try:
        result = get_bot_reply(message, get_db_connection,
                               user_id=session.get('user_id'))
    except Exception as e:
        app.logger.exception('Chatbot error: %s', e)
        result = {
            'reply': 'Xin lỗi, trợ lý đang bận. Bạn vui lòng thử lại sau hoặc gọi hotline 0917873816.',
            'links': [],
        }

    # Lưu câu trả lời của bot (bỏ thẻ HTML để dễ đọc khi xem lại)
    import re as _re
    plain = _re.sub(r'<[^>]+>', '', result.get('reply', ''))
    _save_chat_message('bot', plain)

    return jsonify(result)


@app.route('/chatbot', methods=['DELETE'])
@app.route('/chatbot/clear', methods=['POST', 'DELETE'])
def chatbot_clear():
    """Khách xoá hội thoại của CHÍNH MÌNH (trong DB + phía trình duyệt).

    Chỉ xoá theo session_key hiện tại -> không đụng dữ liệu của khách khác.
    """
    if not session.get('user_id') and '_chat_sid' not in session:
        return jsonify({'success': True, 'deleted': 0})

    key = _chat_session_key()
    try:
        conn = get_db_connection()
        cur = conn.execute('DELETE FROM chat_messages WHERE session_key = ?', (key,))
        conn.commit()
        deleted = cur.rowcount
        conn.close()
    except Exception as exc:
        app.logger.warning('Không xoá được chat: %s', exc)
        return jsonify({'success': False, 'error': 'Không xoá được lịch sử chat.'}), 500

    return jsonify({'success': True, 'deleted': deleted})


@app.route('/admin/chat-history')
def admin_chat_history():
    """Admin xem lại hội thoại chatbot đã lưu trong bảng chat_messages."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    keyword = request.args.get('q', '').strip()
    conn = get_db_connection()

    where, params = [], []
    if keyword:
        where.append('(content LIKE ? OR username LIKE ? OR session_key LIKE ?)')
        like = f'%{keyword}%'
        params += [like, like, like]
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    messages = conn.execute(f"""
        SELECT id, session_key, user_id, username, role, content, created_at
        FROM chat_messages
        {where_sql}
        ORDER BY id DESC
        LIMIT 300
    """, params).fetchall()

    # Gom theo phiên để dễ đọc
    sessions = {}
    for m in messages:
        s = sessions.setdefault(m['session_key'], {
            'key': m['session_key'],
            'username': m['username'] or 'Khách vãng lai',
            'messages': [],
        })
        s['messages'].append(dict(m))
    for s in sessions.values():
        s['messages'].reverse()  # trong mỗi phiên: cũ -> mới

    stats = {
        'total': conn.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0],
        'questions': conn.execute("SELECT COUNT(*) FROM chat_messages WHERE role='user'").fetchone()[0],
        'sessions': conn.execute('SELECT COUNT(DISTINCT session_key) FROM chat_messages').fetchone()[0],
    }
    top_questions = conn.execute("""
        SELECT content, COUNT(*) AS times
        FROM chat_messages WHERE role = 'user'
        GROUP BY content ORDER BY times DESC LIMIT 5
    """).fetchall()

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    pending_count = conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0]
    total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'").fetchone()[0]
    conn.close()

    return render_template('admin_chat_history.html',
                           sessions=list(sessions.values()),
                           stats=stats,
                           top_questions=top_questions,
                           keyword=keyword,
                           total_users=total_users,
                           total_products=total_products,
                           pending_count=pending_count,
                           total_revenue=total_revenue)


@app.route('/lienhe', methods=['GET', 'POST'])
def lienhe():
    """Trang liên hệ - chỉ định nghĩa MỘT lần duy nhất."""
    if request.method == 'POST':
        flash('Cảm ơn bạn đã gửi liên hệ!', 'success')
        return redirect(url_for('lienhe'))
    return render_template('lienhe.html')


# =====================================================================
# QUẢN LÝ TÀI KHOẢN QUẢN TRỊ (chỉ admin)
# - Xem danh sách / thêm / sửa / xóa tài khoản có role = 'admin'
# =====================================================================

def _admin_stats(conn):
    """Các số liệu dùng chung cho sidebar/cards ở mọi trang admin."""
    return {
        'total_users': conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        'total_products': conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        'pending_count': conn.execute(
            "SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
        'total_revenue': conn.execute(
            "SELECT COALESCE(SUM(total_price), 0) FROM orders WHERE status = 'completed'").fetchone()[0],
    }


@app.route('/admin/users')
def admin_users():
    """Danh sách tài khoản quản trị."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    keyword = request.args.get('q', '').strip()
    conn = get_db_connection()

    # DB cũ có thể chưa có cột created_at -> kiểm tra trước khi SELECT
    has_created = any(
        col['name'] == 'created_at'
        for col in conn.execute('PRAGMA table_info(users)').fetchall()
    )
    created_col = 'created_at' if has_created else "'' AS created_at"

    sql = f"""
        SELECT id, username, email, phone, address, avatar, dob, role, {created_col}
        FROM users
        WHERE role = 'admin'
    """
    params = []
    if keyword:
        sql += " AND (username LIKE ? OR email LIKE ? OR phone LIKE ?)"
        like = f'%{keyword}%'
        params.extend([like, like, like])
    sql += " ORDER BY id ASC"

    admins = []
    for row in conn.execute(sql, params).fetchall():
        d = dict(row)
        d['is_me'] = (d['id'] == session.get('user_id'))
        admins.append(d)

    stats = _admin_stats(conn)
    conn.close()

    return render_template('admin_dashboard.html',
                           page='admin_users',
                           admins=admins,
                           keyword=keyword,
                           total_admins=len(admins),
                           **stats)


@app.route('/admin/user/add', methods=['POST'])
@app.route('/admin/users/add', methods=['POST'])
def admin_add_user():
    """Tạo tài khoản quản trị mới."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    username = (request.form.get('username') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    phone = (request.form.get('phone') or '').strip()
    address = (request.form.get('address') or '').strip()
    password = request.form.get('password') or ''
    confirm = request.form.get('confirm_password') or ''

    if not username or not email or not password:
        flash('Tên đăng nhập, email và mật khẩu là bắt buộc!', 'error')
        return redirect(url_for('admin_users'))

    if len(password) < 6:
        flash('Mật khẩu phải có ít nhất 6 ký tự!', 'error')
        return redirect(url_for('admin_users'))

    if confirm and confirm != password:
        flash('Mật khẩu xác nhận không khớp!', 'error')
        return redirect(url_for('admin_users'))

    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT INTO users (username, email, phone, password, avatar, address, role)
            VALUES (?, ?, ?, ?, NULL, ?, 'admin')
        """, (username, email, phone, hash_password(password), address))
        conn.commit()
        flash(f'Đã tạo tài khoản quản trị "{username}".', 'success')
    except sqlite3.IntegrityError:
        flash('Tên đăng nhập hoặc email đã tồn tại!', 'error')
    finally:
        conn.close()

    return redirect(url_for('admin_users'))


@app.route('/admin/user/edit/<int:user_id>', methods=['GET', 'POST'])
def admin_edit_user(user_id):
    """Sửa tài khoản quản trị (mật khẩu để trống = giữ nguyên)."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'admin'", (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        flash('Tài khoản quản trị không tồn tại!', 'error')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        phone = (request.form.get('phone') or '').strip()
        address = (request.form.get('address') or '').strip()
        new_password = request.form.get('password') or ''

        if not username or not email:
            flash('Tên đăng nhập và email là bắt buộc!', 'error')
            conn.close()
            return redirect(url_for('admin_edit_user', user_id=user_id))

        try:
            if new_password:
                if len(new_password) < 6:
                    flash('Mật khẩu phải có ít nhất 6 ký tự!', 'error')
                    conn.close()
                    return redirect(url_for('admin_edit_user', user_id=user_id))
                hashed = hash_password(new_password)
            else:
                hashed = user['password']

            conn.execute("""
                UPDATE users SET username = ?, email = ?, phone = ?, address = ?, password = ?
                WHERE id = ? AND role = 'admin'
            """, (username, email, phone, address, hashed, user_id))
            conn.commit()

            # Nếu tự sửa chính mình thì cập nhật session
            if user_id == session.get('user_id'):
                session['username'] = username

            flash('Cập nhật tài khoản quản trị thành công!', 'success')
            conn.close()
            return redirect(url_for('admin_users'))
        except sqlite3.IntegrityError:
            flash('Tên đăng nhập hoặc email đã tồn tại!', 'error')
        finally:
            if conn:
                conn.close()

        return redirect(url_for('admin_edit_user', user_id=user_id))

    stats = _admin_stats(conn)
    conn.close()
    return render_template('admin_edit_user.html', user=user, **stats)


@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    """Xóa tài khoản quản trị. Không cho xóa chính mình / admin cuối cùng."""
    if session.get('role') != 'admin':
        flash('Chỉ quản trị viên mới được truy cập!', 'error')
        return redirect(url_for('index'))

    if user_id == session.get('user_id'):
        flash('Không thể xóa tài khoản đang đăng nhập!', 'error')
        return redirect(url_for('admin_users'))

    conn = get_db_connection()
    target = conn.execute(
        "SELECT id, username FROM users WHERE id = ? AND role = 'admin'", (user_id,)
    ).fetchone()

    if not target:
        conn.close()
        flash('Tài khoản quản trị không tồn tại!', 'error')
        return redirect(url_for('admin_users'))

    total_admins = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    if total_admins <= 1:
        conn.close()
        flash('Phải còn ít nhất một tài khoản quản trị!', 'error')
        return redirect(url_for('admin_users'))

    conn.execute("DELETE FROM users WHERE id = ? AND role = 'admin'", (user_id,))
    conn.commit()
    conn.close()

    flash(f'Đã xóa tài khoản quản trị "{target["username"]}".', 'success')
    return redirect(url_for('admin_users'))


# Thêm cột ngày giao dự kiến + bảng lịch sử trạng thái nếu DB cũ chưa có
with app.app_context():
    _ensure_order_time_schema()


# === RUN APP ===
if __name__ == '__main__':
    app.run(debug=True)
