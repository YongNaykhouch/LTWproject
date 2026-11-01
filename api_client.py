import json
import os

try:
    import requests
except ImportError:  # fallback nếu chưa cài requests
    requests = None
    import urllib.error
    import urllib.request


BASE_URL = os.environ.get('API_BASE_URL', 'http://127.0.0.1:5000/api/v1')
API_KEY = os.environ.get('APP_API_KEY', 'dev-api-key-2026')


class ApiError(Exception):
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload
        super().__init__(f'HTTP {status}: {payload}')


class ApiClient:
    """Bọc toàn bộ endpoint, trả về dict đã parse JSON."""

    def __init__(self, base_url=BASE_URL, api_key=API_KEY):
        self.base = base_url.rstrip('/')
        self.headers = {'X-API-Key': api_key, 'Content-Type': 'application/json'}

    # ---------------- transport ----------------
    def _request(self, method, path, params=None, body=None):
        url = f'{self.base}{path}'
        headers = dict(self.headers)
        if method == 'GET':
            headers.pop('Content-Type', None)

        if requests is not None:
            resp = requests.request(method, url, params=params, headers=headers,
                                    json=body, timeout=15)
            status, text = resp.status_code, resp.text
        else:
            from urllib.parse import urlencode
            if params:
                url += '?' + urlencode(params)
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    status, text = r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                status, text = e.code, e.read().decode()

        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {'raw': text}

        if status >= 400:
            raise ApiError(status, payload)
        return payload

    # ---------------- health ----------------
    def health(self):
        return self._request('GET', '/health')

    # ---------------- products ----------------
    def list_products(self, page=1, per_page=20, **filters):
        params = {'page': page, 'per_page': per_page}
        params.update({k: v for k, v in filters.items() if v is not None})
        return self._request('GET', '/products', params=params)

    def get_product(self, product_id):
        return self._request('GET', f'/products/{product_id}')['data']

    def create_product(self, **data):
        return self._request('POST', '/products', body=data)['data']

    def update_product(self, product_id, **data):
        return self._request('PATCH', f'/products/{product_id}', body=data)['data']

    def delete_product(self, product_id):
        return self._request('DELETE', f'/products/{product_id}')

    # ---------------- orders ----------------
    def list_orders(self, page=1, per_page=20, **filters):
        params = {'page': page, 'per_page': per_page}
        params.update({k: v for k, v in filters.items() if v is not None})
        return self._request('GET', '/orders', params=params)

    def get_order(self, order_id):
        return self._request('GET', f'/orders/{order_id}')['data']

    def create_order(self, user_id, address, phone, items, status='pending'):
        body = {
            'user_id': user_id,
            'address': address,
            'phone': phone,
            'status': status,
            'items': items,          # [{'product_id': 1, 'quantity': 2}, ...]
        }
        return self._request('POST', '/orders', body=body)['data']

    def update_order(self, order_id, **data):
        return self._request('PATCH', f'/orders/{order_id}', body=data)['data']

    def delete_order(self, order_id):
        return self._request('DELETE', f'/orders/{order_id}')

    # ---------------- order items ----------------
    def list_order_items(self, order_id):
        return self._request('GET', '/order-items', params={'order_id': order_id})['data']

    def add_order_item(self, order_id, product_id, quantity=1):
        return self._request('POST', '/order-items',
                             body={'order_id': order_id, 'product_id': product_id,
                                   'quantity': quantity})['data']

    def update_order_item(self, item_id, **data):
        return self._request('PATCH', f'/order-items/{item_id}', body=data)['data']

    def delete_order_item(self, item_id):
        return self._request('DELETE', f'/order-items/{item_id}')

    # ---------------- customers ----------------
    def list_customers(self, q=None, page=1, per_page=20):
        params = {'page': page, 'per_page': per_page}
        if q:
            params['q'] = q
        return self._request('GET', '/customers', params=params)

    def get_customer(self, customer_id):
        return self._request('GET', f'/customers/{customer_id}')['data']

    def create_customer(self, username, email, phone='', address='', password='123456'):
        return self._request('POST', '/customers', body={
            'username': username, 'email': email, 'phone': phone,
            'address': address, 'password': password,
        })['data']

    def update_customer(self, customer_id, **data):
        return self._request('PATCH', f'/customers/{customer_id}', body=data)['data']

    def delete_customer(self, customer_id):
        return self._request('DELETE', f'/customers/{customer_id}')

    # ---------------- stats ----------------
    def revenue(self, period='month', date=None):
        params = {'period': period}
        if date:
            params['date'] = date
        return self._request('GET', '/stats/revenue', params=params)

    def sales(self):
        """Doanh thu bán được (mọi đơn trừ đơn hủy)."""
        return self._request('GET', '/stats/sales')

    def low_stock(self, threshold=5):
        """Danh sách sản phẩm sắp hết hàng."""
        return self._request('GET', '/stats/low-stock', params={'threshold': threshold})


# =====================================================================
# Demo: chạy trực tiếp file này để thấy toàn bộ luồng CRUD
# =====================================================================
if __name__ == '__main__':
    print('Đang kết nối', BASE_URL, '\n')
    api = ApiClient()

    try:
        print('1) Health:', api.health()['service'])

        print('\n2) 5 sản phẩm mới nhất:')
        for p in api.list_products(per_page=5)['data']:
            print(f"   #{p['id']:<4} {p['name'][:45]:<45} {p['price']:>14,.0f} ₫")

        print('\n3) Tạo sản phẩm test...')
        created = api.create_product(
            name='[API DEMO] Sản phẩm tạm', category='dienthoai',
            brand='DemoBrand', price=1_990_000, stock=3)
        pid = created['id']
        print('   -> id =', pid, '| product_id =', created['product_id'])

        print('\n4) Cập nhật giá sản phẩm vừa tạo...')
        updated = api.update_product(pid, price=1_500_000)
        print('   -> giá mới:', f"{updated['price']:,.0f} ₫")

        print('\n5) Danh sách khách hàng (3 đầu):')
        for c in api.list_customers(per_page=3)['data']:
            print(f"   #{c['id']:<3} {c['username']:<20} {c['email']:<30} "
                  f"{c['order_count']} đơn")

        print('\n6) Đơn hàng gần nhất:')
        for o in api.list_orders(per_page=3)['data']:
            print(f"   #{o['order_id'][:8]:<10} {o['status']:<12} "
                  f"{o['total_price']:>14,.0f} ₫  ({o['item_count']} SP)")

        print('\n7) Thống kê doanh thu tháng này:')
        st = api.revenue('month')
        print(f"   {st['from']} → {st['to']}: {st['total_orders']} đơn, "
              f"{st['total_revenue']:,.0f} ₫")

        print('\n8) Test bảo mật (sai API key) → phải bị chặn:')
        bad = ApiClient(api_key='sai-key')
        try:
            bad.create_product(name='Hacker', category='dienthoai')
        except ApiError as e:
            print('   ->', e.status, e.payload['error'])

        print('\n9) Dọn dẹp: xóa sản phẩm demo...')
        api.delete_product(pid)
        print('   -> đã xóa #', pid)

    except ApiError as err:
        print('\n[API ERROR]', err.status, err.payload)
        print('Kiểm tra: server đã chạy chưa (`python app.py`)?')
    except Exception as err:  # ConnectionError...
        print('\n[LỖI KẾT NỐI]', err)
        print('Chạy server trước: python app.py')
