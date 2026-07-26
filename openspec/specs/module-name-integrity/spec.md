# module-name-integrity Specification

## Purpose
TBD - created by archiving change rename-sync-catalog-test. Update Purpose after archive.
## Requirements
### Requirement: Tham chiếu file module trong test và tài liệu phải giải quyết được

Guard test SHALL quét một tập bề mặt cố định và xác minh mọi token dạng `<name>.py`
xuất hiện trong đó đều trỏ tới một file có thật.

Tập bề mặt được quét: `tests/**/test_*.py` (đệ quy), `README.md`, `CLAUDE.md`,
`openspec/config.yaml`.

Một token `<name>.py` được coi là giải quyết được khi file tồn tại ở gốc repo **hoặc**
ở bất kỳ đâu dưới `tests/`. Token nào không giải quyết được SHALL làm guard thất bại.

Guard SHALL bỏ qua `.superpowers/` và `openspec/changes/`: đó là nhật ký công việc và
hồ sơ đề xuất, ghi lại trạng thái repo tại thời điểm viết. Sửa chúng cho khớp hiện tại
là làm sai lệch hồ sơ lịch sử.

Guard SHALL loại chính file source của nó khỏi phạm vi quét. Guard buộc phải viết ra
tên mà nó cấm, nên tự quét mình sẽ khiến nó đỏ vĩnh viễn.

#### Scenario: Mọi tham chiếu đều trỏ tới file có thật

- **WHEN** guard chạy trên cây thư mục mà mọi token `<name>.py` trong tập bề mặt đều
  ứng với một file ở gốc repo hoặc trong `tests/`
- **THEN** guard pass

#### Scenario: Tài liệu tham chiếu module đã bị gỡ

- **WHEN** `README.md` chứa token `sync_codex_models.py` mà file đó không tồn tại ở gốc
  repo cũng không có trong `tests/`
- **THEN** guard fail
- **AND** thông báo lỗi nêu đường dẫn file vi phạm, số dòng, và token không giải quyết
  được, để tác giả sửa được mà không phải đi dò

#### Scenario: Tham chiếu tới file test được giải quyết trong tests/

- **WHEN** một bề mặt được quét chứa token `test_sync_model_catalog.py`, file này nằm
  trong `tests/` chứ không ở gốc repo
- **THEN** guard coi token đó là hợp lệ và không báo lỗi

#### Scenario: Nhật ký lịch sử không bị quét

- **WHEN** `.superpowers/sdd/task-1-report.md` chứa tham chiếu tới tên module không còn
  tồn tại
- **THEN** guard bỏ qua file đó và không fail vì nó

#### Scenario: Guard không tự quét chính nó

- **WHEN** guard chạy, và source của nó chứa tên module đã bị gỡ vì nó phải khai báo
  tên đó để cấm
- **THEN** guard bỏ qua file source của chính mình
- **AND** không báo vi phạm nào trỏ vào chính guard

### Requirement: Tên file test phải cho biết nó test cái gì

Guard test SHALL xác minh mỗi file `tests/test_<X>.py` thuộc đúng một trong hai loại:

1. **Đặt theo module** — `<X>.py` tồn tại ở gốc repo. File test mang tên module nó test.
2. **Đặt theo chủ đề** — `<X>` nằm trong allowlist tường minh khai báo ngay trong guard,
   dành cho file test cắt ngang nhiều module.

File test không thuộc loại nào SHALL làm guard thất bại. Đây chính là chữ ký của lỗi:
một file test mang tên module từng tồn tại nhưng đã bị đổi tên hoặc gỡ bỏ.

Allowlist SHALL nằm trong source của guard chứ không đọc từ file cấu hình ngoài, để mỗi
lần thêm ngoại lệ đều hiện ra trong diff và bị review.

#### Scenario: File test đặt theo module còn sống

- **WHEN** `tests/test_sync_model_catalog.py` tồn tại và `sync_model_catalog.py` có ở
  gốc repo
- **THEN** guard chấp nhận file đó là loại "đặt theo module"

#### Scenario: File test đặt theo chủ đề có trong allowlist

- **WHEN** `tests/test_windows_store_patch.py` tồn tại, `windows_store_patch.py` không có
  ở gốc repo, và `windows_store_patch` nằm trong allowlist của guard
- **THEN** guard chấp nhận file đó là loại "đặt theo chủ đề"

#### Scenario: File test mang tên module đã chết

- **WHEN** `tests/test_sync_codex_models.py` tồn tại, `sync_codex_models.py` không có ở
  gốc repo, và `sync_codex_models` không nằm trong allowlist
- **THEN** guard fail
- **AND** thông báo lỗi nêu tên file vi phạm và yêu cầu chọn một trong hai: đổi tên file
  cho khớp module nó test, hoặc thêm vào allowlist kèm lý do

#### Scenario: Thêm ngoại lệ phải hiện trong diff

- **WHEN** một file test đặt theo chủ đề mới được thêm và cần miễn trừ
- **THEN** allowlist trong source của guard phải được sửa, nên ngoại lệ xuất hiện trong
  diff của commit đó

### Requirement: Tên `sync_codex_models` không được sót lại ở đâu

Sau thay đổi này, định danh `sync_codex_models` SHALL không còn xuất hiện trong tập bề
mặt được quét. Việc đổi tên SHALL bảo toàn nội dung file test và độ phủ test.

#### Scenario: File test được đổi tên, nội dung giữ nguyên

- **WHEN** kiểm tra cây thư mục sau thay đổi
- **THEN** `tests/test_sync_model_catalog.py` tồn tại và `tests/test_sync_codex_models.py`
  không còn
- **AND** file mới vẫn chứa đủ 57 test method như file cũ, không có method nào bị sửa
  hay bỏ đi

#### Scenario: README không còn khẳng định có compatibility wrapper

- **WHEN** đọc `README.md`
- **THEN** không có đoạn nào nói `sync_codex_models.py` tồn tại như một compatibility
  wrapper, vì file đó không có trong repo

#### Scenario: Ghi chú __pycache__ trong CLAUDE.md không còn trỏ tên đã chết

- **WHEN** đọc `CLAUDE.md`
- **THEN** không đoạn nào tham chiếu `sync_codex_models`

#### Scenario: Độ phủ test không suy giảm sau khi đổi tên

- **WHEN** chạy `python -m unittest discover -s tests`
- **THEN** suite thu được ít nhất 157 test đã có từ trước, cộng thêm các guard test mới
- **AND** tất cả pass

#### Scenario: Tập module thu được khớp đúng tập file nguồn

- **WHEN** chạy discovery trên `tests/`
- **THEN** tập tên module thu được bằng đúng tập `tests/**/test_*.py` có trên đĩa
- **AND** một file `test_*.py` không đóng góp test nào, hoặc một module nạp lỗi, đều làm
  guard fail — vì cả hai làm hai tập lệch nhau

#### Scenario: Module test nạp lỗi phải bị phát hiện

- **WHEN** một module test không import được
- **THEN** guard fail và nêu id của module đó
- **AND** guard không được coi suite là khoẻ chỉ vì `unittest` đã biến lỗi import thành
  một `_FailedTest` đếm được

