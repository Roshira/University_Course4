from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..player import MediaStatus, PlaybackState, PlayerController
from ..playlist import MediaItem, Playlist, RepeatMode
from ..utils import (
    PLAYLIST_EXTENSIONS,
    describe_source,
    format_time,
    is_supported_file,
    is_url,
    open_file_filter,
)
from . import icons
from .widgets import ROLE_CURRENT, ROLE_INFO, InfoView, PlaylistDelegate, SeekSlider, VideoView

APP_TITLE = "Медіаплеєр"
SEEK_STEP_MS = 10_000
VOLUME_STEP = 5
RESTART_THRESHOLD_MS = 3_000
PLAYBACK_RATES = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

EXAMPLE_URLS = (
    "https://test-videos.co.uk/vids/jellyfish/mp4/h264/720/Jellyfish_720_10s_1MB.mp4",
    "https://test-videos.co.uk/vids/sintel/mp4/h264/720/Sintel_720_10s_1MB.mp4",
    "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8"
    "?filter=(type!=%22video%22)||(systemBitrate%3E1200000)",
    "https://upload.wikimedia.org/wikipedia/commons/2/22/Volcano_Lava_Sample.webm",
    "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
)

REPEAT_LABELS = {
    RepeatMode.OFF: "Повтор: вимкнено",
    RepeatMode.ALL: "Повтор: увесь список",
    RepeatMode.ONE: "Повтор: поточний трек",
}


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 680)
        self.setAcceptDrops(True)

        self.settings = QSettings("University_Course4", "Lab2MediaPlayer")
        self.player = PlayerController(self)
        self.playlist = Playlist()
        self._seeking = False
        self._was_maximized = False

        self._create_actions()
        self._create_central()
        self._create_playlist_dock()
        self._create_menus()
        self._connect_player()
        self._restore_settings()
        self._update_transport()


    def _action(self, text: str, slot, shortcut=None, icon: str | None = None,
                checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if icon:
            action.setIcon(icons.icon(icon))
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            action.setShortcuts([QKeySequence(s) for s in seqs])
            action.setToolTip(f"{text} ({QKeySequence(seqs[0]).toString()})")
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def _create_actions(self) -> None:
        a = self._action
        self.act_open = a("Відкрити файл...", self.open_files, QKeySequence.StandardKey.Open, "folder")
        self.act_open_url = a("Відкрити URL...", self.open_url, "Ctrl+U", "link")
        self.act_open_folder = a("Відкрити теку...", self.open_folder, "Ctrl+Shift+O", "folder")
        self.act_save_pl = a("Зберегти список (M3U)...", self.save_playlist, "Ctrl+S", "save")
        self.act_quit = a("Вихід", self.close, "Ctrl+Q")

        self.act_play = a("Відтворити / Пауза", self.player.toggle_play, ["Space", "K"])
        self.act_play.setIcon(icons.icon("play", icons.ON_ACCENT))
        self.act_stop = a("Стоп", self.player.stop, "S", "stop")
        self.act_back = a("Назад на 10 с", lambda: self.player.skip(-SEEK_STEP_MS), "Left", "back")
        self.act_fwd = a("Вперед на 10 с", lambda: self.player.skip(SEEK_STEP_MS), "Right", "forward")
        self.act_prev = a("Попередній трек", self.play_previous, ["PgUp", "P"], "prev")
        self.act_next = a("Наступний трек", self.play_next, ["PgDown", "N"], "next")

        self.act_vol_up = a("Гучніше", lambda: self.change_volume(VOLUME_STEP), "Up")
        self.act_vol_down = a("Тихіше", lambda: self.change_volume(-VOLUME_STEP), "Down")
        self.act_mute = a("Вимкнути звук", self.toggle_mute, "M", "volume", checkable=True)

        self.act_repeat = a(REPEAT_LABELS[RepeatMode.OFF], self.cycle_repeat, "R", "repeat")
        self.act_shuffle = a("Випадковий порядок", self.toggle_shuffle, "H", "shuffle", checkable=True)
        self.act_fullscreen = a("Повний екран", self.toggle_fullscreen, ["F", "F11"], "fullscreen")
        self.act_exit_fullscreen = a("Вийти з повного екрана", self.exit_fullscreen, "Esc")

    def _tool_button(self, action: QAction, size: int = 22) -> QToolButton:
        button = QToolButton()
        button.setDefaultAction(action)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setAutoRaise(True)
        button.setIconSize(QSize(size, size))
        return button

    def _create_central(self) -> None:
        self.video_view = VideoView()
        self.info_view = InfoView()
        self.player.set_video_output(self.video_view)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.info_view)
        self.stack.addWidget(self.video_view)
        self.video_view.doubleClicked.connect(self.toggle_fullscreen)
        self.video_view.clicked.connect(self.player.toggle_play)
        self.info_view.doubleClicked.connect(self.toggle_fullscreen)

        self.now_playing = QLabel("Нічого не відтворюється")
        self.now_playing.setObjectName("NowPlaying")
        self.now_playing.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.now_meta = QLabel("")
        self.now_meta.setObjectName("NowMeta")

        self.time_label = QLabel(format_time(0))
        self.duration_label = QLabel(format_time(0))
        for label in (self.time_label, self.duration_label):
            label.setObjectName("TimeLabel")
            label.setMinimumWidth(56)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek_slider = SeekSlider()
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        seek_row.addWidget(self.time_label)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.duration_label)

        left = QHBoxLayout()
        left.setSpacing(2)
        for action in (self.act_open, self.act_open_url):
            left.addWidget(self._tool_button(action))
        left.addStretch(1)

        center = QHBoxLayout()
        center.setSpacing(6)
        for action in (self.act_stop, self.act_prev, self.act_back):
            center.addWidget(self._tool_button(action))
        self.play_button = self._tool_button(self.act_play, 28)
        self.play_button.setObjectName("PlayButton")
        self.play_button.setFixedSize(52, 52)
        center.addSpacing(6)
        center.addWidget(self.play_button)
        center.addSpacing(6)
        for action in (self.act_fwd, self.act_next):
            center.addWidget(self._tool_button(action))

        self.speed_combo = QComboBox()
        self.speed_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_combo.setToolTip("Швидкість відтворення")
        for rate in PLAYBACK_RATES:
            self.speed_combo.addItem(f"{rate:g}x", rate)
        self.speed_combo.setCurrentIndex(PLAYBACK_RATES.index(1.0))
        self.speed_combo.currentIndexChanged.connect(
            lambda i: self.player.set_rate(self.speed_combo.itemData(i))
        )

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("VolumeSlider")
        self.volume_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setFixedWidth(110)
        self.volume_slider.setToolTip("Гучність (↑ / ↓)")
        self.volume_slider.valueChanged.connect(self._on_volume_slider)
        self.volume_label = QLabel()
        self.volume_label.setObjectName("TimeLabel")
        self.volume_label.setMinimumWidth(40)

        right = QHBoxLayout()
        right.setSpacing(4)
        right.addStretch(1)
        right.addWidget(self.speed_combo)
        right.addSpacing(10)
        right.addWidget(self._tool_button(self.act_mute))
        right.addWidget(self.volume_slider)
        right.addWidget(self.volume_label)
        right.addWidget(self._tool_button(self.act_fullscreen))

        controls = QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addLayout(left, 0, 0)
        controls.addLayout(center, 0, 1)
        controls.addLayout(right, 0, 2)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(2, 1)

        self.controls_panel = QWidget()
        self.controls_panel.setObjectName("ControlsPanel")
        panel_layout = QVBoxLayout(self.controls_panel)
        panel_layout.setContentsMargins(18, 12, 18, 12)
        panel_layout.setSpacing(6)
        panel_layout.addWidget(self.now_playing)
        panel_layout.addWidget(self.now_meta)
        panel_layout.addSpacing(2)
        panel_layout.addLayout(seek_row)
        panel_layout.addLayout(controls)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.controls_panel)
        self.setCentralWidget(central)

    def _create_playlist_dock(self) -> None:
        self.playlist_view = QListWidget()
        self.playlist_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.playlist_view.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.playlist_view.setItemDelegate(PlaylistDelegate(self.playlist_view))
        self.playlist_view.setMouseTracking(True)
        self.playlist_view.setUniformItemSizes(True)
        self.playlist_view.itemDoubleClicked.connect(
            lambda item: self.play_index(self.playlist_view.row(item))
        )

        act_remove = QAction(icons.icon("remove"), "Видалити вибрані", self)
        act_remove.setShortcut(QKeySequence.StandardKey.Delete)
        act_remove.triggered.connect(self.remove_selected)
        self.addAction(act_remove)
        act_clear = QAction(icons.icon("trash"), "Очистити список", self)
        act_clear.triggered.connect(self.clear_playlist)

        buttons = QHBoxLayout()
        buttons.setSpacing(2)
        for action in (self.act_open, self.act_open_url, self.act_save_pl, act_remove, act_clear):
            buttons.addWidget(self._tool_button(action, 18))
        buttons.addStretch(1)
        self.repeat_button = self._tool_button(self.act_repeat, 18)
        buttons.addWidget(self.repeat_button)
        buttons.addWidget(self._tool_button(self.act_shuffle, 18))

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 4, 8, 8)
        self.playlist_count = QLabel()
        self.playlist_count.setObjectName("PlaylistCount")
        layout.addWidget(self.playlist_count)
        layout.addWidget(self.playlist_view, 1)
        layout.addLayout(buttons)

        self.playlist_dock = QDockWidget("Список відтворення", self)
        self.playlist_dock.setObjectName("PlaylistDock")
        self.playlist_dock.setWidget(panel)
        self.playlist_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.playlist_dock)

        self.act_toggle_playlist = self.playlist_dock.toggleViewAction()
        self.act_toggle_playlist.setText("Список відтворення")
        self.act_toggle_playlist.setShortcut(QKeySequence("L"))
        self.addAction(self.act_toggle_playlist)

    def _create_menus(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("&Файл")
        file_menu.addActions([self.act_open, self.act_open_folder, self.act_open_url])
        file_menu.addSeparator()
        file_menu.addAction(self.act_save_pl)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        play_menu = menu.addMenu("&Відтворення")
        play_menu.addActions([self.act_play, self.act_stop])
        play_menu.addSeparator()
        play_menu.addActions([self.act_back, self.act_fwd, self.act_prev, self.act_next])
        play_menu.addSeparator()
        play_menu.addActions([self.act_vol_up, self.act_vol_down, self.act_mute])
        play_menu.addSeparator()
        play_menu.addActions([self.act_repeat, self.act_shuffle])

        view_menu = menu.addMenu("В&игляд")
        view_menu.addActions([self.act_fullscreen, self.act_toggle_playlist])

        help_menu = menu.addMenu("&Довідка")
        help_menu.addAction("Гарячі клавіші", self.show_shortcuts)

    def _connect_player(self) -> None:
        p = self.player
        p.positionChanged.connect(self._on_position)
        p.durationChanged.connect(self._on_duration)
        p.seekableChanged.connect(lambda _: self._update_transport())
        p.playbackStateChanged.connect(self._on_state)
        p.mediaStatusChanged.connect(self._on_status)
        p.hasVideoChanged.connect(self._on_has_video)
        p.metaDataChanged.connect(self._on_metadata)
        p.bufferProgressChanged.connect(self._on_buffer)
        p.errorOccurred.connect(self._on_error)
        p.mediaFinished.connect(lambda: QTimer.singleShot(0, self._on_finished))
        p.audioSamples.connect(self._on_audio_samples)


    def open_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Відкрити медіафайли", self._last_dir(), open_file_filter()
        )
        if files:
            self.settings.setValue("last_dir", str(Path(files[0]).parent))
            self.add_sources(files, play=True)

    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Відкрити теку", self._last_dir())
        if folder:
            self.settings.setValue("last_dir", folder)
            self.add_sources([folder], play=True)

    def open_url(self) -> None:
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Відкрити URL")
        dialog.setLabelText("Посилання на медіа (MP4, WebM, MP3, HLS .m3u8 тощо):")
        dialog.setComboBoxItems(list(EXAMPLE_URLS))
        dialog.setComboBoxEditable(True)
        dialog.setOkButtonText("Відкрити")
        dialog.setCancelButtonText("Скасувати")
        dialog.resize(640, dialog.sizeHint().height())
        if not dialog.exec():
            return
        url = dialog.textValue().strip()
        if not url:
            return
        if not is_url(url):
            QMessageBox.warning(self, APP_TITLE, f"Некоректна адреса:\n{url}")
            return
        self.add_sources([url], play=True)

    def add_sources(self, sources: list[str], play: bool = False) -> None:
        items = self._expand_sources(sources)
        if not items:
            self.statusBar().showMessage("Не знайдено підтримуваних медіафайлів", 5000)
            return
        first = self.playlist.add(items)
        self._refresh_playlist()
        self.statusBar().showMessage(f"Додано до списку: {len(items)}", 3000)
        if play or self.playlist.current is None:
            self.play_index(first)

    def _expand_sources(self, sources: list[str]) -> list[MediaItem]:
        items: list[MediaItem] = []
        for source in sources:
            if is_url(source):
                items.append(MediaItem.from_source(source))
                continue
            path = Path(source)
            if path.is_dir():
                files = sorted(p for p in path.rglob("*") if p.is_file() and is_supported_file(str(p)))
                items.extend(MediaItem.from_source(str(p)) for p in files)
            elif path.suffix.lower() in PLAYLIST_EXTENSIONS:
                try:
                    items.extend(Playlist.load_m3u(path))
                except OSError as exc:
                    QMessageBox.warning(self, APP_TITLE, f"Не вдалося прочитати список:\n{exc}")
            elif path.is_file():
                items.append(MediaItem.from_source(str(path)))
        return items

    def save_playlist(self) -> None:
        if not self.playlist.items:
            self.statusBar().showMessage("Список відтворення порожній", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Зберегти список", str(Path(self._last_dir()) / "playlist.m3u"),
            "Список M3U (*.m3u *.m3u8)",
        )
        if path:
            self.playlist.save_m3u(path)
            self.statusBar().showMessage(f"Список збережено: {path}", 4000)

    def _last_dir(self) -> str:
        return str(self.settings.value("last_dir", str(Path.home())))


    def play_index(self, index: int) -> None:
        item = self.playlist.set_current(index)
        self._seeking = False
        self.seek_slider.setValue(0)
        self.time_label.setText(format_time(0))
        self.duration_label.setText("--:--")
        self.now_playing.setText(item.title)
        self.now_meta.setText(describe_source(item.source))
        self.setWindowTitle(f"{item.title} - {APP_TITLE}")
        self.stack.setCurrentWidget(self.info_view)
        self.info_view.show_loading(item.title)
        self.player.load(item.source)
        self._refresh_playlist()

    def play_next(self) -> None:
        index = self.playlist.next_index()
        if index is not None:
            self.play_index(index)

    def play_previous(self) -> None:
        if self.player.position > RESTART_THRESHOLD_MS and self.player.is_seekable:
            self.player.seek(0)
            return
        index = self.playlist.previous_index()
        if index is not None:
            self.play_index(index)

    def remove_selected(self) -> None:
        rows = sorted({self.playlist_view.row(i) for i in self.playlist_view.selectedItems()}, reverse=True)
        if not rows:
            return
        current_removed = self.playlist.current_index in rows
        for row in rows:
            self.playlist.remove(row)
        if current_removed:
            self._reset_player()
        self._refresh_playlist()

    def clear_playlist(self) -> None:
        self.playlist.clear()
        self._reset_player()
        self._refresh_playlist()

    def _reset_player(self) -> None:
        self.player.unload()
        self.stack.setCurrentWidget(self.info_view)
        self.info_view.show_idle()
        self.now_playing.setText("Нічого не відтворюється")
        self.now_meta.setText("")
        self.setWindowTitle(APP_TITLE)
        self._on_duration(0)
        self._on_position(0)

    def _refresh_playlist(self) -> None:
        self.playlist_view.clear()
        for i, item in enumerate(self.playlist.items):
            row = QListWidgetItem(item.title)
            row.setToolTip(item.source)
            row.setData(ROLE_INFO, describe_source(item.source))
            row.setData(ROLE_CURRENT, i == self.playlist.current_index)
            self.playlist_view.addItem(row)
        if self.playlist.current is not None:
            self.playlist_view.scrollToItem(self.playlist_view.item(self.playlist.current_index))
        count = len(self.playlist)
        self.playlist_count.setText(f"{count} {self._tracks_word(count)}" if count else "Список порожній")
        self._update_transport()

    @staticmethod
    def _tracks_word(n: int) -> str:
        if n % 10 == 1 and n % 100 != 11:
            return "трек"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "треки"
        return "треків"

    def cycle_repeat(self) -> None:
        self.playlist.repeat = self.playlist.repeat.next()
        self._update_repeat_ui()

    def toggle_shuffle(self) -> None:
        self.playlist.shuffle = self.act_shuffle.isChecked()

    def _update_repeat_ui(self) -> None:
        mode = self.playlist.repeat
        self.act_repeat.setText(REPEAT_LABELS[mode])
        self.act_repeat.setToolTip(f"{REPEAT_LABELS[mode]} (R)")
        self.repeat_button.setProperty("active", mode is not RepeatMode.OFF)
        color = icons.TEXT if mode is RepeatMode.OFF else icons.ACCENT
        self.act_repeat.setIcon(icons.icon("repeat", color))
        self.repeat_button.setText("1" if mode is RepeatMode.ONE else "")
        self.repeat_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon if mode is RepeatMode.ONE
            else Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.repeat_button.style().unpolish(self.repeat_button)
        self.repeat_button.style().polish(self.repeat_button)


    def _on_volume_slider(self, value: int) -> None:
        self.player.set_volume(value)
        self.volume_label.setText(f"{value}%")
        self._update_volume_icon()
        if value > 0 and self.player.muted:
            self.act_mute.setChecked(False)
            self.toggle_mute()

    def change_volume(self, delta: int) -> None:
        self.volume_slider.setValue(self.volume_slider.value() + delta)
        self.statusBar().showMessage(f"Гучність: {self.volume_slider.value()}%", 1500)

    def toggle_mute(self) -> None:
        muted = self.act_mute.isChecked()
        self.player.set_muted(muted)
        self.act_mute.setText("Увімкнути звук" if muted else "Вимкнути звук")
        self._update_volume_icon()

    def _update_volume_icon(self) -> None:
        value = self.volume_slider.value()
        if self.act_mute.isChecked() or value == 0:
            name = "mute"
        elif value < 50:
            name = "volume_low"
        else:
            name = "volume"
        self.act_mute.setIcon(icons.icon(name, checked_color=icons.TEXT))


    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_moved(self, value: int) -> None:
        self.time_label.setText(format_time(value))

    def _on_seek_released(self) -> None:
        self.player.seek(self.seek_slider.value())
        self._seeking = False


    def _on_position(self, position: int) -> None:
        if not self._seeking:
            self.seek_slider.setValue(position)
            self.time_label.setText(format_time(position))

    def _on_duration(self, duration: int) -> None:
        self.seek_slider.setRange(0, max(0, duration))
        self.duration_label.setText(format_time(duration) if duration > 0 else "--:--")
        self._update_transport()

    def _on_state(self, state: PlaybackState) -> None:
        playing = state is PlaybackState.PlayingState
        self.act_play.setIcon(icons.icon("pause" if playing else "play", icons.ON_ACCENT))
        self.act_play.setText("Пауза" if playing else "Відтворити")
        if state is PlaybackState.StoppedState and not self._seeking:
            self._on_position(0)
        self._update_transport()

    def _on_status(self, status: MediaStatus) -> None:
        messages = {
            MediaStatus.LoadingMedia: "Завантаження...",
            MediaStatus.BufferingMedia: "Буферизація...",
            MediaStatus.StalledMedia: "Очікування даних...",
            MediaStatus.InvalidMedia: "Не вдалося відтворити медіа",
        }
        if status in messages:
            self.statusBar().showMessage(messages[status])
        elif status in (MediaStatus.LoadedMedia, MediaStatus.BufferedMedia):
            self.statusBar().showMessage(self._media_details(), 0)
            self._on_duration(self.player.duration)
            self._on_has_video(self.player.has_video)

    def _on_buffer(self, progress: float) -> None:
        if 0 < progress < 1:
            self.statusBar().showMessage(f"Буферизація: {progress:.0%}")

    def _on_has_video(self, has_video: bool) -> None:
        if has_video:
            self.stack.setCurrentWidget(self.video_view)
        else:
            self.stack.setCurrentWidget(self.info_view)
            self._on_metadata()

    def _on_metadata(self) -> None:
        item = self.playlist.current
        if item is None:
            return
        md = self.player.metadata()
        title = str(md.get("title") or item.title)
        artist = md.get("artist")
        if isinstance(artist, list):
            artist = ", ".join(map(str, artist))
        subtitle = " - ".join(str(x) for x in (artist, md.get("album")) if x)
        self.now_playing.setText(title)
        info = describe_source(item.source)
        self.now_meta.setText(f"{subtitle}  |  {info}" if subtitle else info)
        if not self.player.has_video:
            cover = md.get("cover") or md.get("thumbnail")
            self.info_view.show_audio(title, subtitle or item.source, cover)

    def _media_details(self) -> str:
        item = self.playlist.current
        if item is None:
            return ""
        md = self.player.metadata()
        parts = ["URL" if item.is_remote else "Файл"]
        if self.player.has_video:
            size = md.get("resolution")
            if size is not None and size.isValid():
                parts.append(f"{size.width()}x{size.height()}")
            if md.get("video_codec"):
                parts.append(f"відео: {md['video_codec']}")
        if md.get("audio_codec"):
            parts.append(f"аудіо: {md['audio_codec']}")
        if not self.player.is_seekable:
            parts.append("трансляція без перемотування")
        return "  |  ".join(parts)

    def _on_error(self, message: str) -> None:
        item = self.playlist.current
        source = item.source if item else ""
        self.statusBar().showMessage(f"Помилка: {message}", 10000)
        self.info_view.show_error(message)
        self.stack.setCurrentWidget(self.info_view)
        QMessageBox.warning(self, APP_TITLE, f"Не вдалося відтворити:\n{source}\n\n{message}")

    def _on_audio_samples(self, samples, rate: int) -> None:
        if self.stack.currentWidget() is self.info_view and self.info_view.spectrum.isVisible():
            self.info_view.spectrum.feed(samples, rate)

    def _on_finished(self) -> None:
        index = self.playlist.next_index(auto=True)
        if index is None:
            self.player.stop()
        else:
            self.play_index(index)

    def _update_transport(self) -> None:
        has_media = self.player.has_source
        seekable = has_media and self.player.is_seekable and self.player.duration > 0
        for action in (self.act_play, self.act_stop):
            action.setEnabled(has_media)
        for action in (self.act_back, self.act_fwd):
            action.setEnabled(seekable)
        self.seek_slider.setEnabled(seekable)
        multiple = len(self.playlist) > 1
        self.act_next.setEnabled(multiple)
        self.act_prev.setEnabled(has_media)


    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._was_maximized = self.isMaximized()
            self._playlist_was_visible = self.playlist_dock.isVisible()
            self.menuBar().hide()
            self.statusBar().hide()
            self.playlist_dock.hide()
            self.showFullScreen()

    def exit_fullscreen(self) -> None:
        if not self.isFullScreen():
            return
        self.menuBar().show()
        self.statusBar().show()
        self.playlist_dock.setVisible(getattr(self, "_playlist_was_visible", True))
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()


    def show_shortcuts(self) -> None:
        actions = (
            self.act_open, self.act_open_url, self.act_play, self.act_stop, self.act_back,
            self.act_fwd, self.act_prev, self.act_next, self.act_vol_up, self.act_vol_down,
            self.act_mute, self.act_repeat, self.act_shuffle, self.act_fullscreen,
            self.act_toggle_playlist,
        )
        rows = "".join(
            f"<tr><td><b>{' / '.join(s.toString() for s in a.shortcuts())}</b></td>"
            f"<td>&nbsp;&nbsp;{a.text().split(':')[0]}</td></tr>"
            for a in actions
        )
        QMessageBox.information(self, "Гарячі клавіші", f"<table>{rows}</table>")

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        sources = [
            url.toLocalFile() if url.isLocalFile() else url.toString()
            for url in event.mimeData().urls()
        ]
        self.add_sources(sources, play=True)
        event.acceptProposedAction()

    def _restore_settings(self) -> None:
        s = self.settings
        geometry = s.value("geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        state = s.value("window_state")
        if isinstance(state, QByteArray):
            self.restoreState(state)
        volume = int(s.value("volume", 70))
        self.volume_slider.setValue(volume)
        self._on_volume_slider(volume)
        try:
            self.playlist.repeat = RepeatMode(s.value("repeat", RepeatMode.OFF.value))
        except ValueError:
            self.playlist.repeat = RepeatMode.OFF
        self._update_repeat_ui()
        shuffle = str(s.value("shuffle", "false")).lower() == "true"
        self.act_shuffle.setChecked(shuffle)
        self.playlist.shuffle = shuffle

        saved = s.value("playlist", [])
        if isinstance(saved, str):
            saved = [saved]
        items = [MediaItem.from_source(src) for src in (saved or [])
                 if is_url(src) or Path(src).is_file()]
        if items:
            self.playlist.add(items)
            self._refresh_playlist()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.exit_fullscreen()
        s = self.settings
        s.setValue("geometry", self.saveGeometry())
        s.setValue("window_state", self.saveState())
        s.setValue("volume", self.volume_slider.value())
        s.setValue("repeat", self.playlist.repeat.value)
        s.setValue("shuffle", self.playlist.shuffle)
        s.setValue("playlist", [item.source for item in self.playlist.items])
        self.player.stop()
        super().closeEvent(event)
