import os
import queue
import re
import shutil
import subprocess
import threading

import customtkinter as ctk
from yt_dlp import YoutubeDL

# Aparencia e tema
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FFMPEG_FALLBACK = (
    r"C:\Users\anton\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
)


class DownloadCancelled(Exception):
    """Sinaliza cancelamento manual do download."""


def get_ffmpeg_path():
    """Retorna (caminho, origem) ou (None, None) se nao encontrado."""
    path = None
    source = None

    if os.environ.get("FFMPEG_PATH"):
        path = os.environ["FFMPEG_PATH"]
        source = "Variavel de Ambiente"
    elif shutil.which("ffmpeg"):
        path = shutil.which("ffmpeg")
        source = "Path do Sistema"
    elif os.path.exists(FFMPEG_FALLBACK):
        path = FFMPEG_FALLBACK
        source = "Caminho WinGet"
    else:
        try:
            import imageio_ffmpeg
            path = imageio_ffmpeg.get_ffmpeg_exe()
            source = "imageio-ffmpeg"
        except Exception:
            pass

    if path:
        try:
            proc = subprocess.run([path, "-version"], capture_output=True)
            if proc.returncode == 0:
                return path, source
        except Exception:
            pass
    return None, None


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Youtube Downloader")
        self.geometry("760x500")
        self.resizable(False, False)
        self.configure(fg_color="#0F172A")

        self._download_thread = None
        self._quality_thread = None
        self._ffmpeg, self._ffmpeg_source = get_ffmpeg_path()
        self._queue = queue.Queue()
        self._polling = False
        self._quality_map = {}
        self._media_type = "Video"
        self._url_debounce_job = None
        self._last_quality_request = (None, None)
        self._is_downloading = False
        self._terminal_state = False
        self._active_download_id = 0
        self._cancel_requested = False
        self._partial_files = set()

        self._status_colors = {
            "idle": "#94A3B8",
            "running": "#60A5FA",
            "ok": "#34D399",
            "error": "#F87171",
            "warning": "#FBBF24",
        }

        self._build_ui()
        self.bind("<Return>", lambda _event: self._start_download())

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(
            self,
            corner_radius=16,
            fg_color="#111827",
            border_width=1,
            border_color="#1F2937",
        )
        card.grid(row=0, column=0, padx=18, pady=12, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            card,
            text="Youtube Downloader",
            font=ctk.CTkFont(size=21, weight="bold"),
            text_color="#E2E8F0",
        )
        title.grid(row=0, column=0, pady=(10, 0))

        subtitle = ctk.CTkLabel(
            card,
            text="Baixe audio e videos do YouTube de forma simples",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
        )
        subtitle.grid(row=1, column=0, pady=(0, 8))

        frame_url = ctk.CTkFrame(card, fg_color="transparent")
        frame_url.grid(row=2, column=0, padx=20, sticky="ew")
        frame_url.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame_url,
            text="URL do video",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.url_entry = ctk.CTkEntry(
            frame_url,
            placeholder_text="https://www.youtube.com/watch?v=...",
            height=32,
            font=ctk.CTkFont(size=12),
            border_width=1,
            border_color="#334155",
            fg_color="#0B1220",
            text_color="#E2E8F0",
        )
        self.url_entry.grid(row=1, column=0, sticky="ew")
        self.url_entry.bind("<KeyRelease>", self._on_url_change)
        self.url_entry.bind("<FocusOut>", self._on_url_change)
        self.url_entry.bind("<<Paste>>", self._on_url_paste)
        self.url_entry.bind("<Control-v>", self._on_url_paste)

        self._build_quality_section(card)
        self._set_media_controls_enabled(False)

        frame_name = ctk.CTkFrame(card, fg_color="transparent")
        frame_name.grid(row=4, column=0, padx=20, sticky="ew", pady=(6, 0))
        frame_name.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame_name,
            text="Nome do arquivo (opcional)",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.name_entry = ctk.CTkEntry(
            frame_name,
            placeholder_text="Deixe em branco para usar o titulo do video",
            height=32,
            font=ctk.CTkFont(size=12),
            border_width=1,
            border_color="#334155",
            fg_color="#0B1220",
            text_color="#E2E8F0",
        )
        self.name_entry.grid(row=1, column=0, sticky="ew")

        frame_out = ctk.CTkFrame(card, fg_color="transparent")
        frame_out.grid(row=5, column=0, padx=20, sticky="ew", pady=(6, 0))
        frame_out.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame_out,
            text="Pasta de destino",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        row_dir = ctk.CTkFrame(frame_out, fg_color="transparent")
        row_dir.grid(row=1, column=0, sticky="ew")
        row_dir.grid_columnconfigure(0, weight=1)

        self.dir_entry = ctk.CTkEntry(
            row_dir,
            placeholder_text="downloads",
            height=32,
            font=ctk.CTkFont(size=12),
            border_width=1,
            border_color="#334155",
            fg_color="#0B1220",
            text_color="#E2E8F0",
        )
        self.dir_entry.insert(0, "downloads")
        self.dir_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            row_dir,
            text="Procurar",
            width=84,
            height=32,
            command=self._browse_dir,
            fg_color="#1D4ED8",
            hover_color="#1E40AF",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        browse_btn.grid(row=0, column=1)
        self.browse_btn = browse_btn

        frame_progress = ctk.CTkFrame(card, fg_color="transparent")
        frame_progress.grid(row=6, column=0, padx=20, sticky="ew", pady=(8, 0))
        frame_progress.grid_columnconfigure(0, weight=1)

        row_pct = ctk.CTkFrame(frame_progress, fg_color="transparent")
        row_pct.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        row_pct.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            row_pct,
            text="Pronto para iniciar",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._status_colors["idle"],
        )
        self.status_label.grid(row=0, column=0, sticky="w")

        self.pct_label = ctk.CTkLabel(
            row_pct,
            text="0%",
            anchor="e",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        )
        self.pct_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(
            frame_progress,
            height=8,
            corner_radius=6,
            fg_color="#1F2937",
            progress_color="#2563EB",
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew")

        frame_actions = ctk.CTkFrame(card, fg_color="transparent")
        frame_actions.grid(row=7, column=0, padx=20, pady=(8, 4), sticky="ew")
        frame_actions.grid_columnconfigure(0, weight=1)
        frame_actions.grid_columnconfigure(1, weight=1)

        self.download_btn = ctk.CTkButton(
            frame_actions,
            text="Baixar video",
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start_download,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            text_color="#FFFFFF",
        )
        self.download_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.cancel_btn = ctk.CTkButton(
            frame_actions,
            text="Cancelar",
            height=34,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._cancel_download,
            fg_color="#B91C1C",
            hover_color="#991B1B",
            text_color="#FFFFFF",
            state="disabled",
        )
        self.cancel_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        if self._ffmpeg:
            ffmpeg_text = f"ffmpeg detectado via {self._ffmpeg_source}"
            ffmpeg_color = self._status_colors["ok"]
        else:
            ffmpeg_text = "ffmpeg nao encontrado - conversao de audio pode ser limitada"
            ffmpeg_color = self._status_colors["warning"]

        ctk.CTkLabel(
            card,
            text=ffmpeg_text,
            font=ctk.CTkFont(size=9),
            text_color=ffmpeg_color,
        ).grid(row=8, column=0, padx=20, pady=(0, 8), sticky="w")

    def _build_quality_section(self, card):
        frame_quality = ctk.CTkFrame(card, fg_color="transparent")
        frame_quality.grid(row=3, column=0, padx=20, sticky="ew", pady=(6, 0))
        frame_quality.grid_columnconfigure(0, weight=1)
        frame_quality.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame_quality,
            text="Tipo de download",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.quality_label = ctk.CTkLabel(
            frame_quality,
            text="Qualidade do video",
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#CBD5E1",
        )
        self.quality_label.grid(row=0, column=1, sticky="w", pady=(0, 6), padx=(8, 0))

        self.media_combo = ctk.CTkComboBox(
            frame_quality,
            values=["Video", "Audio"],
            height=32,
            state="disabled",
            command=self._on_media_type_change,
            border_width=1,
            border_color="#334155",
            fg_color="#0B1220",
            text_color="#E2E8F0",
            button_color="#1D4ED8",
            button_hover_color="#1E40AF",
        )
        self.media_combo.set("Video")
        self.media_combo.grid(row=1, column=0, sticky="ew", padx=(0, 6))

        self.quality_combo = ctk.CTkComboBox(
            frame_quality,
            values=["Melhor video"],
            height=32,
            font=ctk.CTkFont(size=12),
            border_width=1,
            border_color="#334155",
            fg_color="#0B1220",
            text_color="#E2E8F0",
            button_color="#1D4ED8",
            button_hover_color="#1E40AF",
            state="disabled",
        )
        self.quality_combo.set("Melhor video")
        self.quality_combo.grid(row=1, column=1, sticky="ew", padx=(6, 0))

    def _on_url_paste(self, _event=None):
        # Aguarda o texto colado entrar no campo antes de validar/carregar.
        self.after(50, self._on_url_change)

    def _on_url_change(self, _event=None):
        url = self.url_entry.get().strip()
        has_url = bool(url)
        self._set_media_controls_enabled(has_url)

        if self._url_debounce_job is not None:
            self.after_cancel(self._url_debounce_job)
            self._url_debounce_job = None

        if has_url and re.match(r"^https?://", url):
            self._url_debounce_job = self.after(350, lambda: self._load_qualities(show_warnings=False))

    def _set_media_controls_enabled(self, enabled):
        if enabled:
            self.media_combo.configure(state="readonly")
            self.quality_combo.configure(state="readonly")
            return

        self._quality_map = {}

        # Forca o valor padrao antes de bloquear para garantir texto visivel no startup.
        self.media_combo.configure(state="readonly")
        self.media_combo.set("Video")
        self.media_combo.configure(state="disabled")

        self.quality_label.configure(text="Qualidade do video")
        self.quality_combo.configure(state="readonly")
        self.quality_combo.configure(values=["Melhor video"])
        self.quality_combo.set("Melhor video")
        self.quality_combo.configure(state="disabled")

    def _on_media_type_change(self, value):
        self._media_type = value
        self._quality_map = {}

        if value == "Audio":
            self.quality_label.configure(text="Qualidade e formato do audio")
            self.quality_combo.configure(values=["Melhor audio (auto)"])
            self.quality_combo.set("Melhor audio (auto)")
        else:
            self.quality_label.configure(text="Qualidade do video")
            self.quality_combo.configure(values=["Melhor video"])
            self.quality_combo.set("Melhor video")

        self.download_btn.configure(text=self._download_button_text())
        self._load_qualities(show_warnings=False)

    def _browse_dir(self):
        from tkinter import filedialog

        folder = filedialog.askdirectory(title="Selecione a pasta de destino")
        if folder:
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, folder)

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Informe uma URL para continuar", text_color=self._status_colors["warning"])
            return
        if not re.match(r"^https?://", url):
            self.status_label.configure(text="URL invalida (use http:// ou https://)", text_color=self._status_colors["warning"])
            return
        if self._download_thread and self._download_thread.is_alive():
            return

        out_dir = self.dir_entry.get().strip() or "downloads"
        custom_name = self._sanitize_filename(self.name_entry.get().strip())
        media_type = self.media_combo.get().strip() or "Video"
        selected_quality = self.quality_combo.get().strip() or self._default_quality_label(media_type)
        selected_options = self._quality_map.get(selected_quality, self._default_format(media_type))

        if isinstance(selected_options, dict):
            format_selector = selected_options.get("format", self._default_format(media_type))
            audio_post = selected_options.get("audio_post")
        else:
            format_selector = selected_options
            audio_post = None

        self._is_downloading = True
        self._terminal_state = False
        self._active_download_id += 1
        download_id = self._active_download_id
        self._cancel_requested = False
        self._partial_files = set()
        self._drain_progress_queue()
        self._set_ui_locked(True)
        self.download_btn.configure(text="Baixando...", fg_color="#334155")
        self._reset_progress()

        self._polling = True
        self._poll_progress()

        self._download_thread = threading.Thread(
            target=self._run_download,
            args=(download_id, url, out_dir, custom_name, format_selector, media_type, audio_post),
            daemon=True,
        )
        self._download_thread.start()

    def _set_ui_locked(self, locked):
        if locked:
            self.url_entry.configure(state="disabled")
            self.name_entry.configure(state="disabled")
            self.dir_entry.configure(state="disabled")
            self.media_combo.configure(state="disabled")
            self.quality_combo.configure(state="disabled")
            self.browse_btn.configure(state="disabled")
            self.download_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
            return

        self.url_entry.configure(state="normal")
        self.name_entry.configure(state="normal")
        self.dir_entry.configure(state="normal")
        self.browse_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.download_btn.configure(state="normal", text=self._download_button_text(), fg_color="#2563EB")
        self._set_media_controls_enabled(bool(self.url_entry.get().strip()))

    def _cancel_download(self):
        if not self._is_downloading or self._cancel_requested:
            return

        self._cancel_requested = True
        self.cancel_btn.configure(state="disabled", text="Cancelando...")
        self.status_label.configure(
            text="Cancelando download e limpando arquivos...",
            text_color=self._status_colors["warning"],
        )

    def _sanitize_filename(self, value):
        # Remove caracteres invalidos no Windows para evitar falhas ao salvar.
        cleaned = re.sub(r'[<>:"/\\|?*]+', "", value or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
        return cleaned

    def _next_available_custom_name(self, out_dir, base_name):
        if not base_name:
            return base_name

        try:
            entries = os.listdir(out_dir)
        except Exception:
            return base_name

        used_stems = set()
        for entry in entries:
            name = entry
            for suffix in (".part", ".ytdl", ".temp"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
            stem, _ext = os.path.splitext(name)
            if stem:
                used_stems.add(stem)

        if base_name not in used_stems:
            return base_name

        index = 1
        while True:
            candidate = f"{base_name} ({index})"
            if candidate not in used_stems:
                return candidate
            index += 1

    def _parse_hook_percent(self, raw):
        if raw is None:
            return None

        if isinstance(raw, (int, float)):
            num = float(raw)
            return max(0.0, min(100.0, num * 100 if num <= 1 else num))

        if isinstance(raw, str):
            cleaned = raw.strip().replace("%", "").replace(",", ".")
            match = re.search(r"\d+(?:\.\d+)?", cleaned)
            if match:
                num = float(match.group(0))
                return max(0.0, min(100.0, num))

        return None

    def _network_ydl_opts(self):
        # Melhora resiliência contra timeout/intermitência de rede.
        return {
            "socket_timeout": 45,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 3,
        }

    def _friendly_error_message(self, err_text, prefix="Erro"):
        text = (err_text or "").replace("\n", " ").strip()
        low = text.lower()

        network_signals = [
            "timed out",
            "timeout",
            "connection reset",
            "connection aborted",
            "network is unreachable",
            "name resolution",
            "temporary failure in name resolution",
            "dns",
            "failed to establish a new connection",
            "max retries exceeded",
            "proxyerror",
            "ssl",
        ]

        if any(signal in low for signal in network_signals):
            return (
                f"{prefix}: Falha de rede ao conectar no YouTube. "
                "Tente novamente em instantes ou use outra rede."
            )

        if len(text) > 95:
            text = text[:95] + "..."
        return f"{prefix}: {text}"

    def _load_qualities(self, show_warnings=False):
        if self.media_combo.cget("state") == "disabled":
            return

        url = self.url_entry.get().strip()
        if not url:
            if show_warnings:
                self.status_label.configure(text="Informe uma URL antes de carregar qualidades", text_color=self._status_colors["warning"])
            return

        if not re.match(r"^https?://", url):
            if show_warnings:
                self.status_label.configure(text="URL invalida (use http:// ou https://)", text_color=self._status_colors["warning"])
            return

        media_type = self.media_combo.get().strip() or "Video"
        request_key = (url, media_type)
        if request_key == self._last_quality_request and self._quality_map:
            return

        if self._quality_thread and self._quality_thread.is_alive():
            return

        self._last_quality_request = request_key

        kind = "audio" if media_type == "Audio" else "video"
        self.status_label.configure(text=f"Carregando qualidades de {kind}...", text_color=self._status_colors["running"])

        self._quality_thread = threading.Thread(target=self._run_quality_fetch, args=(url, media_type), daemon=True)
        self._quality_thread.start()

    def _run_quality_fetch(self, url, media_type):
        opts = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
            "no_warnings": True,
        }
        opts.update(self._network_ydl_opts())

        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            labels, quality_map = self._extract_qualities(info or {}, media_type)
            self.after(0, self._on_qualities_loaded, labels, quality_map, media_type)
        except Exception as exc:
            self.after(0, self._on_qualities_error, str(exc))

    def _extract_qualities(self, info, media_type):
        if media_type == "Audio":
            labels = ["Melhor audio (auto)"]
            quality_map = {"Melhor audio (auto)": self._default_format("Audio")}

            if self._ffmpeg:
                labels.extend([
                    "MP3 - 320 kbps",
                    "MP3 - 192 kbps",
                    "M4A/AAC - 192 kbps",
                    "WAV - sem compressao",
                ])
                quality_map["MP3 - 320 kbps"] = {
                    "format": "bestaudio/best",
                    "audio_post": {"codec": "mp3", "quality": "320"},
                }
                quality_map["MP3 - 192 kbps"] = {
                    "format": "bestaudio/best",
                    "audio_post": {"codec": "mp3", "quality": "192"},
                }
                quality_map["M4A/AAC - 192 kbps"] = {
                    "format": "bestaudio/best",
                    "audio_post": {"codec": "aac", "quality": "192"},
                }
                quality_map["WAV - sem compressao"] = {
                    "format": "bestaudio/best",
                    "audio_post": {"codec": "wav", "quality": "0"},
                }

            formats = (info or {}).get("formats") or []
            audio_streams = []
            for fmt in formats:
                if fmt.get("acodec") in (None, "none"):
                    continue
                fmt_id = fmt.get("format_id")
                if not fmt_id:
                    continue
                ext = (fmt.get("ext") or "audio").upper()
                abr = fmt.get("abr")
                abr_val = int(round(abr)) if isinstance(abr, (int, float)) and abr > 0 else 0
                audio_streams.append((abr_val, ext, fmt_id))

            audio_streams.sort(key=lambda item: item[0], reverse=True)

            for abr_val, ext, fmt_id in audio_streams:
                if abr_val > 0:
                    base_label = f"STREAM {ext} - {abr_val} kbps"
                else:
                    base_label = f"STREAM {ext} - variavel"

                label = base_label
                if label in quality_map:
                    label = f"{base_label} ({fmt_id})"

                labels.append(label)
                quality_map[label] = f"{fmt_id}/bestaudio/best"

            return labels, quality_map

        labels = ["Melhor video"]
        quality_map = {"Melhor video": self._default_format("Video")}

        seen_heights = set()
        formats = (info or {}).get("formats") or []
        heights = []

        for fmt in formats:
            if fmt.get("vcodec") in (None, "none"):
                continue
            height = fmt.get("height")
            if isinstance(height, int) and height > 0 and height not in seen_heights:
                seen_heights.add(height)
                heights.append(height)

        heights.sort(reverse=True)

        for height in heights:
            label = f"{height}p"
            labels.append(label)
            quality_map[label] = self._format_for_height(height)

        return labels, quality_map

    def _on_qualities_loaded(self, labels, quality_map, media_type):
        self._quality_map = quality_map
        self.quality_combo.configure(values=labels)
        self.quality_combo.set(labels[0])

        kind = "audio" if media_type == "Audio" else "video"
        self.status_label.configure(
            text=f"{max(len(labels) - 1, 0)} opcoes de {kind} carregadas",
            text_color=self._status_colors["ok"],
        )

    def _on_qualities_error(self, err):
        self._last_quality_request = (None, None)
        self.status_label.configure(
            text=self._friendly_error_message(str(err), prefix="Nao foi possivel carregar qualidades"),
            text_color=self._status_colors["error"],
        )

    def _default_format(self, media_type=None):
        media_type = media_type or (self.media_combo.get().strip() if hasattr(self, "media_combo") else "Video")

        if media_type == "Audio":
            return "bestaudio/best"

        if self._ffmpeg:
            return "bestvideo+bestaudio/best"
        return "best[acodec!=none]/best"

    def _format_for_height(self, height):
        if self._ffmpeg:
            return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
        return f"best[height<={height}][acodec!=none]/best[acodec!=none]"

    def _default_quality_label(self, media_type):
        return "Melhor audio (auto)" if media_type == "Audio" else "Melhor video"

    def _download_button_text(self):
        if getattr(self, "media_combo", None) and self.media_combo.get() == "Audio":
            return "Baixar audio"
        return "Baixar video"

    def _run_download(self, download_id, url, out_dir, custom_name, format_selector, media_type, audio_post=None):
        os.makedirs(out_dir, exist_ok=True)
        if custom_name:
            safe_custom_name = self._next_available_custom_name(out_dir, custom_name)
            outtmpl = os.path.join(out_dir, f"{safe_custom_name}.%(ext)s")
        else:
            outtmpl = os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")

        processing_percent = 0.0

        def hook(d):
            if self._cancel_requested:
                raise DownloadCancelled("cancelled-by-user")

            status = d.get("status")
            filename = d.get("filename")
            tmpfilename = d.get("tmpfilename")
            if filename:
                self._partial_files.add(filename)
            if tmpfilename:
                self._partial_files.add(tmpfilename)

            if status == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                if total:
                    pct_val = downloaded / total
                    pct_str = f"{pct_val * 100:.1f}%"
                else:
                    pct_val = 0.0
                    pct_str = "..."
                self._queue.put((download_id, pct_val, pct_str, False))
            elif status == "finished":
                self._queue.put((download_id, 1.0, "100%", False))

        def post_hook(d):
            nonlocal processing_percent

            if self._cancel_requested:
                raise DownloadCancelled("cancelled-by-user")

            status = d.get("status")
            raw_percent = d.get("_percent_str") or d.get("percent") or d.get("progress")
            parsed_percent = self._parse_hook_percent(raw_percent)

            if status == "started":
                processing_percent = 0.0
            elif status == "finished":
                processing_percent = 100.0
            elif parsed_percent is not None:
                processing_percent = max(processing_percent, parsed_percent)
            else:
                # Fallback visual quando o hook nao informa percentual de processamento.
                processing_percent = min(processing_percent + 7.0, 99.0)

            overall_progress = min(0.90 + (processing_percent / 100.0) * 0.10, 1.0)
            pp_text = f"{processing_percent:.0f}%"
            self._queue.put((download_id, overall_progress, pp_text, True))

        if media_type == "Audio":
            ydl_opts = {
                "format": format_selector,
                "outtmpl": outtmpl,
                "progress_hooks": [hook],
                "postprocessor_hooks": [post_hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            ydl_opts.update(self._network_ydl_opts())
            if audio_post and self._ffmpeg:
                ydl_opts["ffmpeg_location"] = self._ffmpeg
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_post.get("codec", "mp3"),
                    "preferredquality": audio_post.get("quality", "192"),
                }]
        elif self._ffmpeg:
            ydl_opts = {
                "format": format_selector,
                "outtmpl": outtmpl,
                "merge_output_format": "mp4",
                "ffmpeg_location": self._ffmpeg,
                "progress_hooks": [hook],
                "postprocessor_hooks": [post_hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            ydl_opts.update(self._network_ydl_opts())
        else:
            ydl_opts = {
                "format": format_selector,
                "outtmpl": outtmpl,
                "progress_hooks": [hook],
                "postprocessor_hooks": [post_hook],
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
            }
            ydl_opts.update(self._network_ydl_opts())

        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Video")
            if self._cancel_requested:
                raise DownloadCancelled("cancelled-by-user")
            self.after(0, self._finish_polling, download_id)
            self.after(0, self._on_done, download_id, f'Download concluido: "{title}"')
        except DownloadCancelled:
            removed_count = self._cleanup_partial_files()
            self.after(0, self._finish_polling, download_id)
            self.after(0, self._on_cancelled, download_id, removed_count)
        except Exception as exc:
            if self._cancel_requested:
                removed_count = self._cleanup_partial_files()
                self.after(0, self._finish_polling, download_id)
                self.after(0, self._on_cancelled, download_id, removed_count)
                return
            self.after(0, self._finish_polling, download_id)
            self.after(0, self._on_error, download_id, str(exc))

    def _cleanup_partial_files(self):
        removed = 0
        candidates = set(self._partial_files)
        extra_suffixes = [".part", ".ytdl", ".temp"]

        for path in list(candidates):
            for suffix in extra_suffixes:
                candidates.add(path + suffix)

        for path in candidates:
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
                    removed += 1
            except Exception:
                pass

        self._partial_files = set()
        return removed

    def _poll_progress(self):
        if self._terminal_state:
            return

        current_id = self._active_download_id
        item = None
        try:
            while True:
                candidate = self._queue.get_nowait()
                if candidate and candidate[0] == current_id:
                    item = candidate
        except queue.Empty:
            pass

        if item is not None:
            _download_id, pct_val, pct_str, merging = item
            if merging:
                self.status_label.configure(text="Processando arquivo final...", text_color=self._status_colors["running"])
                self.pct_label.configure(text=pct_str)
            else:
                self.status_label.configure(text="Baixando...", text_color=self._status_colors["running"])
                self.pct_label.configure(text=pct_str)
            self.progress_bar.set(pct_val)

        if self._polling:
            self.after(100, self._poll_progress)

    def _finish_polling(self, download_id):
        if download_id != self._active_download_id:
            return
        self._polling = False

    def _drain_progress_queue(self):
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _reset_progress(self):
        self.progress_bar.set(0)
        self.status_label.configure(text="Preparando download...", text_color=self._status_colors["running"])
        self.pct_label.configure(text="0%")

    def _on_done(self, download_id, msg):
        if download_id != self._active_download_id:
            return
        self._terminal_state = True
        self._is_downloading = False
        self._cancel_requested = False
        self._drain_progress_queue()
        self.progress_bar.set(1.0)
        self.status_label.configure(text=msg, text_color=self._status_colors["ok"])
        self.pct_label.configure(text="100%")
        self.cancel_btn.configure(text="Cancelar")
        self._set_ui_locked(False)

    def _on_cancelled(self, download_id, removed_count):
        if download_id != self._active_download_id:
            return
        self._terminal_state = True
        self._is_downloading = False
        self._cancel_requested = False
        self._drain_progress_queue()
        self.progress_bar.set(0)
        suffix = f" ({removed_count} arquivo(s) limpo(s))" if removed_count else ""
        self.status_label.configure(
            text=f"Download cancelado pelo usuario{suffix}",
            text_color=self._status_colors["warning"],
        )
        self.pct_label.configure(text="0%")
        self.cancel_btn.configure(text="Cancelar")
        self._set_ui_locked(False)

    def _on_error(self, download_id, err):
        if download_id != self._active_download_id:
            return
        self._terminal_state = True
        self._is_downloading = False
        self._cancel_requested = False
        self._drain_progress_queue()
        self.status_label.configure(
            text=self._friendly_error_message(str(err), prefix="Erro"),
            text_color=self._status_colors["error"],
        )
        self.cancel_btn.configure(text="Cancelar")
        self._set_ui_locked(False)



if __name__ == "__main__":
    app = App()
    app.mainloop()
