# LTWproject-main

Website thương mại điện tử bằng Flask cho các sản phẩm công nghệ như điện thoại, laptop, đồng hồ thông minh, máy ảnh, điều hòa, tủ lạnh và các thiết bị gia dụng.

## Tính năng chính

- Trang chủ hiển thị sản phẩm theo danh mục
- Đăng ký / đăng nhập / quản lý hồ sơ người dùng
- Giỏ hàng và đặt hàng
- Tìm kiếm và lọc sản phẩm theo danh mục
- Trang quản trị admin để quản lý sản phẩm, đơn hàng, khách hàng
- Chatbot hỗ trợ tìm sản phẩm và tương tác với khách hàng
- Lưu trữ dữ liệu bằng SQLite

## Công nghệ sử dụng

- Python 3
- Flask
- SQLite
- Jinja2 templates
- Bootstrap / HTML / CSS / JavaScript

## Yêu cầu môi trường

- Python 3.9+ (khuyến nghị 3.10+)
- pip

## Cài đặt

1. Mở terminal trong thư mục dự án
2. Tạo môi trường ảo (không bắt buộc nhưng nên làm):

```bash
python -m venv venv
venv\Scripts\activate
```

3. Cài đặt thư viện cần thiết:

```bash
pip install flask
```

4. Khởi tạo cơ sở dữ liệu ban đầu:

```bash
python init_db.py
```

5. Chạy ứng dụng:

```bash
python app.py
```

6. Mở trình duyệt và truy cập:

```text
http://127.0.0.1:5000/
```

## Tài khoản admin mặc định

Sau khi chạy `init_db.py`, hệ thống sẽ tạo tài khoản admin mặc định:

- Username: `admin`
- Password: `admin123`

## Cấu trúc thư mục chính

```text
.
├── app.py                  # File ứng dụng chính
├── api.py                  # API backend
├── init_db.py              # Khởi tạo database và dữ liệu mẫu
├── chatbot.py              # Logic chatbot
├── product_extra_specs.py  # Bộ dữ liệu thuộc tính sản phẩm
├── static/                 # File tĩnh (CSS, JS, hình ảnh, uploads)
├── templates/              # Giao diện HTML
├── users.db                # Database SQLite
├── README.md               # Tài liệu dự án
└── ...
```

## Lưu ý

- App sẽ tự tạo thư mục `static/uploads` nếu chưa tồn tại.
- Secret key được sinh tự động nếu chưa có biến môi trường `FLASK_SECRET_KEY`.
- Để deploy production, nên cấu hình thêm secret key, environment variables và bảo mật khác.

## Ghi chú phát triển

Dự án này chủ yếu là một ứng dụng web học tập / demo cho môn lập trình web (LTW), nên cấu trúc và dữ liệu có thể được mở rộng thêm tùy theo yêu cầu thực tế.
