import json


EXTRA_SPEC_FIELDS = {
    'dienthoai': [
        ('network_support', 'Hỗ trợ mạng di động', 'Ví dụ: 5G, 4G LTE'),
        ('fast_charging', 'Sạc nhanh', 'Ví dụ: 45W; không hỗ trợ'),
        ('charger_included', 'Củ sạc đi kèm', 'Ví dụ: Có; không có'),
        ('dust_water_resistance', 'Chuẩn kháng bụi/nước', 'Ví dụ: IP68'),
        ('data_transfer_service', 'Hỗ trợ chuyển dữ liệu', 'Ví dụ: Có miễn phí; liên hệ cửa hàng'),
    ],
    'maytinhbanpc': [
        ('assembled', 'Tình trạng lắp ráp', 'Ví dụ: Lắp ráp sẵn, đã kiểm tra'),
        ('operating_system', 'Hệ điều hành cài sẵn', 'Ví dụ: Windows 11 Home; chưa cài'),
        ('power_supply', 'Nguồn máy tính (PSU)', 'Ví dụ: 650W 80 Plus Bronze'),
        ('case_fan_count', 'Quạt tản nhiệt đi kèm', 'Ví dụ: 3 quạt 120mm'),
        ('water_cooling', 'Hỗ trợ tản nhiệt nước', 'Ví dụ: Có, radiator tối đa 240mm'),
        ('dimensions', 'Kích thước bộ máy', 'Ví dụ: 450 x 220 x 450 mm'),
    ],
    'tulanh': [
        ('dimensions', 'Kích thước (R x C x S)', 'Ví dụ: 700 x 1800 x 650 mm'),
        ('auto_ice', 'Tự động làm đá', 'Ví dụ: Có; không có'),
        ('external_water_dispenser', 'Lấy nước bên ngoài', 'Ví dụ: Có; không có'),
        ('noise_level', 'Độ ồn', 'Ví dụ: 38 dB'),
    ],
    'beptu': [
        ('surface_material', 'Chất liệu mặt bếp', 'Ví dụ: Kính Schott Ceran'),
        ('cookware_compatibility', 'Loại nồi tương thích', 'Ví dụ: Nồi có đáy từ'),
        ('safety_features', 'Tính năng an toàn', 'Ví dụ: Tự ngắt quá nhiệt, nhận diện nồi'),
        ('child_lock', 'Khóa trẻ em', 'Ví dụ: Có; không có'),
        ('installation_service', 'Dịch vụ lắp đặt', 'Ví dụ: Có hỗ trợ; phí theo khu vực'),
    ],
    'dongho': [
        ('watch_type', 'Loại đồng hồ', 'Ví dụ: Smartwatch; cơ; quartz'),
        ('esim_support', 'Hỗ trợ eSIM', 'Ví dụ: Có; không có'),
        ('interchangeable_band', 'Dây đeo thay thế', 'Ví dụ: Dây tháo rời 20mm'),
    ],
    'quat': [
        ('natural_wind', 'Chế độ gió tự nhiên', 'Ví dụ: Có; không có'),
        ('adjustable_height', 'Điều chỉnh chiều cao', 'Ví dụ: Có, 90–120 cm'),
        ('noise_level', 'Độ ồn', 'Ví dụ: 35 dB ở mức thấp'),
        ('dimensions', 'Kích thước sản phẩm', 'Ví dụ: 450 x 400 x 1200 mm'),
        ('easy_cleaning', 'Tháo lắp để vệ sinh', 'Ví dụ: Lồng và cánh tháo rời'),
    ],
    'laptop': [
        ('weight', 'Trọng lượng', 'Ví dụ: 1.65 kg'),
        ('anti_glare', 'Chống lóa màn hình', 'Ví dụ: Có, lớp phủ chống lóa'),
        ('keyboard_backlight', 'Đèn nền bàn phím', 'Ví dụ: Có, LED trắng'),
        ('upgrade_options', 'Khả năng nâng cấp', 'Ví dụ: 1 khe RAM, 1 khe M.2'),
        ('office_software_setup', 'Cài phần mềm văn phòng', 'Ví dụ: Có hỗ trợ theo yêu cầu'),
    ],
    'maygiatsay': [
        ('drying_function', 'Chức năng sấy', 'Ví dụ: Sấy 7kg; không có'),
        ('hot_water_wash', 'Giặt nước nóng', 'Ví dụ: Có, tối đa 60°C'),
        ('drum_cleaning', 'Tự vệ sinh lồng giặt', 'Ví dụ: Có'),
        ('dimensions', 'Kích thước (R x C x S)', 'Ví dụ: 600 x 850 x 600 mm'),
    ],
}

EXTRA_SPEC_LABELS = {
    key: label
    for fields in EXTRA_SPEC_FIELDS.values()
    for key, label, _placeholder in fields
}
EXTRA_SPEC_LABELS['dimensions'] = 'Kích thước'

EXTRA_SPEC_ICONS = {
    'network_support': 'fa-signal',
    'fast_charging': 'fa-bolt',
    'charger_included': 'fa-plug',
    'dust_water_resistance': 'fa-shield-halved',
    'data_transfer_service': 'fa-right-left',
    'assembled': 'fa-screwdriver-wrench',
    'operating_system': 'fa-desktop',
    'power_supply': 'fa-plug',
    'case_fan_count': 'fa-fan',
    'water_cooling': 'fa-droplet',
    'dimensions': 'fa-ruler-combined',
    'auto_ice': 'fa-cubes-stacked',
    'external_water_dispenser': 'fa-glass-water',
    'noise_level': 'fa-volume-low',
    'surface_material': 'fa-layer-group',
    'cookware_compatibility': 'fa-kitchen-set',
    'safety_features': 'fa-shield',
    'child_lock': 'fa-lock',
    'installation_service': 'fa-screwdriver-wrench',
    'watch_type': 'fa-stopwatch',
    'esim_support': 'fa-sim-card',
    'interchangeable_band': 'fa-link',
    'natural_wind': 'fa-wind',
    'adjustable_height': 'fa-arrows-up-down',
    'easy_cleaning': 'fa-broom',
    'weight': 'fa-weight-hanging',
    'anti_glare': 'fa-sun',
    'keyboard_backlight': 'fa-keyboard',
    'upgrade_options': 'fa-arrow-up-from-bracket',
    'office_software_setup': 'fa-file-word',
    'drying_function': 'fa-temperature-high',
    'hot_water_wash': 'fa-temperature-high',
    'drum_cleaning': 'fa-soap',
}


def parse_extra_specs(value):
    if not value:
        return {}
    if isinstance(value, dict):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
    else:
        return {}
    return {
        key: str(item).strip()
        for key, item in parsed.items()
        if key in EXTRA_SPEC_LABELS and item is not None and str(item).strip()
    }


def extra_specs_from_form(form, category):
    allowed = {key for key, _label, _placeholder in EXTRA_SPEC_FIELDS.get(category, [])}
    values = {}
    for key in allowed:
        value = (form.get('extra_spec_' + key) or '').strip()
        if value:
            values[key] = value
    return values


def serialize_extra_specs(value, category=None):
    if value is None:
        parsed = {}
    elif isinstance(value, dict):
        parsed = value
    else:
        raise ValueError('Extra specifications must be provided as an object.')

    allowed_keys = set(EXTRA_SPEC_LABELS)
    if category is not None:
        allowed_keys = {
            key for key, _label, _placeholder in EXTRA_SPEC_FIELDS.get(category, [])
        }
    unknown_keys = set(parsed) - allowed_keys
    if unknown_keys:
        raise ValueError('Unknown extra specification keys.')
    cleaned = {}
    for key, item in parsed.items():
        if item is None:
            continue
        if not isinstance(item, str):
            raise ValueError('Extra specification values must be text.')
        item = item.strip()
        if item:
            cleaned[key] = item
    return json.dumps(cleaned, ensure_ascii=False)
