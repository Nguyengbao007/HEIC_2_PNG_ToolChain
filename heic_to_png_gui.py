import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pillow_heif import register_heif_opener
from PIL import Image, PngImagePlugin

HEIC_EXTS = {".heic", ".heif"}

# -------------------- CORE CONVERSION LOGIC --------------------
def _is_heic(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in HEIC_EXTS

def _gather_heic_files(input_folder: str, recursive: bool = False) -> List[str]:
    if not recursive:
        try:
            return [
                os.path.join(input_folder, f)
                for f in os.listdir(input_folder)
                if _is_heic(f)
            ]
        except FileNotFoundError:
            return []
    heics = []
    for root, _, files in os.walk(input_folder):
        for f in files:
            if _is_heic(f):
                heics.append(os.path.join(root, f))
    return heics

def _rel_output_path(input_path: str, input_folder: str, output_folder: str) -> str:
    rel = os.path.relpath(input_path, input_folder)
    rel_base, _ = os.path.splitext(rel)
    out_path = os.path.join(output_folder, rel_base + ".png")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    return out_path

def _convert_one(in_path: str, out_path: str, compress_level: int = 0) -> None:
    with Image.open(in_path) as img:
        exif = img.info.get("exif")
        icc  = img.info.get("icc_profile")

        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("Converted-From", os.path.basename(in_path))

        save_kwargs = {
            "format": "PNG",
            "compress_level": int(compress_level),  # 0..9 (PNG luôn lossless)
            "optimize": False,
            "pnginfo": pnginfo,
        }
        if exif: save_kwargs["exif"] = exif
        if icc:  save_kwargs["icc_profile"] = icc

        img.save(out_path, **save_kwargs)

def _next_index_output_dir(base_dir: str, prefix: str) -> str:
    os.makedirs(base_dir, exist_ok=True)
    idx = 1
    while True:
        candidate = os.path.join(base_dir, f"{prefix}{idx}")
        if not os.path.exists(candidate):
            os.makedirs(candidate, exist_ok=True)
            return candidate
        idx += 1

def convert_heic_folder_to_png_gui(
    input_folder: str,
    output_base: str,
    output_prefix: str,
    recursive: bool,
    compress_level: int,
    workers: int = None,
    progress_callback=None,
    done_callback=None,
    error_callback=None,
):
    """
    Chạy trong thread nền: chuyển HEIC -> PNG (lossless) vào thư mục ConvertToPNGOutput*index
    và báo tiến độ qua progress_callback(done, total, msg). Không chạm UI trực tiếp!
    """
    try:
        register_heif_opener()

        if not input_folder or not os.path.isdir(input_folder):
            raise NotADirectoryError("INPUT_ROOT không tồn tại hoặc không phải thư mục.")

        if not output_base:
            raise NotADirectoryError("OUTPUT_BASE không được để trống.")

        output_dir = _next_index_output_dir(output_base, output_prefix)

        files = _gather_heic_files(input_folder, recursive=recursive)
        total = len(files)
        if total == 0:
            raise FileNotFoundError("Không tìm thấy ảnh HEIC/HEIF trong thư mục nguồn.")

        if workers is None:
            cpu = os.cpu_count() or 4
            workers = min(32, cpu + 4)

        done = 0
        if progress_callback:
            progress_callback(done, total, f"Bắt đầu… (0/{total})\nOutput: {output_dir}")

        tasks = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for in_path in files:
                out_path = _rel_output_path(in_path, input_folder, output_dir)
                if os.path.exists(out_path):
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, f"Bỏ qua (đã có): {os.path.basename(out_path)}")
                    continue
                tasks.append(ex.submit(_convert_one, in_path, out_path, compress_level))

            for fut in as_completed(tasks):
                try:
                    fut.result()
                except Exception as e:
                    if error_callback:
                        error_callback(str(e))
                finally:
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, f"Đã xử lý: {done}/{total}")

        if done_callback:
            done_callback(output_dir)

    except Exception as e:
        if error_callback:
            error_callback(str(e))
        if done_callback:
            done_callback(None)

# -------------------- TKINTER GUI --------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEIC → PNG Converter (Lossless) - Tkinter")
        self.geometry("760x420")
        self.resizable(False, False)

        # --- Variables ---
        self.var_input   = tk.StringVar(value=r"C:\Users\NguyenBao\Pictures\Data_Final_Prj")
        self.var_output  = tk.StringVar(value=r"C:\Users\NguyenBao\Pictures")
        self.var_prefix  = tk.StringVar(value="ConvertToPNGOutput")
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_compress  = tk.IntVar(value=0)

        # --- Layout config ---
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self._build_form()
        self._build_progress()

        self._bg_thread = None

    # ========== GUI FORM ==========
    def _build_form(self):
        pad_y = 5

        # --- INPUT_ROOT ---
        ttk.Label(self, text="INPUT_ROOT (thư mục chứa HEIC):").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))
        frm_input = ttk.Frame(self)
        frm_input.grid(row=1, column=0, columnspan=2, sticky="we", padx=10, pady=(0, pad_y))
        frm_input.columnconfigure(0, weight=1)
        ttk.Entry(frm_input, textvariable=self.var_input).grid(row=0, column=0, sticky="we")
        ttk.Button(frm_input, text="Browse…", command=self._browse_input, width=10).grid(row=0, column=1, padx=(8, 0))

        # --- OUTPUT_BASE ---
        ttk.Label(self, text="OUTPUT_BASE (thư mục tạo ConvertToPNGOutput*index):").grid(row=2, column=0, sticky="w", padx=10, pady=(10, 0))
        frm_output = ttk.Frame(self)
        frm_output.grid(row=3, column=0, columnspan=2, sticky="we", padx=10, pady=(0, pad_y))
        frm_output.columnconfigure(0, weight=1)
        ttk.Entry(frm_output, textvariable=self.var_output).grid(row=0, column=0, sticky="we")
        ttk.Button(frm_output, text="Browse…", command=self._browse_output, width=10).grid(row=0, column=1, padx=(8, 0))

        # --- OUTPUT_PREFIX ---
        ttk.Label(self, text="OUTPUT_PREFIX (tiền tố thư mục output):").grid(row=4, column=0, sticky="w", padx=10, pady=(10, 0))
        ttk.Entry(self, textvariable=self.var_prefix, width=40).grid(row=5, column=0, sticky="we", padx=10, pady=(0, pad_y))

        # --- OPTIONS ---
        frm_opts = ttk.Frame(self)
        frm_opts.grid(row=6, column=0, columnspan=2, sticky="we", padx=10, pady=(5, 0))
        ttk.Checkbutton(frm_opts, text="Quét cả thư mục con (Recursive)", variable=self.var_recursive).grid(row=0, column=0, sticky="w")
        ttk.Label(frm_opts, text="Compress level (0–9):").grid(row=0, column=1, sticky="e", padx=(20, 6))
        ttk.Spinbox(frm_opts, from_=0, to=9, textvariable=self.var_compress, width=5).grid(row=0, column=2, sticky="w")

        # --- Convert button ---
        self.btn_convert = ttk.Button(self, text="Convert", command=self._on_convert)
        self.btn_convert.grid(row=7, column=0, sticky="w", padx=10, pady=(15, 0))

    # ========== PROGRESS AREA ==========
    def _build_progress(self):
        ttk.Label(self, text="Tiến trình:").grid(row=8, column=0, sticky="w", padx=10, pady=(15, 0))
        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate", length=720)
        self.progress.grid(row=9, column=0, columnspan=2, sticky="we", padx=10, pady=(2, 5))
        self.lbl_status = ttk.Label(self, text="Sẵn sàng.")
        self.lbl_status.grid(row=10, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 10))

    # ---------- Browse buttons ----------
    def _browse_input(self):
        path = filedialog.askdirectory(title="Chọn INPUT_ROOT")
        if path:
            self.var_input.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Chọn OUTPUT_BASE")
        if path:
            self.var_output.set(path)

    # ---------- Convert handling ----------
    def _on_convert(self):
        input_root  = self.var_input.get().strip()
        output_base = self.var_output.get().strip()
        prefix      = self.var_prefix.get().strip() or "ConvertToPNGOutput"
        recursive   = bool(self.var_recursive.get())
        compress    = int(self.var_compress.get())

        if not input_root:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn/thêm INPUT_ROOT.")
            return
        if not output_base:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn/thêm OUTPUT_BASE.")
            return

        # Khóa UI và bắt đầu luồng nền
        self._start_conversion(input_root, output_base, prefix, recursive, compress)

    # ---------- THREAD & UI HELPERS ----------
    def _start_conversion(self, input_root, output_base, prefix, recursive, compress):
        self._set_ui_state(disabled=True)
        self.progress.configure(value=0, maximum=100)
        self._set_status("Đang chuẩn bị…")

        self._bg_thread = threading.Thread(
            target=convert_heic_folder_to_png_gui,
            args=(input_root, output_base, prefix, recursive, compress),
            kwargs=dict(
                progress_callback=self._on_progress,
                done_callback=self._on_done,
                error_callback=self._on_error
            ),
            daemon=True
        )
        self._bg_thread.start()

    def _set_ui_state(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        for child in self.winfo_children():
            try:
                if child is self.progress or child is self.lbl_status:
                    continue
                child.configure(state=state)
            except tk.TclError:
                pass
        if disabled:
            self.btn_convert.configure(state="disabled")
        else:
            self.btn_convert.configure(state="normal")

    # callbacks từ thread nền -> dùng after để an toàn
    def _on_progress(self, done, total, msg: str):
        def update_ui():
            pct = int(done * 100 / total) if total > 0 else 0
            pct = max(0, min(100, pct))
            self.progress.configure(maximum=100, value=pct)
            self._set_status(msg)
        self.after(0, update_ui)

    def _on_done(self, output_dir):
        def finalize():
            self._set_ui_state(disabled=False)
            if output_dir:
                self.progress.configure(value=100)
                self._set_status(f"Hoàn tất! Kết quả: {output_dir}")
                messagebox.showinfo("Xong", f"Chuyển đổi hoàn tất.\nOutput: {output_dir}")
            else:
                self._set_status("Kết thúc với lỗi.")
        self.after(0, finalize)

    def _on_error(self, err_msg: str):
        def show_err():
            messagebox.showerror("Lỗi", err_msg)
        self.after(0, show_err)

    def _set_status(self, text: str):
        self.lbl_status.configure(text=text)

# -------------------- MAIN --------------------
if __name__ == "__main__":
    # Tránh mờ trên màn hình HiDPI (Windows)
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = App()
    app.mainloop()
