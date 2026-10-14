from __future__ import annotations

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import (
    QAudioBuffer,
    QAudioBufferOutput,
    QAudioFormat,
    QAudioOutput,
    QMediaMetaData,
    QMediaPlayer,
)

from .spectrum import to_mono_float
from .utils import is_url

PlaybackState = QMediaPlayer.PlaybackState
MediaStatus = QMediaPlayer.MediaStatus

_SAMPLE_FORMATS = {
    QAudioFormat.SampleFormat.Float: "float",
    QAudioFormat.SampleFormat.Int16: "int16",
    QAudioFormat.SampleFormat.Int32: "int32",
    QAudioFormat.SampleFormat.UInt8: "uint8",
}


class PlayerController(QObject):
    positionChanged = Signal("qint64")
    durationChanged = Signal("qint64")
    playbackStateChanged = Signal(object)
    mediaStatusChanged = Signal(object)
    seekableChanged = Signal(bool)
    hasVideoChanged = Signal(bool)
    bufferProgressChanged = Signal(float)
    metaDataChanged = Signal()
    errorOccurred = Signal(str)
    mediaFinished = Signal()
    audioSamples = Signal(object, int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._buffers = QAudioBufferOutput(self)
        self._player.setAudioBufferOutput(self._buffers)
        self._buffers.audioBufferReceived.connect(self._on_audio_buffer)
        self._volume = 70

        p = self._player
        p.positionChanged.connect(self.positionChanged.emit)
        p.durationChanged.connect(self.durationChanged.emit)
        p.playbackStateChanged.connect(self.playbackStateChanged.emit)
        p.seekableChanged.connect(self.seekableChanged.emit)
        p.hasVideoChanged.connect(self.hasVideoChanged.emit)
        p.bufferProgressChanged.connect(self.bufferProgressChanged.emit)
        p.metaDataChanged.connect(self.metaDataChanged.emit)
        p.mediaStatusChanged.connect(self._on_media_status)
        p.errorOccurred.connect(self._on_error)

        self.set_volume(self._volume)


    def set_video_output(self, output: QObject) -> None:
        self._player.setVideoOutput(output)

    def load(self, source: str, autoplay: bool = True) -> None:
        url = QUrl(source.strip()) if is_url(source) else QUrl.fromLocalFile(source)
        self._player.setSource(url)
        if autoplay:
            self._player.play()

    def unload(self) -> None:
        self._player.stop()
        self._player.setSource(QUrl())

    @property
    def has_source(self) -> bool:
        return not self._player.source().isEmpty()


    def play(self) -> None:
        if self.has_source:
            self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def toggle_play(self) -> None:
        if self.state is PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        if self._player.isSeekable():
            duration = self.duration
            if duration > 0:
                position_ms = min(position_ms, duration)
            self._player.setPosition(max(0, position_ms))

    def skip(self, delta_ms: int) -> None:
        self.seek(self.position + delta_ms)

    @property
    def state(self) -> PlaybackState:
        return self._player.playbackState()

    @property
    def position(self) -> int:
        return self._player.position()

    @property
    def duration(self) -> int:
        return self._player.duration()

    @property
    def is_seekable(self) -> bool:
        return self._player.isSeekable()

    @property
    def has_video(self) -> bool:
        return self._player.hasVideo()


    @property
    def volume(self) -> int:
        return self._volume

    def set_volume(self, percent: int) -> None:
        self._volume = max(0, min(100, int(percent)))
        self._audio.setVolume((self._volume / 100) ** 2)

    @property
    def muted(self) -> bool:
        return self._audio.isMuted()

    def set_muted(self, muted: bool) -> None:
        self._audio.setMuted(muted)

    def set_rate(self, rate: float) -> None:
        self._player.setPlaybackRate(rate)


    def metadata(self) -> dict[str, object]:
        md = self._player.metaData()
        keys = {
            "title": QMediaMetaData.Key.Title,
            "artist": QMediaMetaData.Key.ContributingArtist,
            "album": QMediaMetaData.Key.AlbumTitle,
            "cover": QMediaMetaData.Key.CoverArtImage,
            "thumbnail": QMediaMetaData.Key.ThumbnailImage,
            "resolution": QMediaMetaData.Key.Resolution,
        }
        result: dict[str, object] = {}
        for name, key in keys.items():
            value = md.value(key)
            if value is None or value == "":
                continue
            if isinstance(value, QImage) and value.isNull():
                continue
            result[name] = value
        for name, key in (("audio_codec", QMediaMetaData.Key.AudioCodec),
                          ("video_codec", QMediaMetaData.Key.VideoCodec)):
            if key in md.keys() and (text := md.stringValue(key)):
                result[name] = text
        return result


    def _on_audio_buffer(self, buffer: QAudioBuffer) -> None:
        fmt = buffer.format()
        kind = _SAMPLE_FORMATS.get(fmt.sampleFormat())
        if kind is None or not buffer.isValid():
            return
        samples = to_mono_float(bytes(buffer.constData()), kind, fmt.channelCount())
        self.audioSamples.emit(samples, fmt.sampleRate())

    def _on_media_status(self, status: MediaStatus) -> None:
        self.mediaStatusChanged.emit(status)
        if status is MediaStatus.EndOfMedia:
            self.mediaFinished.emit()

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error is not QMediaPlayer.Error.NoError:
            self.errorOccurred.emit(message or str(error))
