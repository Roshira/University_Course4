import tempfile
import unittest
from pathlib import Path

from media_player.playlist import MediaItem, Playlist, RepeatMode
from media_player.utils import display_name, format_time, is_url, media_kind


class UtilsTest(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time(0), "0:00")
        self.assertEqual(format_time(65_400), "1:05")
        self.assertEqual(format_time(3_725_000), "1:02:05")
        self.assertEqual(format_time(-5), "0:00")

    def test_is_url(self):
        self.assertTrue(is_url("https://example.com/a.mp4"))
        self.assertTrue(is_url("rtsp://cam.local/stream"))
        self.assertFalse(is_url(r"C:\music\a.mp3"))
        self.assertFalse(is_url("https://"))

    def test_media_kind(self):
        self.assertEqual(media_kind("song.MP3"), "audio")
        self.assertEqual(media_kind("clip.webm"), "video")
        self.assertEqual(media_kind("https://x.org/v/clip.mp4?token=1"), "video")
        self.assertIsNone(media_kind("notes.txt"))

    def test_display_name(self):
        self.assertEqual(display_name("https://x.org/a/My%20Song.mp3"), "My Song.mp3")
        self.assertEqual(display_name("https://x.org/"), "x.org")


def make_playlist(n: int) -> Playlist:
    pl = Playlist()
    pl.add([MediaItem(f"https://x.org/{i}.mp3", str(i)) for i in range(n)])
    return pl


class PlaylistTest(unittest.TestCase):
    def test_next_without_repeat_stops_at_end(self):
        pl = make_playlist(3)
        pl.set_current(1)
        self.assertEqual(pl.next_index(), 2)
        pl.set_current(2)
        self.assertIsNone(pl.next_index(auto=True))

    def test_repeat_all_wraps(self):
        pl = make_playlist(3)
        pl.repeat = RepeatMode.ALL
        pl.set_current(2)
        self.assertEqual(pl.next_index(), 0)
        pl.set_current(0)
        self.assertEqual(pl.previous_index(), 2)

    def test_repeat_one_only_on_auto(self):
        pl = make_playlist(3)
        pl.repeat = RepeatMode.ONE
        pl.set_current(1)
        self.assertEqual(pl.next_index(auto=True), 1)
        self.assertEqual(pl.next_index(auto=False), 2)

    def test_shuffle_never_repeats_current(self):
        pl = make_playlist(4)
        pl.shuffle = True
        pl.set_current(2)
        for _ in range(50):
            self.assertNotEqual(pl.next_index(), 2)

    def test_remove_adjusts_current(self):
        pl = make_playlist(4)
        pl.set_current(2)
        pl.remove(0)
        self.assertEqual(pl.current_index, 1)
        self.assertEqual(pl.current.title, "2")
        pl.remove(1)
        self.assertIsNone(pl.current)

    def test_repeat_mode_cycle(self):
        self.assertIs(RepeatMode.OFF.next(), RepeatMode.ALL)
        self.assertIs(RepeatMode.ONE.next(), RepeatMode.OFF)

    def test_m3u_roundtrip_with_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "a.mp3").write_bytes(b"")
            m3u = tmp / "list.m3u"
            m3u.write_text(
                "#EXTM3U\n#EXTINF:12,Перша\na.mp3\n\nhttps://x.org/b.mp4\n", encoding="utf-8"
            )
            items = Playlist.load_m3u(m3u)
            self.assertEqual([i.title for i in items], ["Перша", "b.mp4"])
            self.assertEqual(Path(items[0].source), (tmp / "a.mp3").resolve())
            self.assertTrue(items[1].is_remote)

            pl = Playlist()
            pl.add(items)
            out = tmp / "out.m3u"
            pl.save_m3u(out)
            self.assertEqual(Playlist.load_m3u(out), items)


if __name__ == "__main__":
    unittest.main()
