import html
import re
import sqlite3
import unicodedata
from datetime import datetime

from flask import url_for
from product_extra_specs import EXTRA_SPEC_FIELDS, EXTRA_SPEC_LABELS, parse_extra_specs

# --------------------------------------------------------------------------
# Cấu hình chung
# --------------------------------------------------------------------------
CATEGORY_LABELS = {
    'dienthoai': 'Điện thoại',
    'laptop': 'Laptop',
    'dongho': 'Đồng hồ thông minh',
    'maytinhbanpc': 'Máy tính bàn',
    'mayanh': 'Máy ảnh',
    'tulanh': 'Tủ lạnh',
    'quat': 'Quạt',
    'maygiatsay': 'Máy giặt & sấy',
    'beptu': 'Bếp từ',
    'dieuhoa': 'Điều hoà',
    'tainghe': 'Tai nghe',
}

# Từ khoá -> danh mục
CATEGORY_KEYWORDS = {
    'dienthoai': ['dien thoai', 'dienthoai', 'phone', 'smartphone', 'di dong'],
    'laptop': ['laptop', 'may tinh xach tay', 'notebook', 'macbook'],
    'maytinhbanpc': ['may tinh ban', 'pc', 'desktop', 'may tinh de ban'],
    'dongho': ['dong ho', 'smartwatch', 'watch'],
    'mayanh': ['may anh', 'camera', 'may chup hinh'],
    'tulanh': ['tu lanh', 'fridge', 'refrigerator'],
    'quat': ['quat', 'fan', 'quat dien'],
    'maygiatsay': ['may giat', 'may say', 'giat say', 'washing'],
    'beptu': ['bep tu', 'bep dien', 'bep'],
    'dieuhoa': ['dieu hoa', 'may lanh', 'dieu hoa nhiet do'],
    'tainghe': ['tai nghe', 'headphone', 'earphone', 'airpod'],
}

# Tên hãng: câu có tên hãng -> tìm theo hãng, KHÔNG coi là tên danh mục
BRAND_KEYWORDS = [
    'iphone', 'samsung', 'oppo', 'xiaomi', 'realme', 'vivo', 'nokia',
    'asus', 'acer', 'dell', 'hp', 'lenovo', 'msi', 'macbook', 'apple',
    'panasonic', 'toshiba', 'aqua', 'electrolux', 'lg', 'sharp',
    'sony', 'jbl', 'logitech', 'casio', 'garmin',
]

SHOP_INFO = (
    '<b>Cửa hàng Điện tử</b><br>'
    'Hotline: <b>0917873816</b><br>'
    'Email: yongnaykhouch1@gmail.com<br>'
    'Hỗ trợ trực tuyến 24/7 — kể cả ngày lễ'
)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp từ khoá dễ hơn."""
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
    # đ -> d
    return text.replace('đ', 'd')


def _fmt_money(value) -> str:
    try:
        return '{:,.0f} ₫'.format(float(value))
    except (TypeError, ValueError):
        return '0 ₫'


def _strip_decorative_icons(value: str) -> str:
    """Keep chatbot replies readable by removing decorative emoji and icon markup."""
    value = re.sub(r'<i\b[^>]*>.*?</i>', '', value, flags=re.IGNORECASE | re.DOTALL)
    return ''.join(
        char for char in value
        if unicodedata.category(char) != 'So' and char not in '\ufe0e\ufe0f\u200d'
    )


def _clean_bot_result(result: dict) -> dict:
    reply = result.get('reply')
    if isinstance(reply, str):
        result['reply'] = _strip_decorative_icons(reply)
    return result


# Cụm từ chứa tên danh mục nhưng KHÔNG phải câu hỏi về danh mục đó.
# Ví dụ: "số điện thoại" không phải "điện thoại".
CATEGORY_FALSE_POSITIVES = {
    'so dien thoai', 'sdt', 'lien he', 'hotline', 'dia chi',
    'so dt', 'email', 'gio mo cua',
}


def _has_phrase(normalized: str, phrase: str) -> bool:
    """So khớp theo ranh giới từ để 'pc' không khớp trong 'laptop'."""
    return re.search(r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])',
                     normalized) is not None


def _detect_category(normalized: str):
    """Trả về (category, keyword) nếu câu hỏi nhắc tới một danh mục."""
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if _has_phrase(normalized, kw):
                return category, kw
    return None, None


def _detect_brand(normalized: str):
    """Trả về tên hãng xuất hiện trong câu (nếu có)."""
    for brand in BRAND_KEYWORDS:
        if _has_phrase(normalized, brand):
            return brand
    return None


# Hãng gợi ý danh mục khi câu không nói rõ (vd: "iphone" -> điện thoại)
BRAND_DEFAULT_CATEGORY = {
    'iphone': 'dienthoai',
    'samsung': None,        # Samsung bán cả đồng hồ, tủ lạnh... -> không gán
    'macbook': 'laptop',
    'airpod': 'tainghe',
    'xiaomi': 'dienthoai',
    'oppo': 'dienthoai',
    'realme': 'dienthoai',
    'vivo': 'dienthoai',
    'nokia': 'dienthoai',
}


def _extract_budget(normalized: str):
    """
    Đọc ngân sách từ câu kiểu:
      "dưới 10 triệu", "tầm 15tr", "khoảng 5.000.000", "trên 20 triệu"
    Trả về (min_price, max_price) hoặc None.
    """
    def _is_min(n):
        # dùng ranh giới từ: tránh "hon" khớp bên trong "iphon(e)"
        return any(_has_phrase(n, w) for w in ('tren', 'hon', 'toi thieu', 'it nhat'))

    # 12 triệu / 12tr / 12 chai
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(trieu|tr|chai|cu)\b', normalized)
    if m:
        amount = float(m.group(1).replace(',', '.')) * 1_000_000
        return (amount, None) if _is_min(normalized) else (0, amount)

    # 5.000.000 / 5000000
    m = re.search(r'(\d[\d.,]{5,})', normalized)
    if m:
        amount = float(re.sub(r'[.,]', '', m.group(1)))
        return (amount, None) if _is_min(normalized) else (0, amount)
    return None


def _search_products(conn, keyword=None, category=None, min_price=None,
                     max_price=None, limit=5):
    sql = """
        SELECT id, name, price, category, brand
        FROM products
        WHERE 1 = 1
    """
    params = []
    if category:
        sql += " AND category = ?"
        params.append(category)
    if keyword:
        sql += """ AND (
            LOWER(name) LIKE ? OR LOWER(IFNULL(brand, '')) LIKE ?
        )"""
        params += ['%{}%'.format(keyword.lower())] * 2
    if min_price is not None:
        sql += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        sql += " AND price <= ?"
        params.append(max_price)

    sql += " ORDER BY price ASC LIMIT ?"
    params.append(limit)

    return conn.execute(sql, params).fetchall()


EXTRA_SPEC_QUERY_TERMS = {
    'network_support': ('5g', '4g', 'mang di dong', 'ho tro mang'),
    'fast_charging': ('sac nhanh',),
    'charger_included': ('cu sac', 'sac kem', 'sac trong hop', 'bo sac'),
    'dust_water_resistance': ('chong nuoc', 'khang nuoc', 'khang bui', 'ip68'),
    'data_transfer_service': ('chuyen du lieu', 'chuyen data'),
    'assembled': ('lap rap san', 'tinh trang lap rap'),
    'operating_system': ('he dieu hanh', 'windows', 'macos'),
    'power_supply': ('nguon may', 'bo nguon', 'psu'),
    'case_fan_count': ('quat di kem', 'quat case'),
    'water_cooling': ('tan nhiet nuoc', 'tan nhiet bang nuoc'),
    'dimensions': ('kich thuoc',),
    'auto_ice': ('tu dong lam da', 'lam da tu dong', 'da tu dong'),
    'external_water_dispenser': ('lay nuoc ben ngoai', 'voi nuoc ben ngoai'),
    'noise_level': ('do on', 'tieng on'),
    'surface_material': ('chat lieu mat bep', 'mat bep lam bang'),
    'cookware_compatibility': ('noi tuong thich', 'loai noi', 'noi day tu'),
    'safety_features': ('tinh nang an toan', 'tinh nang bao ve'),
    'child_lock': ('khoa tre em',),
    'installation_service': ('dich vu lap dat', 'ho tro lap dat'),
    'watch_type': ('loai dong ho', 'dong ho co', 'dong ho quartz', 'smartwatch'),
    'esim_support': ('esim',),
    'interchangeable_band': ('day deo thay the', 'day deo thao roi'),
    'natural_wind': ('gio tu nhien',),
    'adjustable_height': ('chieu cao', 'dieu chinh do cao'),
    'easy_cleaning': ('thao lap de ve sinh', 'de ve sinh'),
    'weight': ('trong luong', 'nang bao nhieu'),
    'anti_glare': ('chong loa', 'man hinh chong loa'),
    'keyboard_backlight': ('den nen ban phim', 'ban phim co den'),
    'upgrade_options': ('kha nang nang cap', 'nang cap ram', 'nang cap o cung'),
    'office_software_setup': ('cai phan mem van phong', 'cai office'),
    'drying_function': ('chuc nang say', 'co say khong', 'say quan ao'),
    'hot_water_wash': ('giat nuoc nong', 'nuoc nong'),
    'drum_cleaning': ('tu ve sinh long giat', 've sinh long giat'),
}


def _answer_extra_spec_question(conn, normalized, category=None):
    """Answer only product-spec questions backed by saved, category-valid data."""
    requested_keys = [
        key for key, terms in EXTRA_SPEC_QUERY_TERMS.items()
        if any(_has_phrase(normalized, term) for term in terms)
    ]
    if not requested_keys:
        return None

    products = conn.execute(
        'SELECT id, name, category, extra_specs FROM products'
    ).fetchall()
    matches = [
        product for product in products
        if _strip_accents(product['name']).strip() in normalized
    ]

    if not matches:
        if category:
            category_label = CATEGORY_LABELS.get(category, 'sản phẩm')
            prompt = (
                'Bạn đang hỏi thông số của {}. Bạn cho tôi biết tên hoặc model '
                'sản phẩm cụ thể để tra cứu chính xác nhé.'.format(category_label)
            )
            links = [{'label': 'Xem danh mục ' + category_label,
                      'url': url_for('category_products', category=category)}]
        else:
            prompt = (
                'Bạn cho tôi biết tên hoặc model sản phẩm cần tra cứu thông số '
                'để tôi kiểm tra chính xác nhé.'
            )
            links = [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}]
        return {'reply': prompt, 'links': links}

    normalized_names = {
        _strip_accents(row['name']).strip() for row in matches
    }
    if len(normalized_names) != 1:
        return {
            'reply': 'Tôi tìm thấy nhiều sản phẩm phù hợp. Bạn vui lòng gửi tên đầy đủ '
                     'hoặc model cụ thể để tránh tra nhầm thông số.',
            'links': [{'label': 'Xem danh mục ' + CATEGORY_LABELS.get(
                category or matches[0]['category'], 'sản phẩm'
            ), 'url': url_for(
                'category_products', category=category or matches[0]['category']
            )}],
        }

    product_categories = {row['category'] for row in matches}
    if len(product_categories) != 1:
        return {
            'reply': 'Tôi tìm thấy nhiều sản phẩm phù hợp. Bạn vui lòng gửi tên đầy đủ '
                     'hoặc model cụ thể để tránh tra nhầm thông số.',
            'links': [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}],
        }

    product_category = next(iter(product_categories))
    allowed_keys = {
        key for key, _label, _placeholder
        in EXTRA_SPEC_FIELDS.get(product_category, [])
    }
    relevant_keys = [key for key in requested_keys if key in allowed_keys]
    product_name = matches[0]['name'].strip()
    product_specs = [parse_extra_specs(row['extra_specs']) for row in matches]
    lines = ['Thông tin đã xác nhận cho <b>{}</b>:'.format(html.escape(product_name))]
    missing_labels = []
    for key in relevant_keys:
        values = {specs.get(key) for specs in product_specs}
        label = EXTRA_SPEC_LABELS[key]
        if len(values) == 1 and None not in values:
            lines.append('<b>{}</b>: {}'.format(
                html.escape(label), html.escape(next(iter(values)))
            ))
        else:
            missing_labels.append(label)

    if not relevant_keys:
        missing_labels = [
            EXTRA_SPEC_LABELS[key] for key in requested_keys
        ]
    if missing_labels:
        lines.append(
            'Chưa có thông tin đã xác minh về {} trong dữ liệu cửa hàng.'.format(
                ' và '.join(html.escape(label.lower()) for label in missing_labels)
            )
        )
    return {
        'reply': '<br>'.join(lines),
        'links': [{
            'label': 'Xem sản phẩm',
            'url': url_for('product_detail', product_id=matches[0]['id']),
        }],
    }


# --------------------------------------------------------------------------
# Các "skill" của bot
# --------------------------------------------------------------------------

def _answer_greeting():
    return {
        'reply': (
            'Xin chào, tôi là trợ lý trực tuyến của <b>Cửa hàng Điện tử</b>.<br>'
            'Tôi có thể hỗ trợ tìm sản phẩm theo danh mục hoặc ngân sách, '
            'tra cứu đơn hàng và giải đáp chính sách mua hàng.'
        )
    }


def _answer_budget(conn, category, budget):
    min_price, max_price = budget
    rows = _search_products(conn, category=category, min_price=min_price,
                            max_price=max_price, limit=5)
    cat_label = CATEGORY_LABELS.get(category, 'sản phẩm')
    scope = 'dưới {}'.format(_fmt_money(max_price)) if max_price else 'trên {}'.format(_fmt_money(min_price))

    if not rows:
        links = ([{'label': 'Xem tất cả ' + cat_label,
                   'url': url_for('category_products', category=category)}]
                 if category else [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}])

        # Gợi ý sản phẩm rẻ nhất cùng danh mục để khách không bị "hụt"
        nearest = _search_products(conn, category=category, limit=1)[:1]
        reply = 'Mình chưa tìm thấy {} nào {} trong kho ạ.'.format(cat_label.lower(), scope)
        if nearest:
            reply += '<br>Sản phẩm gần nhất cùng loại: <b>{}</b> — {}'.format(
                html.escape(nearest[0]['name']), _fmt_money(nearest[0]['price']))
        reply += '<br>Bạn có thể thử một mức ngân sách khác hoặc xem toàn bộ danh mục.'
        return {'reply': reply, 'links': links}

    lines = ['Mình gợi ý cho bạn các <b>{}</b> {}:'.format(cat_label.lower(), scope)]
    for r in rows:
        lines.append('• {} — <span class="text-danger fw-bold">{}</span>'.format(
            html.escape(r['name']), _fmt_money(r['price'])))
    links = [{'label': 'Đặt hàng', 'url': url_for('view_cart')}]
    if category:
        links.insert(0, {'label': 'Xem danh mục ' + cat_label,
                         'url': url_for('category_products', category=category)})
    return {
        'reply': '<br>'.join(lines),
        'links': links,
    }


def _answer_category(conn, category):
    cat_label = CATEGORY_LABELS.get(category, 'Sản phẩm')
    rows = _search_products(conn, category=category, limit=5)
    if not rows:
        return {
            'reply': 'Hiện kho chưa có sản phẩm nào trong mục <b>{}</b>.'.format(cat_label),
            'links': [{'label': 'Xem danh mục khác', 'url': url_for('index')}],
        }

    total = conn.execute(
        'SELECT COUNT(*) FROM products WHERE category = ?', (category,)
    ).fetchone()[0]
    lines = ['<b>{}</b> hiện có {} sản phẩm. Một số lựa chọn:'.format(cat_label, total)]
    for r in rows:
        lines.append('• {} — <span class="text-danger fw-bold">{}</span>'.format(
            html.escape(r['name']), _fmt_money(r['price'])))
    if total > len(rows):
        lines.append('<br>Đang hiển thị {} sản phẩm đầu tiên.'.format(len(rows)))
    lines.append('<br>Cho tôi biết ngân sách dự kiến để lọc sản phẩm phù hợp hơn.')
    return {
        'reply': '<br>'.join(lines),
        'links': [{'label': 'Xem tất cả ' + cat_label, 'url': url_for('category_products', category=category)}],
    }


def _answer_product_search(conn, keyword, display=None):
    """keyword: từ khoá đã chuẩn hoá để query; display: bản đã escape để hiển thị."""
    display = display or keyword
    rows = _search_products(conn, keyword=keyword, limit=5)
    if not rows:
        return {
            'reply': 'Tôi chưa tìm thấy sản phẩm khớp với "<b>{}</b>". '
                         'Bạn có thể thử tên hãng, model hoặc danh mục (ví dụ: <i>iPhone</i>, <i>laptop Asus</i>).'.format(display),
            'links': [{'label': 'Tìm kiếm nâng cao', 'url': url_for('search', q=keyword)}],
            'not_found': True,
        }
    lines = ['Các sản phẩm khớp với "<b>{}</b>":'.format(display)]
    for r in rows:
        lines.append('• {} — <span class="text-danger fw-bold">{}</span>'.format(
            html.escape(r['name']), _fmt_money(r['price'])))
    return {
        'reply': '<br>'.join(lines),
        'links': [{'label': 'Xem kết quả tìm kiếm', 'url': url_for('search', q=keyword)}],
    }


def _answer_order(conn, order_id=None):
    if not order_id:
        return {
            'reply': 'Để kiểm tra đơn hàng, bạn cho mình mã đơn (8 ký tự đầu, ví dụ: <i>a1b2c3d4</i>) nhé. '
                     'Mã đơn nằm trong email xác nhận hoặc trang <b>Hồ sơ → Đơn hàng của tôi</b>.',
            'links': [{'label': 'Đơn hàng của tôi', 'url': url_for('profile')}],
        }

    row = conn.execute(
        """
        SELECT o.order_id, o.total_price, o.status, o.created_at, u.username
        FROM orders o LEFT JOIN users u ON o.user_id = u.id
        WHERE LOWER(o.order_id) LIKE ?
        """,
        ('%{}%'.format(order_id.lower()),),
    ).fetchone()

    if not row:
        return {
            'reply': 'Mình không tìm thấy đơn hàng có mã "<b>{}</b>". Bạn kiểm tra lại giúp mình nhé.'.format(order_id),
            'links': [{'label': 'Đơn hàng của tôi', 'url': url_for('profile')}],
        }

    status_map = {
        'pending': 'Chờ xử lý',
        'processing': 'Đang xử lý',
        'shipped': 'Đang giao',
        'delivered': 'Đã giao',
        'completed': 'Đã giao',
        'cancelled': 'Đã hủy',
    }
    status = status_map.get((row['status'] or 'pending').lower(), row['status'])

    reply = (
        'Đơn hàng <b>#{}</b><br>'
        'Khách hàng: {}<br>'
        'Trạng thái: {}<br>'
        'Tổng tiền: <span class="text-danger fw-bold">{}</span><br>'
        'Ngày đặt: {}'
    ).format(
        row['order_id'][:8],
        row['username'] or '—',
        status,
        _fmt_money(row['total_price']),
        (row['created_at'] or '')[:16],
    )
    return {
        'reply': reply,
        'links': [{'label': 'Xem chi tiết đơn', 'url': url_for('profile')}],
    }


def _answer_policy(normalized):
    if any(k in normalized for k in ['bao hanh', 'warranty']):
        return {'reply':         '<b>Chính sách bảo hành</b><br>'
                         '• 12 tháng cho các sản phẩm điện tử, 24 tháng cho tủ lạnh & máy giặt.<br>'
                         '• 1 đổi 1 trong 7 ngày nếu lỗi do nhà sản xuất.<br>'
                         '• Hỗ trợ bảo hành tại cửa hàng, miễn phí kiểm tra.'}
    if any(k in normalized for k in ['doi tra', 'hoan tien', 'refund', 'tra hang']):
        return {'reply':         '<b>Chính sách đổi trả</b><br>'
                         '• Đổi trong 7 ngày với sản phẩm còn đủ hộp/phụ kiện.<br>'
                         '• Hoàn tiền 100% nếu sản phẩm lỗi kỹ thuật.<br>'
                         '• Vui lòng giữ hoá đơn khi đổi trả.'}
    if any(k in normalized for k in ['giao hang', 'ship', 'van chuyen', 'phi giao']):
        return {'reply':         '<b>Giao hàng</b><br>'
                         '• Nội thành: 2–4 giờ, phí 20.000 ₫.<br>'
                         '• Ngoại thành: 1–2 ngày, phí 35.000 ₫.<br>'
                         '• <b>Miễn phí ship</b> cho đơn từ 2.000.000 ₫.'}
    # Thanh toán & trả góp được xử lý ở nhóm mở rộng bên dưới
    # (_answer_payment_methods / _answer_installment) để trả lời chi tiết hơn.
    return None


def _answer_contact():
    return {'reply': SHOP_INFO}


# ==========================================================================
# CAC NHOM CAU HOI MO RONG (deu doc du lieu that tu DB)
# ==========================================================================

def _answer_cheapest(conn, category=None):
    """Sản phẩm RẺ NHẤT (theo danh mục nếu có)."""
    where = 'WHERE COALESCE(stock, 0) > 0'
    params = []
    if category:
        where += ' AND category = ?'
        params.append(category)
    rows = conn.execute(
        f'SELECT id, name, price, stock, category FROM products {where} '
        f'ORDER BY price ASC LIMIT 3', params).fetchall()

    label = CATEGORY_LABELS.get(category, 'sản phẩm') if category else 'sản phẩm'
    if not rows:
        return {'reply': f'Hiện chưa có {label} nào còn hàng.',
            'links': [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}]}

    lines = [f'<b>{label.capitalize()} có giá thấp nhất</b> (còn hàng):']
    for i, r in enumerate(rows, 1):
        product_url = url_for('product_detail', product_id=r['id'])
        lines.append(f'{i}. <a class="cb-product-link" href="{product_url}">'
                     f'{html.escape(r["name"])}</a> — '
                     f'<span class="text-danger fw-bold">{_fmt_money(r["price"])}</span> '
                     f'<small class="text-muted">(còn {r["stock"]})</small>')
    return {'reply': '<br>'.join(lines),
            'links': [{'label': 'Xem danh mục', 'url': url_for('category_products', category=category)}]
                     if category else [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}]}


def _answer_expensive(conn, category=None):
    """Sản phẩm CAO CẤP / đắt nhất."""
    where = 'WHERE 1=1'
    params = []
    if category:
        where += ' AND category = ?'
        params.append(category)
    rows = conn.execute(
        f'SELECT name, price, stock FROM products {where} ORDER BY price DESC LIMIT 3',
        params).fetchall()

    label = CATEGORY_LABELS.get(category, 'sản phẩm') if category else 'sản phẩm'
    if not rows:
        return {'reply': 'Kho hiện chưa có sản phẩm nào.'}

    lines = [f'<b>{label.capitalize()} có giá cao nhất</b>:']
    for i, r in enumerate(rows, 1):
        lines.append(f'{i}. {html.escape(r["name"])} — '
                     f'<span class="text-danger fw-bold">{_fmt_money(r["price"])}</span>')
    return {'reply': '<br>'.join(lines)}


def _answer_compare(conn, first_kw, second_kw):
    """So sánh 2 sản phẩm theo thông số chính."""
    def _pick(kw, category=None):
        category_filter = ' AND category = ?' if category else ''
        params = [f'%{kw}%']
        if category:
            params.append(category)
        return conn.execute(
            'SELECT * FROM products WHERE LOWER(name) LIKE ?' + category_filter
            + ' ORDER BY price LIMIT 1',
            params).fetchone()

    a = _pick(first_kw)
    b = _pick(second_kw, a['category']) if a else None
    if not b:
        b = _pick(second_kw)
    if not a or not b:
        return {'reply': 'Mình chưa tìm thấy đủ 2 sản phẩm để so sánh. '
                         'Bạn ghi rõ tên, ví dụ: <i>so sánh iphone và samsung</i>.'}

    fields = [('Giá', 'price', True), ('CPU', 'cpu', False), ('RAM', 'ram', False),
              ('Bộ nhớ', 'storage', False), ('Pin', 'battery', False),
              ('Camera', 'camera', False), ('Màn hình', 'display', False)]

    def val(p, key, money):
        v = p[key]
        if money:
            return _fmt_money(v)
        return html.escape(str(v)) if v else '—'

    lines = [f'<b>So sánh</b>: {html.escape(a["name"])} <b>và</b> {html.escape(b["name"])}', '<br>']
    for label, key, money in fields:
        va, vb = val(a, key, money), val(b, key, money)
        if va == '—' and vb == '—':
            continue
        lines.append(f'<b>{label}</b>: {va} &nbsp;|&nbsp; {vb}')

    cheaper = a if a['price'] <= b['price'] else b
    lines.append(f'<br>Giá thấp hơn: <b>{html.escape(cheaper["name"])}</b>')
    return {'reply': '<br>'.join(lines)}


def _answer_stock_status(conn, keyword=None, category=None):
    """Kiểm tra còn hàng / hết hàng."""
    # Nếu từ khoá chính là tên danh mục ("laptop", "tulanh") -> hiểu là lọc theo danh mục
    if keyword:
        cat_from_kw, _ = _detect_category(_strip_accents(keyword))
        if cat_from_kw:
            category, keyword = category or cat_from_kw, None

    where, params = [], []
    if keyword:
        where.append('LOWER(name) LIKE ?')
        params.append(f'%{keyword}%')
    if category:
        where.append('category = ?')
        params.append(category)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    rows = conn.execute(
        f'SELECT name, stock FROM products {where_sql} ORDER BY stock DESC LIMIT 6',
        params).fetchall()

    if not rows:
        return {'reply': 'Tôi chưa tìm thấy sản phẩm phù hợp. '
                     'Bạn vui lòng cung cấp tên hoặc model cụ thể (ví dụ: <i>iPhone còn hàng không</i>).'}

    in_stock = [r for r in rows if (r['stock'] or 0) > 0]
    lines = []
    if keyword:
        r = rows[0]
        st = r['stock'] or 0
        if st == 0:
            lines.append(f'<b>{html.escape(r["name"])}</b> hiện đã <b>hết hàng</b>. '
                         'Vui lòng liên hệ cửa hàng để được tư vấn về tình trạng hàng.')
        else:
            availability = 'Số lượng còn hạn chế.' if st <= 5 else 'Sản phẩm hiện còn hàng.'
            lines.append(f'<b>{html.escape(r["name"])}</b> còn <b>{st}</b> sản phẩm. {availability}')
    else:
        lines.append(f'Có <b>{len(in_stock)}/{len(rows)}</b> sản phẩm trong danh sách còn hàng:')
        for r in rows:
            st = r['stock'] or 0
            lines.append(f'{html.escape(r["name"])} — còn {st}')
    return {'reply': '<br>'.join(lines)}


def _answer_sale_products(conn):
    """Danh sách sản phẩm đang có giá tốt / dưới 5 triệu (khuyến mãi)."""
    rows = conn.execute(
        "SELECT name, price, category FROM products WHERE price <= 5000000 "
        "AND COALESCE(stock,0) > 0 ORDER BY price ASC LIMIT 5").fetchall()
    if not rows:
        return {'reply': 'Hiện chưa có chương trình ưu đãi nào ạ.'}
    lines = ['<b>Một số sản phẩm dưới 5 triệu đồng:</b>']
    for r in rows:
        lines.append(f'• {html.escape(r["name"])} — '
                     f'<span class="text-danger fw-bold">{_fmt_money(r["price"])}</span>')
    return {'reply': '<br>'.join(lines),
            'links': [{'label': 'Xem tất cả sản phẩm', 'url': url_for('index')}]}


def _answer_category_stats(conn):
    """Thống kê số lượng + giá từng danh mục."""
    rows = conn.execute(
        "SELECT category, COUNT(*) AS n, MIN(price) AS lo, MAX(price) AS hi "
        "FROM products GROUP BY category ORDER BY n DESC").fetchall()
    lines = ['<b>Sản phẩm theo danh mục:</b>']
    for r in rows:
        label = CATEGORY_LABELS.get(r['category'], r['category'])
        lines.append(f'• <b>{label}</b>: {r["n"]} SP — '
                     f'{_fmt_money(r["lo"])} → {_fmt_money(r["hi"])}')
    return {'reply': '<br>'.join(lines)}


def _answer_top_selling(conn):
    """Top sản phẩm bán chạy (từ order_items thực tế)."""
    rows = conn.execute("""
        SELECT oi.product_name, SUM(oi.quantity) AS qty
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.status != 'cancelled'
        GROUP BY oi.product_name
        ORDER BY qty DESC LIMIT 5
    """).fetchall()
    if not rows:
        return {'reply': 'Chưa có dữ liệu bán hàng ạ.'}
    lines = ['<b>Sản phẩm bán chạy:</b>']
    for i, r in enumerate(rows, 1):
        lines.append(f'{i}. {html.escape(r["product_name"])} — đã bán {r["qty"]}')
    return {'reply': '<br>'.join(lines)}


def _answer_my_orders(conn, user_id):
    """Đơn hàng của chính khách đang đăng nhập."""
    if not user_id:
        return {'reply': 'Bạn cần <b>đăng nhập</b> để mình xem đơn giúp bạn nhé.',
                'links': [{'label': 'Đăng nhập', 'url': url_for('login')}]}

    rows = conn.execute("""
        SELECT order_id, total_price, status, created_at
        FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5
    """, (user_id,)).fetchall()
    if not rows:
        return {'reply': 'Bạn chưa có đơn hàng nào. Hãy chọn sản phẩm nhé!',
                'links': [{'label': 'Mua sắm', 'url': url_for('index')}]}

    status_label = {'pending': 'Chờ xử lý', 'processing': 'Đang xử lý',
                    'shipped': 'Đang giao', 'completed': 'Đã giao',
                    'delivered': 'Đã giao', 'cancelled': 'Đã hủy'}
    lines = ['<b>Đơn hàng gần đây của bạn:</b>']
    for r in rows:
        status = status_label.get((r['status'] or '').lower(), 'Chưa xác định')
        lines.append(f'<b>#{r["order_id"][:8]}</b> — {status} — '
                     f'{_fmt_money(r["total_price"])} — {(r["created_at"] or "")[:10]}')
    return {'reply': '<br>'.join(lines),
            'links': [{'label': 'Xem lịch sử đơn', 'url': url_for('view_cart')}]}


def _answer_payment_methods():
    return {'reply': (
        '<b>Các hình thức thanh toán</b><br>'
        '• <b>COD</b>: trả tiền khi nhận hàng (phổ biến nhất).<br>'
        '• <b>Chuyển khoản</b>: Vietcombank — 0123456789 — YONG NAYKHOUCH.<br>'
        '• <b>Trả góp 0%</b> qua thẻ tín dụng cho đơn từ 3.000.000 ₫ (kỳ hạn 3–12 tháng).<br>'
        '• <b>Ví điện tử</b>: MoMo, ZaloPay.')}


def _answer_installment():
    return {'reply': (
        '<b>Trả góp 0%</b><br>'
        '• Áp dụng cho đơn từ <b>3.000.000 ₫</b>.<br>'
        '• Kỳ hạn <b>3, 6, 9, 12 tháng</b> — không lãi suất.<br>'
        '• Cần CMND/CCCD + thẻ tín dụng hoặc thẻ tín dụng của ngân hàng liên kết.<br>'
        '• Ví dụ: laptop 24.000.000 ₫ → chỉ <b>2.000.000 ₫/tháng</b> (12 tháng).')}


def _answer_gift_wrap():
    return {'reply': (
        '<b>Dịch vụ gói quà</b><br>'
        '• Mọi đơn hàng đều được gói quà miễn phí nếu bạn ghi chú trong phần "Ghi chú" khi đặt.<br>'
        '• Có thiệp chúc mừng viết tay theo yêu cầu.')}


def _answer_invoice():
    return {'reply': (
        '<b>Xuất hoá đơn</b><br>'
        '• Có xuất <b>hoá đơn VAT</b> cho doanh nghiệp.<br>'
        '• Vui lòng cung cấp: tên công ty, mã số thuế, địa chỉ.<br>'
        '• Liên hệ hotline <b>0917873816</b> hoặc gửi yêu cầu qua trang Liên hệ.')}


def _answer_time():
    now = datetime.now()
    return {'reply': (f'Hiện tại là <b>{now.strftime("%H:%M")}</b> ngày '
                      f'<b>{now.strftime("%d/%m/%Y")}</b>.\n'
                      'Trợ lý trực tuyến hỗ trợ bạn 24/7.')}


def _answer_register_guide():
    return {'reply': (
        '<b>Hướng dẫn đăng ký</b><br>'
        '1. Bấm <b>Đăng ký</b> ở thanh trên cùng.<br>'
        '2. Điền tên đăng nhập, email <b>@gmail.com</b>, số điện thoại.<br>'
        '3. Nhập mật khẩu 2 lần cho khớp.<br>'
        '4. Bấm <b>Đăng ký</b> → đăng nhập ngay.'),
        'links': [{'label': 'Đăng ký ngay', 'url': url_for('register')}]}


def _answer_forgot_password():
    return {'reply': (
        '<b>Quên mật khẩu</b><br>'
        'Hiện chưa hỗ trợ đặt lại tự động. Vui lòng:'
        '<br>• Gọi hotline <b>0917873816</b> để được hỗ trợ.'
        '<br>• Hoặc mang CMND đến cửa hàng để xác minh.')}


def _answer_banking_info():
    return {'reply': (
        '<b>Thông tin chuyển khoản</b><br>'
        '• Ngân hàng: <b>Vietcombank</b><br>'
        '• Số TK: <b>0123456789</b><br>'
        '• Chủ TK: <b>YONG NAYKHOUCH</b><br>'
        '• Nội dung: <i>Ma don + Ten ban</i>')}


def _answer_cancel_order():
    return {'reply': (
        '<b>Hướng dẫn huỷ đơn hàng</b><br>'
        '• Đơn <b>Chờ xác nhận</b> hoặc <b>Đang xử lý</b>: huỷ được.<br>'
        '• Đơn <b>Đang giao</b>: gọi hotline ngay.<br>'
        '• Đơn <b>Đã giao</b>: không huỷ được, chuyển sang đổi trả.<br>'
        'Liên hệ <b>0917873816</b> để được hỗ trợ nhanh.')}


def _answer_return_policy():
    return {'reply': (
        '<b>Đổi trả và hoàn tiền</b><br>'
        '• Đổi trong <b>7 ngày</b> nếu còn đủ hộp/phụ kiện.<br>'
        '• Hoàn <b>100%</b> nếu lỗi kỹ thuật do nhà sản xuất.<br>'
        '• Hàng đã qua sử dụng/trầy xước: <b>không</b> nhận đổi (trừ lỗi NSX).<br>'
        '• Vui lòng giữ hoá đơn.')}


def _answer_hello_help():
    return {'reply': (
        '<b>Tôi có thể hỗ trợ bạn các nội dung sau:</b><br>'
        '• Tìm sản phẩm theo danh mục, thương hiệu hoặc ngân sách<br>'
        '• Kiểm tra tình trạng hàng và đơn hàng<br>'
        '• So sánh sản phẩm<br>'
        '• Tra cứu chính sách mua hàng')}


def _answer_thanks():
    return {'reply': 'Rất vui được hỗ trợ bạn. Nếu cần thêm thông tin, bạn cứ tiếp tục nhắn.'}


def _answer_fallback():
    return {
        'reply': (
            'Tôi chưa xác định được chính xác yêu cầu. Bạn có thể hỏi theo một trong các cách sau:<br>'
            '• <i>"Tư vấn điện thoại dưới 10 triệu"</i><br>'
            '• <i>"Có laptop nào không?"</i><br>'
            '• <i>"Kiểm tra đơn a1b2c3d4"</i><br>'
            '• <i>"Chính sách bảo hành"</i>'
        ),
        'links': [
            {'label': 'Xem tất cả sản phẩm', 'url': url_for('index')},
            {'label': 'Liên hệ hotline', 'url': url_for('lienhe')},
        ],
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def _get_bot_reply(message: str, db_connection_factory, user_id=None) -> dict:
    """
    Nhận câu hỏi, trả về {'reply': html, 'links': [...]}.

    db_connection_factory: hàm trả về sqlite3.Connection (truyền app.get_db_connection vào).
                            Bot tự đóng connection sau khi dùng xong.
    """
    message = (message or '').strip()
    if not message:
        return _answer_greeting()

    if len(message) > 500:
        message = message[:500]

    # Chặn XSS: câu trả lời được render bằng innerHTML ở trình duyệt.
    safe_message = html.escape(message, quote=False)

    norm = _strip_accents(message)

    # 1. Chào hỏi / cảm ơn
    if re.match(r'^(hi|hello|hey|chao|xin chao|alo|ad oi|shop oi)\b', norm):
        return _answer_greeting()
    if any(k in norm for k in ['cam on', 'thank', 'thanks']):
        return _answer_thanks()

    # 2. Liên hệ — đặt TRƯỚC bước dò danh mục để "số điện thoại"
    #    không bị hiểu thành danh mục "Điện thoại".
    if any(k in norm for k in ['lien he', 'hotline', 'so dien thoai', 'so dt',
                               'email', 'dia chi', 'gio mo cua', 'o dau']):
        return _answer_contact()

    # 3. Chính sách
    policy = _answer_policy(norm)
    if policy:
        return policy

    # ================= NHÓM CÂU HỎI MỞ RỘNG (không cần DB) =================
    # Trả góp (phải đặt TRƯỚC 'thanh toan')
    if any(k in norm for k in ['tra gop', 'gop 0', 'ky han', 'tra cham', 'tra gop 0']):
        return _answer_installment()
    # Thanh toán (mở rộng)
    if any(k in norm for k in ['thanh toan', 'payment', 'mo mo', 'momo',
                                'zalopay', 'chuyen khoan']):
        return _answer_payment_methods()
    # Thông tin ngân hàng
    if any(k in norm for k in ['so tai khoan', 'bank', 'ngan hang', 'stk', 'chuyen khoan']):
        return _answer_banking_info()
    # Gói quà
    if any(k in norm for k in ['goi qua', 'qua tang', 'thiep', 'hop qua']):
        return _answer_gift_wrap()
    # Hoá đơn VAT
    if any(k in norm for k in ['hoa don vat', 'vat', 'xuat hoa don', 'ma so thue']):
        return _answer_invoice()
    # Huỷ đơn
    if any(k in norm for k in ['huy don', 'cancel', 'khong muon mua', 'hoan don']):
        return _answer_cancel_order()
    # Đổi trả (mở rộng)
    if any(k in norm for k in ['doi tra', 'hoan tien', 'tra hang', 'refund']):
        return _answer_return_policy()
    # Đăng ký
    if any(k in norm for k in ['dang ky', 'tao tai khoan', 'register', 'đăng ký']):
        return _answer_register_guide()
    # Quên mật khẩu
    if any(k in norm for k in ['quen mat khau', 'forgot', 'doi mat khau', 'reset']):
        return _answer_forgot_password()
    # Giờ mở cửa / thời gian
    if any(k in norm for k in ['may gio', 'gio mo cua', 'mo cua', 'bay gio', 'thoi gian']):
        return _answer_time()
    # Hướng dẫn chung
    if any(k in norm for k in ['giup gi', 'giup duoc gi', 'lam duoc gi', 'lam gi',
                               'huong dan', 'help', 'co the gi', 'hoi gi',
                               'chuc nang', 'ban biet gi', 'bat dau']):
        return _answer_hello_help()

    conn = db_connection_factory()
    conn.row_factory = sqlite3.Row
    try:
        # ============các ý định mở rộng cần truy vấn DB============

        category, _cat_kw = _detect_category(norm)
        spec_answer = _answer_extra_spec_question(conn, norm, category)
        if spec_answer:
            return spec_answer

        # 4a. Đơn của tôi (cần user_id)
        if any(k in norm for k in ['don cua toi', 'don hang cua toi', 'lich su don',
                                   'don cua minh', 'my order']):
            return _answer_my_orders(conn, user_id)

        # 4b. Sản phẩm bán chạy
        if any(k in norm for k in ['ban chay', 'top ban', 'mua nhieu', 'hot nhat']):
            return _answer_top_selling(conn)

        # 4c. Thống kê danh mục
        if any(k in norm for k in ['danh muc nao', 'co nhung gi', 'kho hang',
                                   'nhung loai', 'bao nhieu loai']):
            return _answer_category_stats(conn)

        # 4d. So sánh 2 sản phẩm
        if 'so sanh' in norm or ' vs ' in norm:
            m = re.search(r'so sanh\s+(.+?)\s+(?:va|voi|vs)\s+(.+)', norm)
            if m:
                return _answer_compare(conn, m.group(1).strip(), m.group(2).strip())

        # 4e. Sản phẩm rẻ nhất / cao cấp nhất
        category, cat_kw = _detect_category(norm)
        if any(k in norm for k in ['re nhat', 'gia re', 'tiet kiem', 'it tien',
                                   'sinh vien', 'duoi 5 trieu']):
            return _answer_cheapest(conn, category)
        if any(k in norm for k in ['cao cap', 'dat nhat', 'xịn', 'xin nhat', 'pro max']):
            return _answer_expensive(conn, category)

        # 4f. Khuyến mãi / giảm giá
        if any(k in norm for k in ['khuyen mai', 'giam gia', 'sale', 'uu dai']):
            return _answer_sale_products(conn)

        # 4g. Tình trạng còn hàng
        if any(k in norm for k in ['con hang', 'het hang', 'con khong', 'co san',
                                   'ton kho', 'stock']):
            # Bỏ các từ chỉ tình trạng + từ đệm, phần còn lại mới là tên sản phẩm
            kw = norm
            for p in ['con hang khong', 'con hang', 'het hang khong', 'het hang',
                      'con khong', 'co san khong', 'co san', 'ton kho', 'stock',
                      'co khong', 'khong', 'cua', 'shop', 'ban', 'a', 'nhi']:
                kw = re.sub(r'(?<![a-z0-9])' + re.escape(p) + r'(?![a-z0-9])', ' ', kw)
            kw = re.sub(r'[^a-z0-9 ]+', ' ', kw).strip()
            kw = re.sub(r'\s+', ' ', kw)
            return _answer_stock_status(conn,
                                        keyword=kw if len(kw) >= 3 else None,
                                        category=category)

        # 4. Kiểm tra đơn hàng (ưu tiên hơn tìm sản phẩm vì mã đơn có cả chữ số)
        if any(k in norm for k in ['don hang', 'kiem tra don', 'ma don', 'order', 'van don']):
            order_id = None
            # mã đơn của dự án có dạng ORD-XXXXXXXX hoặc UUID
            m = re.search(r'\b(?:ord-)?([a-f0-9]{6,36})\b', norm)
            if m:
                order_id = m.group(1)
            return _answer_order(conn, order_id)

        # 5. Ngân sách + danh mục + từ khoá sản phẩm
        brand = _detect_brand(norm)
        budget = _extract_budget(norm)

        # 5a-pre. Có tên hãng -> tìm theo hãng (có thể kèm ngân sách)
        if brand:
            if not category:
                category = BRAND_DEFAULT_CATEGORY.get(brand)
            rows = _search_products(conn, keyword=brand, category=category,
                                    min_price=budget[0] if budget else None,
                                    max_price=budget[1] if budget else None,
                                    limit=5)
            if rows:
                scope = ''
                if budget:
                    scope = ' dưới ' + _fmt_money(budget[1]) if budget[1] else ' trên ' + _fmt_money(budget[0])
                lines = ['Sản phẩm <b>{}</b>{}:'.format(brand.upper(), scope)]
                for r in rows:
                    lines.append('• {} — <span class="text-danger fw-bold">{}</span>'.format(
                        html.escape(r['name']), _fmt_money(r['price'])))
                links = []
                if category:
                    links.append({'label': 'Xem danh mục ' + CATEGORY_LABELS[category],
                                  'url': url_for('category_products', category=category)})
                else:
                    links.append({'label': 'Xem tất cả sản phẩm', 'url': url_for('index')})
                return {'reply': '<br>'.join(lines), 'links': links}

        # Bỏ các từ đệm để phần còn lại là tên/hãng sản phẩm
        stop_words = ['tu van', 'gia bao nhieu', 'bao nhieu', 'co khong',
                      'tim', 'goi y', 'cho minh', 'minh muon', 'san pham',
                      'loai', 'chiec', 'toi muon', 'shop']
        search_text = norm
        for sw in stop_words:
            search_text = search_text.replace(sw, ' ')
        # Bỏ luôn số tiền (đã xử lý bằng budget) để không lẫn vào từ khoá
        search_text = re.sub(r'\d+(?:[.,]\d+)?\s*(?:trieu|tr|chai|cu|d|vnd)\b', ' ', search_text)
        search_text = re.sub(r'\d[\d.,]{5,}', ' ', search_text)
        search_text = re.sub(r'[^a-z0-9 ]+', ' ', search_text)
        products_hint = re.sub(r'\s+', ' ', search_text).strip()

        # 5a. Có từ khoá cụ thể hơn tên danh mục -> tìm theo tên/hãng
        extra_kw = products_hint
        if brand:
            extra_kw = re.sub(r'(?<![a-z0-9])' + re.escape(brand) + r'(?![a-z0-9])',
                              ' ', extra_kw)
        if cat_kw:
            extra_kw = re.sub(r'(?<![a-z0-9])' + re.escape(cat_kw) + r'(?![a-z0-9])',
                              ' ', extra_kw)
        # bỏ tên danh mục tiếng Anh lẫn trong câu (vd: "tim samsung" -> "samsung")
        extra_kw = re.sub(r'\s+', ' ', extra_kw).strip()
        if len(extra_kw) >= 3:
            result = _answer_product_search(conn, extra_kw, display=safe_message)
            if not result.get('not_found'):
                return result

        # 5b. Chỉ có danh mục (kèm hoặc không kèm ngân sách)
        if category and budget:
            return _answer_budget(conn, category, budget)
        if category:
            return _answer_category(conn, category)
        if budget and any(k in norm for k in ['san pham', 'mua', 'tu van', 'goi y', 'tim']):
            return _answer_budget(conn, None, budget)

        # 5c. Tìm tự do theo cụm còn lại
        if len(products_hint) >= 3:
            result = _answer_product_search(conn, products_hint, display=safe_message)
            if not result.get('not_found'):
                return result

        return _answer_fallback()
    finally:
        conn.close()


def get_bot_reply(message: str, db_connection_factory, user_id=None) -> dict:
    """Return a concise, presentation-ready reply without decorative icons."""
    return _clean_bot_result(
        _get_bot_reply(message, db_connection_factory, user_id=user_id)
    )
