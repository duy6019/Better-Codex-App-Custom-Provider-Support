# Better Codex App — Custom Provider Support

Công cụ Python vá ứng dụng ChatGPT/Codex desktop để hỗ trợ custom provider.

## Chạy test

```bash
python -m unittest discover -s tests
```

Dùng `unittest` của thư viện chuẩn, **không phải pytest** (pytest chưa cài). Test hiện có
dùng dependency injection (`input_func`, `output_func`, `command_runner`) thay vì mock —
giữ đúng phong cách đó.

Trạng thái: **157 test, tất cả pass.**

Cảnh báo về `__pycache__` cũ: `sync_codex_models.py` đã được đổi tên thành
`sync_model_catalog.py`, nhưng bytecode cũ có thể còn sót trong `__pycache__/` và làm
`unittest discover` nạp nhầm phiên bản cũ — biểu hiện là
`ModuleNotFoundError: No module named 'sync_codex_models'` cùng số test ít hơn 157.
Nếu gặp, dọn cache rồi chạy lại; đó không phải lỗi source:

```bash
find . -name __pycache__ -type d -exec rm -rf {} + && python -m unittest discover -s tests
```

---

## Định tuyến công việc (đọc mỗi phiên)

Repo này dùng schema OpenSpec `sdd-tdd` (hai tầng) ghép với superpowers.
Năm nguyên tắc bất di bất dịch của dự án nằm trong `openspec/config.yaml`.

### Việc đầu tiên, trước khi gọi bất kỳ skill nào

Với mọi yêu cầu thêm tính năng hoặc sửa lỗi, hành động đầu tiên là chạy `openspec list`
rồi phân tầng. **Không brainstorm trước bước này.**

- **NHẸ — mặc định.** Thay đổi nằm trong một module, không thêm dependency, không đổi
  định dạng file cấu hình, không đụng luồng vá ASAR.
- **NẶNG** — chỉ khi có ít nhất một trong: vượt ranh giới module, đổi định dạng file
  cấu hình hoặc catalog, chạm vào luồng backup/patch/restore của `ChatGPT.app`, buộc
  phải cân nhắc lại một trong năm nguyên tắc, hoặc tôi gõ đúng chữ **LARGE CHANGE**.

Bạn được phép **đề xuất** nâng lên NẶNG. Bạn không được tự quyết, và không được đổi tầng
giữa chừng.

### Tầng NHẸ

Đây là chỉ thị thường trực của tôi, dùng đúng quyền ưu tiên mà `superpowers:using-superpowers`
đã cấp cho user instructions. **Tôi đang nói rõ với bạn rằng hãy bỏ qua các bước sau:**

- **Bỏ `superpowers:writing-plans`.** Tầng nhẹ không có plan file.
- Nếu `superpowers:brainstorming` được gọi, **trạng thái kết thúc của nó trong repo này
  KHÔNG phải `writing-plans`**. Kết quả ghi vào `openspec/changes/<name>/proposal.md` và
  `openspec/changes/<name>/specs/`, rồi dừng.
- **Không ghi vào `docs/superpowers/`.** Thư mục đó đã bị xoá và không được tạo lại.

Đường đi: `/opsx:propose` → `/opsx:apply` → `openspec archive <name>`.

### Tầng NẶNG

Thêm `design.md`, `tasks.md`, và `<change-name>-plan.md` do `superpowers:writing-plans`
viết — ghi thẳng vào thư mục change, **không** vào `docs/superpowers/plans/`.

Tên file plan phải là `<change-name>-plan.md`, **không bao giờ** là `plan.md`:
`sdd-workspace` lấy slug từ tên file, đặt trùng thì mọi change dùng chung một workspace
và ghi đè ledger của nhau.

### Chỉ thị thường trực khác

- **Worktree: không dùng, và đừng hỏi.** Làm thẳng trên nhánh hiện tại.
- **Đóng change bằng CLI:** `openspec archive <name>`. Không dùng `/opsx:sync` — đó là
  đường merge do agent tự làm, không có chốt chặn mất scenario.
- **Archive TRƯỚC khi** gọi `superpowers:finishing-a-development-branch`.
- **ADDED nghĩa là "chưa có trong spec", không phải "chưa có trong code."** Repo này có
  code chạy lâu rồi nhưng `openspec/specs/` mới bắt đầu từ con số không, nên gần như mọi
  delta đầu tiên của một capability đều là ADDED. Dùng MODIFIED cho thứ chưa có trong
  spec chính sẽ khiến `openspec archive` báo lỗi cứng — và chỉ báo lúc archive, tức là
  sau khi đã code xong.
- **Không back-fill spec.** Không dựng lại spec cho phần code đã có. Chỉ viết spec cho
  thứ bạn sắp thay đổi.
- **Spec Kit đã được gỡ khỏi repo này** (`.specify/`, `.agents/skills/speckit-*`). Đừng
  gọi `/speckit.*` và đừng tìm `.specify/memory/constitution.md` — nội dung constitution
  đã chuyển sang `openspec/config.yaml`.

### Test cũ chưa có lưới an toàn

Khi sửa code chưa có test, khai loại test **trước khi chạy**:

- **SPEC TEST** dẫn dắt hành vi mới — **phải fail trước**. Pass ngay là test hỏng.
- **CHARACTERIZATION TEST** ghim hành vi đã có — **phải pass trước**. Pass ngay là **điều
  kiện thành công**, không phải red flag. Iron Law chi phối việc sinh production code;
  viết characterization test không sinh production code nên không kích hoạt nó. Kiểm
  chứng bằng cách cố tình làm hỏng production code, xem test fail, rồi hoàn tác.

Không được đổi một spec test thành characterization test **sau khi** thấy nó pass.
