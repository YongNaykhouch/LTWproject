"""
Web API REST (JSON) cho hệ thống Cửa hàng Điện tử.

Mục đích (theo yêu cầu môn học):
    - Cung cấp phần Back-end thuần (không giao diện) để hệ thống khác gọi vào.
    - Đầy đủ CRUD: Create / Read / Update / Delete.
    - Dùng cho Postman hoặc cho các client viết bằng Python (xem api_client.py).

Cách đăng ký trong app.py:
    from api import api_bp
    app.register_blueprint(api_bp)

Xác thực:
    Mọi request (trừ GET công khai) cần header:
        X-API-Key: <giá trị API_KEY>
    API_KEY lấy từ biến môi trường APP_API_KEY, mặc định 'dev-api-key-2026'.

Danh sách endpoint:
    GET    /api/v1/health
    GET    /api/v1/products?category=&brand=&q=&min_price=&max_price=&page=&per_page=
    GET    /api/v1/products/<id>
    POST   /api/v1/products
    PUT    /api/v1/products/<id>
    PATCH  /api/v1/products/<id>
    DELETE /api/v1/products/<id>

    GET    /api/v1/orders?status=&q=&page=&per_page=
    GET    /api/v1/orders/<order_id>
    POST   /api/v1/orders                (tạo đơn từ danh sách items)
    PUT    /api/v1/orders/<order_id>     (cập nhật đơn)
    DELETE /api/v1/orders/<order_id>

    GET    /api/v1/order-items?order_id=
    GET    /api/v1/order-items/<id>
    POST   /api/v1/order-items
    PUT    /api/v1/order-items/<id>
    DELETE /api/v1/order-items/<id>

    GET    /api/v1/customers?q=
    GET    /api/v1/customers/<id>
    POST   /api/v1/customers
    PUT    /api/v1/customers/<id>
    DELETE /api/v1/customers/<id>

    GET    /api/v1/stats/revenue?period=day|month|year&date=YYYY-MM-DD|YYYY-MM|YYYY
"""

import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request
from product_extra_specs import parse_extra_specs, serialize_extra_specs

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

API_KEY = os.environ.get('APP_API_KEY', 'dev-api-key-2026')
# Luôn trỏ đúng file DB nằm cạnh app.py, bất kể thư mục đang chạy lệnh
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _hash(password: str) -> str:
    """Giữ cùng thuật toán với app.py để tài khoản tạo qua API đăng nhập được."""
    return hashlib.sha256(password.encode()).hexdigest()


def _json(data, status=200):
    return jsonify(data), status


def _error(message, status=400, **extra):
    payload = {'success': False, 'error': message}
    payload.update(extra)
    return jsonify(payload), status


def require_key(f):
    """Bảo vệ các endpoint ghi dữ liệu bằng API key."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('X-API-Key', '')
        if key != API_KEY:
            return _error('API key không hợp lệ hoặc thiếu header X-API-Key.', 401)
        return f(*args, **kwargs)
    return wrapper


def _row_to_dict(row):
    if row is None:
        return None
    data = dict(row)
    if 'extra_specs' in data:
        data['extra_specs'] = parse_extra_specs(data['extra_specs'])
    return data


def _restore_stock(conn, order_id):
    """Cộng lại tồn kho khi đơn bị hủy/xóa (dùng chung với app.py)."""
    items = conn.execute(
        'SELECT product_id, quantity FROM order_items WHERE order_id = ?',
        (order_id,)
    ).fetchall()
    restored = 0
    for it in items:
        if it['product_id'] is None:
            continue
        conn.execute('UPDATE products SET stock = COALESCE(stock, 0) + ? WHERE id = ?',
                     (it['quantity'], it['product_id']))
        restored += it['quantity']
    return restored


SHIPPING_DAYS = 3  # phải khớp hằng số trong app.py


def _log_order_status(conn, order_id, status):
    """Ghi lịch sử trạng thái để trang Theo dõi đơn của khách có mốc thời gian."""
    try:
        conn.execute(
            'INSERT INTO order_status_history (order_id, status) VALUES (?, ?)',
            (order_id, status)
        )
    except sqlite3.Error:
        pass  # DB cũ chưa có bảng -> bỏ qua, không làm hỏng request


def _has_column(conn, table, column):
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()]
    return column in cols


def _paging(default=20, maximum=100):
    page = request.args.get('page', 1, type=int) or 1
    per_page = request.args.get('per_page', default, type=int) or default
    page = max(page, 1)
    per_page = min(max(per_page, 1), maximum)
    return page, per_page, (page - 1) * per_page


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

@api_bp.get('/health')
def health():
    return _json({
        'success': True,
        'service': 'electronic-store-api',
        'version': '1.0',
        'time': datetime.now().isoformat(timespec='seconds'),
    })


# --------------------------------------------------------------------------
# PRODUCTS
# --------------------------------------------------------------------------

PRODUCT_WRITABLE = [
    'product_id', 'name', 'category', 'brand', 'price', 'stock', 'description',
    'image', 'cpu', 'display', 'ram', 'storage', 'gpu', 'battery', 'camera',
    'chip', 'sensor', 'water_resistance', 'ports', 'wifi', 'cooling',
    'capacity', 'type', 'cooling_tech', 'energy_rating', 'motor', 'technology',
    'warranty', 'shelves', 'power', 'speed_levels', 'control_type',
    'oscillation', 'timer', 'size', 'blade_type', 'filter', 'zones',
    'burners', 'grates', 'safety', 'ignition',
    'extra_specs',
]


@api_bp.get('/products')
def list_products():
    page, per_page, offset = _paging()

    where, params = [], []
    category = request.args.get('category', '').strip()
    brand = request.args.get('brand', '').strip()
    q = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)

    if category:
        where.append('category = ?')
        params.append(category)
    if brand:
        where.append('LOWER(IFNULL(brand, \'\')) LIKE ?')
        params.append(f'%{brand.lower()}%')
    if q:
        where.append('(LOWER(name) LIKE ? OR LOWER(IFNULL(brand, \'\')) LIKE ?)')
        params += [f'%{q.lower()}%', f'%{q.lower()}%']
    if min_price is not None:
        where.append('price >= ?')
        params.append(min_price)
    if max_price is not None:
        where.append('price <= ?')
        params.append(max_price)

    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db()
    try:
        total = conn.execute(f'SELECT COUNT(*) FROM products {where_sql}', params).fetchone()[0]
        rows = conn.execute(
            f'SELECT * FROM products {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?',
            params + [per_page, offset],
        ).fetchall()
    finally:
        conn.close()

    return _json({
        'success': True,
        'page': page,
        'per_page': per_page,
        'total': total,
        'data': [_row_to_dict(r) for r in rows],
    })


@api_bp.get('/products/<int:product_id>')
def get_product(product_id):
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return _error('Sản phẩm không tồn tại.', 404)
    return _json({'success': True, 'data': _row_to_dict(row)})


@api_bp.post('/products')
@require_key
def create_product():
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    category = (data.get('category') or '').strip()
    if not name or not category:
        return _error('Thiếu trường bắt buộc: name, category.')

    try:
        price = float(data.get('price') or 0)
        stock = int(data.get('stock') or 0)
    except (TypeError, ValueError):
        return _error('price/stock phải là số.')

    if price < 0 or stock < 0:
        return _error('price/stock không được âm.')

    values = {k: data.get(k) for k in PRODUCT_WRITABLE}
    values.update({
        'product_id': data.get('product_id') or str(uuid.uuid4())[:8].upper(),
        'name': name,
        'category': category,
        'price': price,
        'stock': stock,
    })
    try:
        values['extra_specs'] = serialize_extra_specs(
            data.get('extra_specs'), category
        )
    except (TypeError, ValueError):
        return _error('extra_specs phải là đối tượng JSON hợp lệ.')

    cols = ', '.join(values.keys())
    marks = ', '.join(['?'] * len(values))

    conn = get_db()
    try:
        cur = conn.execute(f'INSERT INTO products ({cols}) VALUES ({marks})', list(values.values()))
        conn.commit()
        new_id = cur.lastrowid
        row = conn.execute('SELECT * FROM products WHERE id = ?', (new_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        return _error(f'Vi phạm ràng buộc dữ liệu: {exc}', 409)
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã tạo sản phẩm.', 'data': _row_to_dict(row)}, 201)


@api_bp.route('/products/<int:product_id>', methods=['PUT', 'PATCH'])
@require_key
def update_product(product_id):
    data = request.get_json(silent=True) or {}
    partial = request.method == 'PATCH'

    if not partial and ('name' not in data or 'category' not in data):
        return _error('PUT yêu cầu đầy đủ name, category, price, stock.')

    updates = {k: v for k, v in data.items() if k in PRODUCT_WRITABLE}
    if not updates:
        return _error('Không có trường hợp lệ để cập nhật.')

    if 'price' in updates:
        try:
            updates['price'] = float(updates['price'])
        except (TypeError, ValueError):
            return _error('price phải là số.')
    if 'stock' in updates:
        try:
            updates['stock'] = int(updates['stock'])
        except (TypeError, ValueError):
            return _error('stock phải là số nguyên.')
    if 'extra_specs' in updates:
        category = updates.get('category')
        if category is None:
            conn = get_db()
            try:
                row = conn.execute(
                    'SELECT category FROM products WHERE id = ?', (product_id,)
                ).fetchone()
                if row is None:
                    return _error('Sản phẩm không tồn tại.', 404)
                category = row['category']
            finally:
                conn.close()
        try:
            updates['extra_specs'] = serialize_extra_specs(
                updates['extra_specs'], category
            )
        except (TypeError, ValueError):
            return _error('extra_specs phải là đối tượng JSON hợp lệ.')

    set_sql = ', '.join(f'{k} = ?' for k in updates)
    conn = get_db()
    try:
        cur = conn.execute(f'UPDATE products SET {set_sql} WHERE id = ?',
                           list(updates.values()) + [product_id])
        conn.commit()
        if cur.rowcount == 0:
            return _error('Sản phẩm không tồn tại.', 404)
        row = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã cập nhật sản phẩm.', 'data': _row_to_dict(row)})


@api_bp.delete('/products/<int:product_id>')
@require_key
def delete_product(product_id):
    conn = get_db()
    try:
        exists = conn.execute('SELECT 1 FROM products WHERE id = ?', (product_id,)).fetchone()
        if not exists:
            return _error('Sản phẩm không tồn tại.', 404)
        # Giữ lịch sử đơn: NULL hoá tham chiếu thay vì xoá order_items
        conn.execute('UPDATE order_items SET product_id = NULL WHERE product_id = ?', (product_id,))
        conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
        conn.commit()
    finally:
        conn.close()
    return _json({'success': True, 'message': f'Đã xoá sản phẩm #{product_id}.'})


# --------------------------------------------------------------------------
# ORDERS
# --------------------------------------------------------------------------

VALID_STATUS = ('pending', 'processing', 'shipped', 'completed', 'cancelled')


def _order_with_items(conn, order_id):
    order = conn.execute('''
        SELECT o.*, u.username, u.email
        FROM orders o
        LEFT JOIN users u ON u.id = o.user_id
        WHERE o.order_id = ?
    ''', (order_id,)).fetchone()
    if not order:
        return None
    items = conn.execute('''
        SELECT oi.*, p.name AS product_current_name, p.image AS product_image
        FROM order_items oi
        LEFT JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = ?
        ORDER BY oi.id
    ''', (order_id,)).fetchall()

    result = _row_to_dict(order)
    result['items'] = [_row_to_dict(i) for i in items]
    return result


@api_bp.get('/orders')
def list_orders():
    page, per_page, offset = _paging()

    where, params = [], []
    status = request.args.get('status', '').strip()
    q = request.args.get('q', '').strip()

    if status:
        if status not in VALID_STATUS:
            return _error(f'status phải là một trong: {", ".join(VALID_STATUS)}')
        where.append('o.status = ?')
        params.append(status)
    if q:
        where.append('(o.order_id LIKE ? OR u.username LIKE ? OR o.phone LIKE ? OR u.email LIKE ?)')
        like = f'%{q}%'
        params += [like, like, like, like]

    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db()
    try:
        total = conn.execute(
            f'SELECT COUNT(*) FROM orders o LEFT JOIN users u ON u.id = o.user_id {where_sql}',
            params,
        ).fetchone()[0]
        rows = conn.execute(f'''
            SELECT o.*, u.username, u.email,
                   (SELECT COALESCE(SUM(quantity), 0) FROM order_items oi
                    WHERE oi.order_id = o.order_id) AS item_count
            FROM orders o
            LEFT JOIN users u ON u.id = o.user_id
            {where_sql}
            ORDER BY o.created_at DESC
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset]).fetchall()
    finally:
        conn.close()

    return _json({
        'success': True,
        'page': page,
        'per_page': per_page,
        'total': total,
        'data': [_row_to_dict(r) for r in rows],
    })


@api_bp.get('/orders/<string:order_id>')
def get_order(order_id):
    conn = get_db()
    try:
        order = _order_with_items(conn, order_id)
    finally:
        conn.close()
    if not order:
        return _error('Đơn hàng không tồn tại.', 404)
    return _json({'success': True, 'data': order})


@api_bp.post('/orders')
@require_key
def create_order():
    data = request.get_json(silent=True) or {}

    user_id = data.get('user_id')
    address = (data.get('address') or '').strip()
    phone = (data.get('phone') or '').strip()
    items = data.get('items') or []

    if not user_id:
        return _error('Thiếu user_id.')
    if not address or not phone:
        return _error('Thiếu address hoặc phone.')
    if not isinstance(items, list) or not items:
        return _error('items phải là mảng và không được rỗng.')

    conn = get_db()
    try:
        user = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
        if not user:
            return _error('user_id không tồn tại.', 404)

        prepared, total = [], 0.0
        for idx, it in enumerate(items):
            pid = it.get('product_id')
            qty = it.get('quantity', 1)
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                return _error(f'items[{idx}].quantity phải là số nguyên.')

            if qty < 1:
                return _error(f'items[{idx}].quantity phải >= 1.')

            product = conn.execute('SELECT * FROM products WHERE id = ?', (pid,)).fetchone()
            if not product:
                return _error(f'items[{idx}]: sản phẩm id={pid} không tồn tại.', 404)
            if product['stock'] is not None and qty > product['stock']:
                return _error(
                    f'Sản phẩm "{product["name"]}" chỉ còn {product["stock"]} trong kho.', 409)

            price = product['price']
            total += price * qty
            prepared.append((product['id'], product['name'], price, qty))

        order_id = str(uuid.uuid4())[:12].upper()
        now = datetime.now()
        created_at = now.strftime('%Y-%m-%d %H:%M:%S')
        status = data.get('status') or 'pending'
        if status not in VALID_STATUS:
            return _error(f'status phải là một trong: {", ".join(VALID_STATUS)}')

        # Ngày giao dự kiến: lấy từ request, nếu không có thì ngày đặt + SHIPPING_DAYS
        expected = (data.get('expected_delivery') or '').strip()
        try:
            expected = (datetime.strptime(expected, '%Y-%m-%d').date()
                        if expected else (now + timedelta(days=SHIPPING_DAYS)).date())
        except ValueError:
            return _error('expected_delivery phải có định dạng YYYY-MM-DD.')
        expected = expected.strftime('%Y-%m-%d')

        if _has_column(conn, 'orders', 'expected_delivery'):
            conn.execute('''
                INSERT INTO orders
                (order_id, user_id, total_price, status, address, phone, created_at, expected_delivery)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, user_id, total, status, address, phone, created_at, expected))
        else:
            conn.execute('''
                INSERT INTO orders (order_id, user_id, total_price, status, address, phone, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, user_id, total, status, address, phone, created_at))
        _log_order_status(conn, order_id, status)

        for pid, name, price, qty in prepared:
            conn.execute('''
                INSERT INTO order_items (order_id, product_id, product_name, price, quantity)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, pid, name, price, qty))
            # Trừ tồn kho (không để âm)
            conn.execute('UPDATE products SET stock = MAX(COALESCE(stock, 0) - ?, 0) WHERE id = ?',
                         (qty, pid))

        conn.commit()
        order = _order_with_items(conn, order_id)
    except sqlite3.Error as exc:
        conn.rollback()
        return _error(f'Lỗi database: {exc}', 500)
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã tạo đơn hàng.', 'data': order}, 201)


@api_bp.route('/orders/<string:order_id>', methods=['PUT', 'PATCH'])
@require_key
def update_order(order_id):
    data = request.get_json(silent=True) or {}

    allowed = {'status', 'address', 'phone'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return _error('Chỉ được cập nhật: status, address, phone.')

    if 'status' in updates and updates['status'] not in VALID_STATUS:
        return _error(f'status phải là một trong: {", ".join(VALID_STATUS)}')

    conn = get_db()
    try:
        current = conn.execute('SELECT status FROM orders WHERE order_id = ?',
                               (order_id,)).fetchone()
        if not current:
            return _error('Đơn hàng không tồn tại.', 404)

        if (updates.get('status') == 'cancelled'
                and current['status'] == 'completed'):
            return _error('Đơn đã giao không thể hủy.', 409)

        set_sql = ', '.join(f'{k} = ?' for k in updates)
        conn.execute(f'UPDATE orders SET {set_sql} WHERE order_id = ?',
                     list(updates.values()) + [order_id])

        # Ghi lịch sử khi trạng thái thực sự thay đổi
        if 'status' in updates and updates['status'] != current['status']:
            _log_order_status(conn, order_id, updates['status'])

        # Hủy đơn -> trả hàng về kho
        if updates.get('status') == 'cancelled' and current['status'] != 'cancelled':
            _restore_stock(conn, order_id)

        conn.commit()
        order = _order_with_items(conn, order_id)
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã cập nhật đơn hàng.', 'data': order})


@api_bp.delete('/orders/<string:order_id>')
@require_key
def delete_order(order_id):
    conn = get_db()
    try:
        order = conn.execute('SELECT status FROM orders WHERE order_id = ?', (order_id,)).fetchone()
        if not order:
            return _error('Đơn hàng không tồn tại.', 404)

        # Đơn chưa giao -> hoàn hàng về kho trước khi xóa
        restored = 0
        if order['status'] not in ('completed', 'cancelled'):
            restored = _restore_stock(conn, order_id)

        conn.execute('DELETE FROM order_items WHERE order_id = ?', (order_id,))
        conn.execute('DELETE FROM orders WHERE order_id = ?', (order_id,))
        conn.commit()
    finally:
        conn.close()

    message = f'Đã xoá đơn {order_id} và chi tiết liên quan.'
    if restored:
        message += f' Đã hoàn {restored} sản phẩm về kho.'
    return _json({'success': True, 'message': message, 'restored_quantity': restored})


# --------------------------------------------------------------------------
# ORDER ITEMS
# --------------------------------------------------------------------------

@api_bp.get('/order-items')
def list_order_items():
    order_id = request.args.get('order_id', '').strip()
    conn = get_db()
    try:
        if order_id:
            rows = conn.execute(
                'SELECT * FROM order_items WHERE order_id = ? ORDER BY id', (order_id,)
            ).fetchall()
        else:
            page, per_page, offset = _paging()
            rows = conn.execute(
                'SELECT * FROM order_items ORDER BY id DESC LIMIT ? OFFSET ?',
                (per_page, offset),
            ).fetchall()
    finally:
        conn.close()
    return _json({'success': True, 'total': len(rows),
                  'data': [_row_to_dict(r) for r in rows]})


@api_bp.get('/order-items/<int:item_id>')
def get_order_item(item_id):
    conn = get_db()
    try:
        row = conn.execute('SELECT * FROM order_items WHERE id = ?', (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return _error('Dòng chi tiết không tồn tại.', 404)
    return _json({'success': True, 'data': _row_to_dict(row)})


@api_bp.post('/order-items')
@require_key
def create_order_item():
    data = request.get_json(silent=True) or {}
    order_id = (data.get('order_id') or '').strip()
    product_id = data.get('product_id')

    if not order_id or not product_id:
        return _error('Thiếu order_id hoặc product_id.')
    try:
        quantity = int(data.get('quantity', 1))
    except (TypeError, ValueError):
        return _error('quantity phải là số nguyên.')
    if quantity < 1:
        return _error('quantity phải >= 1.')

    conn = get_db()
    try:
        if not conn.execute('SELECT 1 FROM orders WHERE order_id = ?', (order_id,)).fetchone():
            return _error('order_id không tồn tại.', 404)
        product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
        if not product:
            return _error('product_id không tồn tại.', 404)

        price = data.get('price')
        price = float(price) if price is not None else float(product['price'])
        name = data.get('product_name') or product['name']

        cur = conn.execute('''
            INSERT INTO order_items (order_id, product_id, product_name, price, quantity)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, product_id, name, price, quantity))

        # Cập nhật lại tổng tiền đơn
        conn.execute('''
            UPDATE orders SET total_price = (
                SELECT COALESCE(SUM(price * quantity), 0) FROM order_items WHERE order_id = ?
            ) WHERE order_id = ?
        ''', (order_id, order_id))

        conn.commit()
        row = conn.execute('SELECT * FROM order_items WHERE id = ?', (cur.lastrowid,)).fetchone()
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã thêm dòng chi tiết.',
                  'data': _row_to_dict(row)}, 201)


@api_bp.route('/order-items/<int:item_id>', methods=['PUT', 'PATCH'])
@require_key
def update_order_item(item_id):
    data = request.get_json(silent=True) or {}
    updates = {k: v for k, v in data.items()
               if k in ('product_name', 'price', 'quantity')}
    if not updates:
        return _error('Chỉ được cập nhật: product_name, price, quantity.')

    if 'quantity' in updates:
        try:
            updates['quantity'] = int(updates['quantity'])
        except (TypeError, ValueError):
            return _error('quantity phải là số nguyên.')
        if updates['quantity'] < 1:
            return _error('quantity phải >= 1.')
    if 'price' in updates:
        try:
            updates['price'] = float(updates['price'])
        except (TypeError, ValueError):
            return _error('price phải là số.')

    set_sql = ', '.join(f'{k} = ?' for k in updates)
    conn = get_db()
    try:
        cur = conn.execute(f'UPDATE order_items SET {set_sql} WHERE id = ?',
                           list(updates.values()) + [item_id])
        if cur.rowcount == 0:
            return _error('Dòng chi tiết không tồn tại.', 404)

        item = conn.execute('SELECT order_id FROM order_items WHERE id = ?', (item_id,)).fetchone()
        conn.execute('''
            UPDATE orders SET total_price = (
                SELECT COALESCE(SUM(price * quantity), 0) FROM order_items WHERE order_id = ?
            ) WHERE order_id = ?
        ''', (item['order_id'], item['order_id']))

        conn.commit()
        row = conn.execute('SELECT * FROM order_items WHERE id = ?', (item_id,)).fetchone()
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã cập nhật dòng chi tiết.',
                  'data': _row_to_dict(row)})


@api_bp.delete('/order-items/<int:item_id>')
@require_key
def delete_order_item(item_id):
    conn = get_db()
    try:
        item = conn.execute('SELECT order_id FROM order_items WHERE id = ?', (item_id,)).fetchone()
        if not item:
            return _error('Dòng chi tiết không tồn tại.', 404)

        conn.execute('DELETE FROM order_items WHERE id = ?', (item_id,))
        conn.execute('''
            UPDATE orders SET total_price = (
                SELECT COALESCE(SUM(price * quantity), 0) FROM order_items WHERE order_id = ?
            ) WHERE order_id = ?
        ''', (item['order_id'], item['order_id']))
        conn.commit()
    finally:
        conn.close()

    return _json({'success': True, 'message': f'Đã xoá dòng chi tiết #{item_id}.'})


# --------------------------------------------------------------------------
# CUSTOMERS
# --------------------------------------------------------------------------

@api_bp.get('/customers')
def list_customers():
    page, per_page, offset = _paging()
    q = request.args.get('q', '').strip()

    where, params = ["role = 'user'"], []
    if q:
        where.append('(username LIKE ? OR email LIKE ? OR phone LIKE ?)')
        like = f'%{q}%'
        params += [like, like, like]

    where_sql = 'WHERE ' + ' AND '.join(where)

    conn = get_db()
    try:
        total = conn.execute(f'SELECT COUNT(*) FROM users {where_sql}', params).fetchone()[0]
        rows = conn.execute(f'''
            SELECT u.id, u.username, u.email, u.phone, u.address, u.avatar,
                   (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) AS order_count,
                   (SELECT COALESCE(SUM(total_price), 0) FROM orders o
                    WHERE o.user_id = u.id AND o.status = 'completed') AS total_spent
            FROM users u
            {where_sql}
            ORDER BY u.id DESC
            LIMIT ? OFFSET ?
        ''', params + [per_page, offset]).fetchall()
    finally:
        conn.close()

    return _json({'success': True, 'page': page, 'per_page': per_page,
                  'total': total, 'data': [_row_to_dict(r) for r in rows]})


@api_bp.get('/customers/<int:customer_id>')
def get_customer(customer_id):
    conn = get_db()
    try:
        row = conn.execute('''
            SELECT id, username, email, phone, address, avatar, dob
            FROM users WHERE id = ? AND role = 'user'
        ''', (customer_id,)).fetchone()
        if not row:
            return _error('Khách hàng không tồn tại.', 404)
        orders = conn.execute('''
            SELECT order_id, total_price, status, created_at
            FROM orders WHERE user_id = ? ORDER BY created_at DESC
        ''', (customer_id,)).fetchall()
    finally:
        conn.close()

    data = _row_to_dict(row)
    data['orders'] = [_row_to_dict(o) for o in orders]
    return _json({'success': True, 'data': data})


@api_bp.post('/customers')
@require_key
def create_customer():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    email = (data.get('email') or '').strip().lower()

    if not username or not email:
        return _error('Thiếu username hoặc email.')
    if username.lower() == 'admin':
        return _error("Username 'admin' được dành riêng.")

    conn = get_db()
    try:
        cur = conn.execute('''
            INSERT INTO users (username, email, phone, password, address, role)
            VALUES (?, ?, ?, ?, ?, 'user')
        ''', (username, email,
              (data.get('phone') or '').strip(),
              _hash(data.get('password') or '123456'),
              (data.get('address') or '').strip()))
        conn.commit()
        row = conn.execute(
            'SELECT id, username, email, phone, address FROM users WHERE id = ?',
            (cur.lastrowid,)).fetchone()
    except sqlite3.IntegrityError:
        return _error('Username hoặc email đã tồn tại.', 409)
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã tạo khách hàng.',
                  'data': _row_to_dict(row)}, 201)


@api_bp.route('/customers/<int:customer_id>', methods=['PUT', 'PATCH'])
@require_key
def update_customer(customer_id):
    data = request.get_json(silent=True) or {}
    allowed = ('username', 'email', 'phone', 'address', 'password')
    updates = {k: v for k, v in data.items() if k in allowed}

    if 'password' in updates:
        updates['password'] = _hash(updates['password'])
    if not updates:
        return _error('Không có trường hợp lệ để cập nhật.')

    set_sql = ', '.join(f'{k} = ?' for k in updates)
    conn = get_db()
    try:
        cur = conn.execute(f"UPDATE users SET {set_sql} WHERE id = ? AND role = 'user'",
                           list(updates.values()) + [customer_id])
        conn.commit()
        if cur.rowcount == 0:
            return _error('Khách hàng không tồn tại.', 404)
        row = conn.execute(
            'SELECT id, username, email, phone, address FROM users WHERE id = ?',
            (customer_id,)).fetchone()
    except sqlite3.IntegrityError:
        return _error('Username hoặc email đã tồn tại.', 409)
    finally:
        conn.close()

    return _json({'success': True, 'message': 'Đã cập nhật khách hàng.',
                  'data': _row_to_dict(row)})


@api_bp.delete('/customers/<int:customer_id>')
@require_key
def delete_customer(customer_id):
    conn = get_db()
    try:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE id = ? AND role = 'user'", (customer_id,)).fetchone()
        if not exists:
            return _error('Khách hàng không tồn tại.', 404)

        conn.execute('''DELETE FROM order_items WHERE order_id IN
                        (SELECT order_id FROM orders WHERE user_id = ?)''', (customer_id,))
        conn.execute('DELETE FROM orders WHERE user_id = ?', (customer_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (customer_id,))
        conn.commit()
    finally:
        conn.close()

    return _json({'success': True, 'message': f'Đã xoá khách hàng #{customer_id} và đơn liên quan.'})


# --------------------------------------------------------------------------
# STATS
# --------------------------------------------------------------------------

@api_bp.get('/stats/sales')
def stats_sales():
    """Doanh thu bán được: mọi đơn trừ đơn hủy (dùng cho báo cáo Lập trình Web)."""
    conn = get_db()
    try:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status != 'cancelled' THEN total_price ELSE 0 END), 0) AS sold_revenue,
                COALESCE(SUM(CASE WHEN status = 'completed'  THEN total_price ELSE 0 END), 0) AS realized_revenue,
                COUNT(CASE WHEN status != 'cancelled' THEN 1 END) AS sold_orders,
                COUNT(CASE WHEN status = 'cancelled'  THEN 1 END) AS cancelled_orders
            FROM orders
        """).fetchone()

        by_status = conn.execute("""
            SELECT status,
                   COUNT(*) AS orders,
                   COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            GROUP BY status
            ORDER BY orders DESC
        """).fetchall()
    finally:
        conn.close()

    return _json({
        'success': True,
        'sold_revenue': row['sold_revenue'],
        'realized_revenue': row['realized_revenue'],
        'pending_revenue': row['sold_revenue'] - row['realized_revenue'],
        'sold_orders': row['sold_orders'],
        'cancelled_orders': row['cancelled_orders'],
        'by_status': [_row_to_dict(r) for r in by_status],
    })


@api_bp.get('/stats/low-stock')
def stats_low_stock():
    """Sản phẩm sắp hết hàng — phục vụ cảnh báo tồn kho."""
    threshold = request.args.get('threshold', 5, type=int) or 5

    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT id, name, category, brand, price, stock
            FROM products
            WHERE COALESCE(stock, 0) <= ?
            ORDER BY COALESCE(stock, 0) ASC, id DESC
        """, (threshold,)).fetchall()
    finally:
        conn.close()

    return _json({
        'success': True,
        'threshold': threshold,
        'total': len(rows),
        'data': [_row_to_dict(r) for r in rows],
    })


@api_bp.get('/stats/revenue')
def stats_revenue():
    period = request.args.get('period', 'month')
    raw = request.args.get('date', '').strip()

    today = datetime.now().date()
    try:
        if period == 'day':
            start = end = datetime.strptime(raw, '%Y-%m-%d').date() if raw else today
        elif period == 'year':
            year = int(raw) if raw else today.year
            start, end = datetime(year, 1, 1).date(), datetime(year, 12, 31).date()
        else:
            period = 'month'
            dt = datetime.strptime(raw, '%Y-%m').date() if raw else today.replace(day=1)
            start = dt.replace(day=1)
            end = (datetime(start.year + (start.month == 12),
                            (start.month % 12) + 1, 1) - timedelta(days=1)).date()
    except ValueError:
        return _error('date không đúng định dạng cho period đã chọn.')

    conn = get_db()
    try:
        summary = conn.execute('''
            SELECT COUNT(*) AS orders, COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE status = 'completed' AND DATE(created_at) BETWEEN ? AND ?
        ''', (start.isoformat(), end.isoformat())).fetchone()

        rows = conn.execute('''
            SELECT DATE(created_at) AS day,
                   COUNT(*) AS orders,
                   COALESCE(SUM(total_price), 0) AS revenue
            FROM orders
            WHERE status = 'completed' AND DATE(created_at) BETWEEN ? AND ?
            GROUP BY DATE(created_at)
            ORDER BY day
        ''', (start.isoformat(), end.isoformat())).fetchall()
    finally:
        conn.close()

    return _json({
        'success': True,
        'period': period,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'total_orders': summary['orders'],
        'total_revenue': summary['revenue'],
        'by_day': [_row_to_dict(r) for r in rows],
    })
