## Why

Lần đổi tên `sync_codex_models.py` → `sync_model_catalog.py` trước đây chỉ hoàn tất ở
phía module production. Ba tàn dư còn lại vẫn mang cái tên đã chết:

- `tests/test_sync_codex_models.py` — file test đặt theo tên module không còn tồn tại,
  trong khi nội dung của nó `import sync_model_catalog`.
- `README.md:164-166` — khẳng định `sync_codex_models.py` "remains as a compatibility
  wrapper for existing installations". File đó không có trong repo. Đây là **thông tin
  sai**, không chỉ là thông tin cũ: người đọc README sẽ đi tìm một wrapper không tồn tại.
- `CLAUDE.md:15-24` — ghi chú cảnh báo `__pycache__` xây quanh chính cái tên đã chết.

Tên file test là thứ đầu tiên người đọc dùng để định vị test cho một module. Trỏ vào một
module không tồn tại làm hỏng đúng chức năng đó, và tài liệu sai thì tệ hơn tài liệu
thiếu.

## What Changes

- Đổi tên `tests/test_sync_codex_models.py` → `tests/test_sync_model_catalog.py` bằng
  `git mv`. **Nội dung file giữ nguyên, không sửa một dòng nào.**
- Xoá đoạn `README.md:164-166` nói về compatibility wrapper không tồn tại.
- Cập nhật ghi chú `__pycache__` trong `CLAUDE.md:15-24` để không còn tham chiếu
  `sync_codex_models`.
- Xác nhận `openspec/config.yaml:8-9` liệt kê đúng tên module hiện tại (đang đúng; kiểm
  tra để tên module lọt vào lưới của guard test mới).
- Thêm một guard test mới chặn tái phát: không file nào trong `tests/`, `README.md`,
  `CLAUDE.md`, hay `openspec/config.yaml` được tham chiếu một module cấp root không tồn
  tại. Đây là **SPEC TEST** — phải đỏ trước khi dọn, vì hôm nay các tham chiếu đó đang có
  thật.

Không có **BREAKING** nào: không đổi tên module production, không đổi lệnh người dùng
gõ, không đổi API. Lệnh chạy test giữ nguyên `python -m unittest discover -s tests`. Lệnh
chạy một file thì đổi từ `python -m unittest tests.test_sync_codex_models` sang
`tests.test_sync_model_catalog` — đường dẫn nội bộ của dự án, không phải hợp đồng ngoài.

### Phạm vi bị loại trừ có chủ ý

`tests/test_sync_model_catalog.py` sau khi đổi tên **vẫn chứa 6/10 class test
`patch_chatgpt_providers`** (`PatcherTemplateTests`, `CurrentBundleTests`,
`SiblingOriginalTests`, `RollbackSnapshotTests`, `PatchTransactionTests`, `ReapplyTests`
— dòng 177-1466, khoảng 88% file). Chỉ 4 class đầu (dòng 34-176) thật sự test
`sync_model_catalog`. Việc tách file đã được cân nhắc và **chủ ý loại khỏi thay đổi
này**: đây là quyết định phạm vi của chủ dự án, đổi lấy rủi ro gần bằng 0. Hệ quả cần
nói thẳng: tên mới đúng về module nó trỏ tới, nhưng vẫn mô tả sai phần lớn nội dung. Việc
tách là một change riêng nếu muốn làm sau.

## Capabilities

### New Capabilities

- `module-name-integrity`: Tên module cấp root xuất hiện trong file test và tài liệu dự
  án phải tương ứng với module có thật. Bao gồm cả hành vi thất bại: guard phải chỉ đúng
  file, dòng, và tên module chết khi phát hiện vi phạm.

### Modified Capabilities

Không có. `openspec/specs/` hiện trống, nên đây là delta đầu tiên của capability này và
toàn bộ là ADDED.

## Impact

**Đổi tên**
- `tests/test_sync_codex_models.py` → `tests/test_sync_model_catalog.py` (`git mv`, nội
  dung không đổi, 57 test method giữ nguyên)

**Sửa tài liệu**
- `README.md:164-166` (xoá đoạn wrapper sai)
- `CLAUDE.md:15-24` (ghi chú `__pycache__`)
- `openspec/config.yaml:8-9` (xác nhận)

**Thêm mới**
- Một guard test cho `module-name-integrity`

**Không chạm vào**
- Không sửa file production nào: `patch_chatgpt_providers.py`, `codex_config.py`,
  `setup.py`, `setup_custom_provider.py`, `sync_model_catalog.py` đều giữ nguyên.
- Không chạm `ChatGPT.app`, không chạm cấu hình Codex, không chạm file định tuyến
  provider.
- **Không nguyên tắc nào trong I–V bị ảnh hưởng.** Thay đổi này nằm hoàn toàn trong
  tầng test và tài liệu. Cụ thể: các class test luồng backup/patch/rollback
  (`RollbackSnapshotTests`, `PatchTransactionTests`, `ReapplyTests` — phủ nguyên tắc I,
  II, III) **được đổi tên file chứ không sửa nội dung**, nên độ phủ của chúng không hề
  suy giảm.

**Kiểm chứng**
- `python -m unittest discover -s tests` phải vẫn ra **157 test, tất cả pass**, cộng thêm
  guard test mới. Số test giảm đi là dấu hiệu file bị mất khỏi discovery.
- Dọn `tests/__pycache__/test_sync_codex_models.cpython-*.pyc` sau khi đổi tên. Lưu ý:
  bytecode mồ côi trong `__pycache__/` không import được nếu thiếu file nguồn (Python
  3.2+), nên nó là rác cần dọn chứ chưa được xác nhận là nguyên nhân của triệu chứng mà
  ghi chú `CLAUDE.md` mô tả — lý do càng nên bỏ ghi chú đó thay vì chép lại nó dưới tên
  mới.

**Rủi ro**
- Rủi ro chính là công cụ ngoài repo tham chiếu cứng đường dẫn test cũ. Không tìm thấy
  tham chiếu nào: repo không có CI config, không có `pyproject.toml`/`setup.cfg`. Tham
  chiếu duy nhất tới tên cũ nằm trong `CLAUDE.md`, và nó nằm trong phạm vi thay đổi này.
