import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Tuple
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from pillow_heif import register_heif_opener
from PIL import Image, PngImagePlugin, ImageColor

HEIC_EXTS = {".heic", ".heif"}

# -------------------- CORE LOGIC --------------------
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

def _contain_size(ow: int, oh: int, tw: int, th: int, avoid_upscale: bool) -> Tuple[int, int]:
    sx, sy = tw / ow, th / oh
    s = min(sx, sy)
    if avoid_upscale:
        s = min(s, 1.0)
    return max(1, int(round(ow * s))), max(1, int(round(oh * s)))

def _resize_fit(img, tw: Optional[int], th: Optional[int], avoid_upscale: bool):
    ow, oh = img.size
    if not tw and not th:
        return img
    if not tw:
        tw = int(round(ow * (th / oh)))
    if not th:
        th = int(round(oh * (tw / ow)))
    nw, nh = _contain_size(ow, oh, tw, th, avoid_upscale)
    if (nw, nh) == (ow, oh):
        return img
    return img.resize((nw, nh), Image.Resampling.LANCZOS)

def _resize_stretch(img, tw: int, th: int):
    return img.resize((tw, th), Image.Resampling.LANCZOS)

def _pad_to_size(img, tw: int, th: int, bg: str, avoid_upscale: bool):
    ow, oh = img.size
    nw, nh = _contain_size(ow, oh, tw, th, avoid_upscale)
    if (nw, nh) != (ow, oh):
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    try:
        rgb = ImageColor.getrgb(bg)
    except Exception:
        rgb = (255, 255, 255)
    mode = "RGBA" if img.mode in ("RGBA", "LA") else "RGB"
    canvas = Image.new(mode, (tw, th), rgb if mode == "RGB" else (rgb[0], rgb[1], rgb[2], 255))
    canvas.paste(img, ((tw - img.width)//2, (th - img.height)//2))
    return canvas

def _convert_one(in_path, out_path, cl=0, mode="keep", tw=None, th=None, avoid=True, bg="#FFFFFF"):
    with Image.open(in_path) as img:
        if mode == "fit":
            img = _resize_fit(img, tw, th, avoid)
        elif mode == "stretch" and tw and th:
            img = _resize_stretch(img, tw, th)
        elif mode == "pad" and tw and th:
            img = _pad_to_size(img, tw, th, bg, avoid)
        # keep -> không đổi

        exif, icc = img.info.get("exif"), img.info.get("icc_profile")
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("Converted-From", os.path.basename(in_path))
        img.save(
            out_path,
            format="PNG",
            compress_level=int(cl),  # 0..9 (lossless)
            pnginfo=pnginfo,
            exif=exif if exif else None,
            icc_profile=icc if icc else None,
        )

def _next_index_dir(base, prefix):
    os.makedirs(base, exist_ok=True)
    i = 1
    while True:
        p = os.path.join(base, f"{prefix}{i}")
        if not os.path.exists(p):
            os.makedirs(p)
            return p
        i += 1

def convert_heic_folder_to_png_gui(inp, outb, pref, rec, cl, mode, tw, th, avoid, bg,
                                   stop_event: threading.Event,
                                   progress_callback=None, done_callback=None, error_callback=None):
    """
    Đa luồng + hỗ trợ Stop (graceful): dừng xếp job mới, hủy job chưa chạy; job đang chạy kết thúc rồi dừng.
    """
    outdir = None
    try:
        register_heif_opener()
        if not os.path.isdir(inp):
            raise NotADirectoryError("INPUT_ROOT không tồn tại.")
        outdir = _next_index_dir(outb, pref)

        files = _gather_heic_files(inp, rec)
        total = len(files)
        if total == 0:
            raise FileNotFoundError("Không tìm thấy ảnh HEIC.")
        if progress_callback:
            progress_callback(0, total, f"Bắt đầu… (0/{total})\nOutput: {outdir}")

        done = 0
        max_workers = min(32, (os.cpu_count() or 4) + 4)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = []
            for f in files:
                if stop_event.is_set():
                    break
                out_path = _rel_output_path(f, inp, outdir)
                if os.path.exists(out_path):
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, f"Bỏ qua (đã có): {os.path.basename(out_path)}")
                    continue
                futures.append(ex.submit(_convert_one, f, out_path, cl, mode, tw, th, avoid, bg))

            if stop_event.is_set():
                ex.shutdown(wait=False, cancel_futures=True)

            for fut in as_completed(futures):
                if stop_event.is_set():
                    break
                try:
                    fut.result()
                except Exception as e:
                    if error_callback:
                        error_callback(str(e))
                finally:
                    done += 1
                    if progress_callback:
                        progress_callback(done, total, f"Đã xử lý: {done}/{total}")

        if stop_event.is_set():
            if progress_callback:
                progress_callback(done, total, f"Đã dừng: {done}/{total}")
            if done_callback:
                done_callback(outdir)
            return

        if done_callback:
            done_callback(outdir)

    except Exception as e:
        if error_callback:
            error_callback(str(e))
        if done_callback:
            done_callback(outdir)

# -------------------- GUI --------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HEIC → PNG Converter Tool Chain")
        # Tăng kích thước cửa sổ để không che nút Browse/Stop/Progress:
        self.geometry("950x550")
        self.resizable(False, False)  # Cố định để không bị thu nhỏ mất nút

        # ==== Variables ====
        self.var_input = tk.StringVar(value=r"C:\Users\NguyenBao\Pictures\Data_Final_Prj")
        self.var_output = tk.StringVar(value=r"C:\Users\NguyenBao\Pictures")
        self.var_prefix = tk.StringVar(value="ConvertToPNGOutput")
        self.var_recursive = tk.BooleanVar(value=True)
        self.var_compress = tk.IntVar(value=0)

        self.var_mode = tk.StringVar(value="keep")       # keep | fit | stretch | pad
        self.var_no_upscale = tk.BooleanVar(value=True)
        self.var_width = tk.StringVar(value="")
        self.var_height = tk.StringVar(value="")
        self.var_pad_color = tk.StringVar(value="#FFFFFF")

        # progress anim
        self._anim_value = 0.0      # 0..1000
        self._anim_target = 0.0     # 0..1000
        self._anim_job = None
        self._indeterminate = False

        # stop control
        self._stop_event = None

        # ==== Build UI ====
        self._build_form()
        self._build_scale_section()
        self._build_buttons_row()   # Convert + Stop
        self._build_progress()

    # ---------- General Form ----------
    def _build_form(self):
        ttk.Label(self, text="INPUT_ROOT:").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 0))
        f1 = ttk.Frame(self); f1.grid(row=1, column=0, padx=12, sticky="we")
        f1.columnconfigure(0, weight=1)
        ttk.Entry(f1, textvariable=self.var_input).grid(row=0, column=0, sticky="we")
        ttk.Button(f1, text="Browse", command=self._browse_input, width=10).grid(row=0, column=1, padx=8)

        ttk.Label(self, text="OUTPUT_BASE:").grid(row=2, column=0, sticky="w", padx=12, pady=(8, 0))
        f2 = ttk.Frame(self); f2.grid(row=3, column=0, padx=12, sticky="we")
        f2.columnconfigure(0, weight=1)
        ttk.Entry(f2, textvariable=self.var_output).grid(row=0, column=0, sticky="we")
        ttk.Button(f2, text="Browse", command=self._browse_output, width=10).grid(row=0, column=1, padx=8)

        ttk.Label(self, text="OUTPUT_PREFIX:").grid(row=4, column=0, sticky="w", padx=12, pady=(8, 0))
        ttk.Entry(self, textvariable=self.var_prefix).grid(row=5, column=0, padx=12, sticky="we")

        f3 = ttk.Frame(self); f3.grid(row=6, column=0, padx=12, sticky="we", pady=6)
        ttk.Checkbutton(f3, text="Recursive", variable=self.var_recursive).grid(row=0, column=0, sticky="w")
        ttk.Label(f3, text="Compress level:").grid(row=0, column=1, sticky="e", padx=8)
        ttk.Spinbox(f3, from_=0, to=9, width=5, textvariable=self.var_compress).grid(row=0, column=2, sticky="w")

    # ---------- Scale Section ----------
    def _build_scale_section(self):
        ttk.Separator(self, orient="horizontal").grid(row=7, column=0, sticky="we", padx=12, pady=(10, 6))
        frm = ttk.LabelFrame(self, text="Scale ảnh"); frm.grid(row=8, column=0, padx=12, sticky="we")

        # Row 0: chế độ
        mode_frame = ttk.Frame(frm); mode_frame.grid(row=0, column=0, columnspan=4, sticky="we", pady=(6, 4))
        ttk.Label(mode_frame, text="Chế độ:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        for c in range(4):
            mode_frame.columnconfigure(c + 1, weight=1, uniform="scale_modes")

        opts = [
            ("Giữ nguyên", "keep"),
            ("Fit within (giữ tỉ lệ)", "fit"),
            ("Exact (kéo dãn)", "stretch"),
            ("Pad to size (không méo)", "pad"),
        ]
        for i, (text, value) in enumerate(opts):
            ttk.Radiobutton(
                mode_frame, text=text, value=value,
                variable=self.var_mode, command=self._on_mode_change
            ).grid(row=0, column=i + 1, sticky="w", padx=8)

        # Row 1: width / height
        ttk.Label(frm, text="Width(px):").grid(row=1, column=0, sticky="e", padx=(10, 6))
        self.ent_w = ttk.Entry(frm, textvariable=self.var_width, width=10)
        self.ent_w.grid(row=1, column=1, sticky="w")
        ttk.Label(frm, text="Height(px):").grid(row=1, column=2, sticky="e", padx=(20, 6))
        self.ent_h = ttk.Entry(frm, textvariable=self.var_height, width=10)
        self.ent_h.grid(row=1, column=3, sticky="w")

        # Row 2: no-upscale
        self.chk_no_up = ttk.Checkbutton(frm, text="Không upscale (không phóng lớn)", variable=self.var_no_upscale)
        self.chk_no_up.grid(row=2, column=0, columnspan=4, sticky="w", padx=10, pady=(2, 6))

        # Row 3: pad color
        self.frm_pad = ttk.Frame(frm); self.frm_pad.grid(row=3, column=0, columnspan=4, sticky="w", padx=10, pady=(0, 6))
        ttk.Label(self.frm_pad, text="Màu nền:").grid(row=0, column=0, sticky="w")
        self.lbl_color = ttk.Label(self.frm_pad, textvariable=self.var_pad_color, relief="groove", width=12)
        self.lbl_color.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(self.frm_pad, text="Chọn", command=self._pick_color, width=8).grid(row=0, column=2, padx=6)

        self._on_mode_change()

    # ---------- Buttons Row (Convert + Stop) ----------
    def _build_buttons_row(self):
        row = ttk.Frame(self)
        row.grid(row=9, column=0, sticky="we", padx=12, pady=(12, 0))
        row.columnconfigure(0, weight=0)
        row.columnconfigure(1, weight=1)

        self.btn_convert = ttk.Button(row, text="Convert", command=self._on_convert)
        self.btn_convert.grid(row=0, column=0, sticky="w")

        self.btn_stop = ttk.Button(row, text="Stop", command=self._on_stop, state="disabled")
        self.btn_stop.grid(row=0, column=1, sticky="e")

    # ---------- Progress (smooth) ----------
    def _build_progress(self):
        ttk.Label(self, text="Tiến trình:").grid(row=10, column=0, sticky="w", padx=12, pady=(14, 0))
        # Tăng chiều dài để luôn hiển thị đầy đủ trong cửa sổ lớn
        self.prog = ttk.Progressbar(self, orient="horizontal", mode="determinate", maximum=1000, length=900)
        self.prog.grid(row=11, column=0, padx=12, sticky="we")
        self.lbl = ttk.Label(self, text="Sẵn sàng.")
        self.lbl.grid(row=12, column=0, sticky="w", padx=12, pady=(6, 12))

    # ---------- Mode / Color ----------
    def _pick_color(self):
        color, _ = colorchooser.askcolor(color=self.var_pad_color.get())
        if color:
            self.var_pad_color.set('#%02x%02x%02x' % (int(color[0]), int(color[1]), int(color[2])))

    def _on_mode_change(self):
        m = self.var_mode.get()
        def set_state(w, on):
            try:
                w.config(state="normal" if on else "disabled")
            except tk.TclError:
                pass
        set_state(self.ent_w, m != "keep")
        set_state(self.ent_h, m != "keep")
        set_state(self.chk_no_up, m in ("fit", "pad"))
        for ch in self.frm_pad.winfo_children():
            set_state(ch, m == "pad")

    # ---------- Convert / Stop ----------
    def _on_convert(self):
        i  = self.var_input.get().strip()
        o  = self.var_output.get().strip()
        pf = self.var_prefix.get().strip() or "ConvertToPNGOutput"
        rec = bool(self.var_recursive.get())
        cl  = int(self.var_compress.get())

        mode = self.var_mode.get()
        avoid = bool(self.var_no_upscale.get())
        tw = int(self.var_width.get()) if self.var_width.get().isdigit() else None
        th = int(self.var_height.get()) if self.var_height.get().isdigit() else None
        bg = self.var_pad_color.get().strip() or "#FFFFFF"

        if not i or not o:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn INPUT_ROOT và OUTPUT_BASE."); return
        if mode == "fit" and not (tw or th):
            messagebox.showwarning("Thiếu thông tin", "Nhập Width hoặc Height cho Fit within."); return
        if mode in ("stretch", "pad") and (not tw or not th):
            messagebox.showwarning("Thiếu thông tin", "Nhập đủ Width và Height cho chế độ này."); return

        # Stop event & UI
        self._stop_event = threading.Event()
        self._lock_ui(True)
        self.btn_stop.configure(state="normal", text="Stop")
        self._set_status("Đang xử lý…")
        self._start_indeterminate()

        threading.Thread(
            target=convert_heic_folder_to_png_gui,
            args=(i, o, pf, rec, cl, mode, tw, th, avoid, bg, self._stop_event),
            kwargs=dict(progress_callback=self._on_progress,
                        done_callback=self._on_done,
                        error_callback=self._on_error),
            daemon=True
        ).start()

    def _on_stop(self):
        if self._stop_event and not self._stop_event.is_set():
            self._stop_event.set()
            self.btn_stop.configure(text="Stopping…", state="disabled")
            self._set_status("Đang dừng… chờ file đang xử lý hoàn tất.")

    # ---------- Smooth progress internals ----------
    def _start_indeterminate(self):
        if not self._indeterminate:
            self._indeterminate = True
            self.prog.configure(mode="indeterminate", maximum=100)
            self.prog.start(10)
            self._anim_value = 0.0
            self._anim_target = 0.0

    def _stop_indeterminate(self):
        if self._indeterminate:
            self._indeterminate = False
            self.prog.stop()
            self.prog.configure(mode="determinate", maximum=1000)

    def _animate_progress(self):
        if self._indeterminate:
            return
        delta = self._anim_target - self._anim_value
        if abs(delta) < 0.5:
            self._anim_value = self._anim_target
            self.prog["value"] = self._anim_value
            self._anim_job = None
            return
        self._anim_value += delta * 0.2  # easing
        self.prog["value"] = self._anim_value
        self._anim_job = self.after(16, self._animate_progress)  # ~60 FPS

    def _on_progress(self, done, total, msg):
        def update():
            if self._indeterminate:
                self._stop_indeterminate()
            pct = 0 if total <= 0 else max(0.0, min(1.0, done / total))
            self._anim_target = pct * 1000.0
            if self._anim_job is None:
                self._anim_job = self.after(16, self._animate_progress)
            self._set_status(msg)
        self.after(0, update)

    def _on_done(self, outdir):
        def finish():
            self._stop_indeterminate()
            self._anim_target = 1000.0
            if self._anim_job is None:
                self._anim_job = self.after(16, self._animate_progress)
            self._lock_ui(False)
            self.btn_stop.configure(state="disabled", text="Stop")
            if outdir:
                self._set_status(f"Hoàn tất. Kết quả: {outdir}")
                messagebox.showinfo("Hoàn tất", f"Đã lưu vào:\n{outdir}")
            else:
                self._set_status("Kết thúc với lỗi.")
        self.after(0, finish)

    def _on_error(self, err_msg):
        self.after(0, lambda: messagebox.showerror("Lỗi", err_msg))

    # ---------- UI helpers ----------
    def _lock_ui(self, lock: bool):
        state = "disabled" if lock else "normal"
        for w in self.winfo_children():
            try:
                if w in (self.prog, self.lbl):
                    continue
                w.configure(state=state)
            except tk.TclError:
                pass
        if lock:
            self.btn_stop.configure(state="normal")
            self.btn_convert.configure(state="disabled")
        else:
            self.btn_stop.configure(state="disabled")
            self.btn_convert.configure(state="normal")

    def _set_status(self, s: str):
        self.lbl.configure(text=s)

    # ---------- Browse ----------
    def _browse_input(self):
        p = filedialog.askdirectory(title="Chọn INPUT_ROOT")
        if p:
            self.var_input.set(p)

    def _browse_output(self):
        p = filedialog.askdirectory(title="Chọn OUTPUT_BASE")
        if p:
            self.var_output.set(p)

# -------------------- MAIN --------------------
if __name__ == "__main__":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)  # sharpen on HiDPI
    except Exception:
        pass
    App().mainloop()
