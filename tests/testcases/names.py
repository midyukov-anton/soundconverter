#!/usr/bin/python3
# -*- coding: utf-8 -*-


"""Test filename handling."""


import unittest
import os
from urllib.parse import unquote
import urllib.parse
import urllib.error
from gi.repository import Gst, Gio

from soundconverter.util.settings import settings
from soundconverter.util.namegenerator import TargetNameGenerator
from soundconverter.util.soundfile import SoundFile
from soundconverter.util.fileoperations import filename_to_uri, unquote_filename, beautify_uri
from soundconverter.interface.batch import prepare_files_list

from util import reset_settings


def quote(ss):
    if isinstance(ss, str):
        ss = ss.encode('utf-8')
    return urllib.parse.quote(ss)


class FilenameToUriTest(unittest.TestCase):
    def test(self):
        for path in ('foo', '/foo', 'foo/bar', '/foo/bar'):
            uri = filename_to_uri(path)
            self.assertTrue(uri.startswith('file://'))
            self.assertTrue(Gio.file_parse_name(path).get_uri() in uri)

        for path in ('http://example.com/foo', ):
            uri = filename_to_uri(path)
            self.assertTrue(uri.startswith('http://'))
            self.assertTrue(Gio.file_parse_name(path).get_uri() in uri)


class PrepareFilesList(unittest.TestCase):
    def tearDown(self):
        reset_settings()

    def testNonRecursiveDirectory(self):
        test = ["tests/test data/empty/"]
        # it should not find anything, as test is a directory
        expectation = ([], [])
        self.assertEqual(prepare_files_list(test), expectation)

    def testRecursiveDirectory(self):
        settings["recursive"] = True
        test = ["tests/test data/empty/", "tests/test data/empty/b"]
        expectation = ([
            filename_to_uri(test[0] + "a"),
            filename_to_uri(test[0] + "b/c"),
            filename_to_uri(test[1] + "/c")
        ], [
            "empty/",
            "empty/b/",
            "b/"
        ])
        result = prepare_files_list(test)
        for path in result[0]:
            self.assertTrue(path.startswith('file://'))
        self.assertEqual(result, expectation)

    def testFile(self):
        test = ["tests/test data/empty/a"]
        # it should not detect the name of the parent directory as
        # it's only a single file
        expectation = ([filename_to_uri(test[0])], [""])
        result = prepare_files_list(test)
        self.assertTrue(result[0][0].startswith('file://'))
        self.assertEqual(result, expectation)


class TargetNameGeneratorTestCases(unittest.TestCase):
    def setUp(self):
        self.g = TargetNameGenerator()
        self.g.exists = self.never_exists
        self.g.replace_messy_chars = True

        self.s = SoundFile("/path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })

    def tearDown(self):
        self.g = None
        self.s = None

    def never_exists(self, pathname):
        return False

    def always_exists(self, pathname):
        return True

    def test_unquote_filename(self):
        self.assertEqual(unquote_filename('file://baz%20qux'), 'file://baz qux')

    def test_beautify_uri(self):
        self.assertEqual(beautify_uri('file://baz%20qux'), 'baz qux')

    def test_safe_name(self):
        # the "test data" folder has the space in it on purpose for this spec

        # 1. path doesn't exist at all
        self.assertEqual(self.g.safe_name('/b äz/quズx/foo.mp3'), '/b_az/qux/foo.mp3')
        self.assertEqual(self.g.safe_name('/baズz/qux'), '/baz/qux')
        self.assertEqual(self.g.safe_name('./ qux/foズo.mp3'), './_qux/foo.mp3')
        self.assertEqual(self.g.safe_name('./qズux/'), './qux/')
        self.assertEqual(self.g.safe_name('/ズfoo.mp3'), '/foo.mp3')
        self.assertEqual(self.g.safe_name('fooズ.mp3'), 'foo.mp3')
        self.assertEqual(self.g.safe_name('bla /foズo.mp3'), 'bla_/foo.mp3')
        self.assertEqual(self.g.safe_name('blズa/'), 'bla/')
        self.assertEqual(self.g.safe_name('ズblä'), 'bla')

        # 2. the outer dir exists
        self.assertEqual(self.g.safe_name('/home/qфux/foo.mp3'), '/home/qux/foo.mp3')
        self.assertEqual(self.g.safe_name('./foфo.mp3'), './foo.mp3')
        self.assertEqual(self.g.safe_name('./tests/asdf/fфoo.mp3'), './tests/asdf/foo.mp3')
        self.assertEqual(self.g.safe_name('tests/asdf/fooф.mp3'), 'tests/asdf/foo.mp3')

        # 3. all dirs exist (space of 'test data' will be kept)
        original_name = os.getcwd() + '/tests/test data/audio/fâoo.mp3'
        self.assertEqual(self.g.safe_name(original_name), os.getcwd() + '/tests/test data/audio/faoo.mp3')
        self.assertEqual(self.g.safe_name('./tests/test data/fooâ.mp3'), './tests/test data/fooa.mp3')
        self.assertEqual(self.g.safe_name('tests/test data/fфズ oo.mp3â'), 'tests/test data/f_oo.mp3a')
        
        # 4. the complete path exists
        original_name = os.getcwd() + '/tests/test data/audio/a.wav'
        self.assertEqual(self.g.safe_name(original_name), os.getcwd() + '/tests/test data/audio/a.wav')
        self.assertEqual(self.g.safe_name('./tests/test data'), './tests/test data')
        self.assertEqual(self.g.safe_name('tests/test data/'), 'tests/test data/')
        
        # 5. paths with special chars can be transformed into existing paths.
        # Doesn't increment the filename. on_task_finished of gstreamer.py does that later.
        # To reuse paths that were generated from {artist} tags with special characters
        original_name = os.getcwd() + '/tests/test data/âuズdio/â.wav'
        self.assertEqual(self.g.safe_name(original_name), os.getcwd() + '/tests/test data/audio/a.wav')

        # 6. doesn't change %20 spaces in URIs into _20, but rather into _ and keeps the URI scheme
        original_name = 'foo://' + os.getcwd() + '/tests/test%20data/fo%20o.mp3'
        expected_name = 'foo://' + os.getcwd() + '/tests/test%20data/fo_o.mp3'
        self.assertEqual(self.g.safe_name(original_name), expected_name)

    def testSuffix(self):
        self.g.suffix = ".ogg"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/path/to/file.ogg"
        )

    def testNoSuffix(self):
        try:
            self.g.get_target_name(self.s)
        except AssertionError:
            return  # ok
        assert False

    def testNoExtension(self):
        self.g.suffix = ".ogg"
        self.s = SoundFile("/path/to/file")
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/path/to/file.ogg"
        )

    def testBasename(self):
        self.g.suffix = ".ogg"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/path/to/01-Hi_Ho.ogg"
        )

    def testLocation(self):
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(track-number)02d-%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/music/Foo_Bar/IS__TOO/01-Hi_Ho.ogg"
        )

    def testLocationEscape(self):
        self.s = SoundFile("/path/to/file with spaces")
        self.g.replace_messy_chars = False
        self.g.suffix = ".ogg"
        self.g.folder = "/mu sic"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/mu%20sic/file%20with%20spaces.ogg"
        )

    def testURI(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        # self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "ssh:user@server:port///path/to/file.ogg"
        )

    def testURILocalDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "/music"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/music/file.ogg"
        )

    def testURIDistantDestination(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:/music/"

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "ftp:user2@dest-server:another-port:/music/file.ogg"
        )

    def testURIUnicode(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote(
            "///path/to/file with \u041d chars.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "ftp:user2@dest-server:another-port:/m%C3%BBs%C3%AEc/file%20with%20%D0%9D%20chars.ogg"
        )

    def testURIUnicode_utf8(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")
        self.g.replace_messy_chars = False

        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs фズ.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "ftp:user2@dest-server:another-port:" + quote("/mûsîc/file with strângë chàrs фズ.ogg")
        )

    def testURIUnicodeMessy(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        self.g.folder = "ftp:user2@dest-server:another-port:" + quote("/mûsîc/")

        self.s = SoundFile("ssh:user@server:port" + quote("///path/to/file with strângë chàrs.flac"))
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.assertEqual(
            self.g.get_target_name(self.s),
            "ftp:user2@dest-server:another-port:/" + quote("mûsîc") + "/file_with_strange_chars.ogg"
        )

    def testDisplay(self):
        self.g.exists = self.always_exists
        self.g.suffix = ".ogg"
        # self.g.folder = "/")

        self.s = SoundFile("ssh:user@server:port///path/to/file.flac")
        self.assertEqual(
            self.s.filename_for_display,
            "file.flac"
        )
        self.s = SoundFile("ssh:user@server:port///path/to/fîlé.flac")
        self.assertEqual(
            self.s.filename_for_display,
            "fîlé.flac"
        )
        self.s = SoundFile(
            "ssh:user@server:port///path/to/fileфズ.flac"
        )
        self.assertEqual(self.s.filename_for_display, "fileфズ.flac")

    def test8bits(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = False
        self.assertEqual(
            self.g.get_target_name(self.s),
            quote("/path/to/file\xa0\xb0\xc0\xd0.ogg")
        )

    def test8bits_messy(self):
        self.s = SoundFile(quote("/path/to/file\xa0\xb0\xc0\xd0.flac"))
        self.g.suffix = ".ogg"
        self.g.replace_messy_chars = True
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/path/to/file_A.ogg"
        )

    def test8bits_tags(self):
        self.g.replace_messy_chars = False
        self.s = SoundFile("/path/to/fileyop.flac")
        self.s.tags.update({
            "artist": "\xa0\xb0\xc0\xd0",
            "title": "\xa1\xb1\xc1\xd1",
            "album": "\xa2\xb2\xc2\xd2",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.subfolders = "%(artist)s/%(album)s"
        self.g.basename = "%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            quote("/music/\xa0\xb0\xc0\xd0/\xa2\xb2\xc2\xd2/\xa1\xb1\xc1\xd1.ogg")
        )

    def testRoot(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/path/to/file.ogg"
        )

    def testRootPath(self):
        self.s = SoundFile("/path/#to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        # self.g.basename = "%(title)s")
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/music/%23to/file.ogg"
        )

    def testRootCustomPattern(self):
        self.s = SoundFile("/path/#to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11
        })
        self.g.suffix = ".ogg"
        # make sure that a missing genre does not translate to '/filename',
        # because then os.path.join would ignore anything before that and
        # assume the directory should be a child of root.
        self.g.basename = "%(genre)s/%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            # basefolder handling is disabled when the pattern has a /
            "/path/Unknown_Genre/Hi_Ho.ogg"
        )

    def testLeadingSlashPattern(self):
        self.s = SoundFile("/path/#to/file.flac", "/path/")
        self.s.tags.update({
            "title": "Hi Ho"
        })
        self.g.suffix = ".ogg"
        self.g.basename = "/home/foo/%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/home/foo/Hi_Ho.ogg"
        )

    def testRootPathCustomPattern(self):
        self.s = SoundFile("/path/to/file.flac", "/path/")
        self.s.tags.update({
            "artist": "Foo Bar",
            "title": "Hi Ho",
            "album": "IS: TOO",
            "track-number": 1,
            "track-count": 11,
        })
        self.g.suffix = ".ogg"
        self.g.folder = "/music"
        self.g.basename = "%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            "/music/to/Hi_Ho.ogg"
        )

    def testQuote(self):
        self.s = SoundFile(quote("/path%'#/to/file%'#.flac"))
        self.s.tags.update({
            "artist": "Foo%'#Bar",
            "title": "Hi%'#Ho",
        })
        self.g.replace_messy_chars = False
        self.g.suffix = ".ogg"
        self.assertEqual(
            self.g.get_target_name(self.s),
            quote("/path%'#/to/file%'#.ogg")
        )
        self.g.subfolders = "%(artist)s"
        self.g.basename = "%(title)s"
        self.assertEqual(
            self.g.get_target_name(self.s),
            quote("/path%'#/to/Foo%'#Bar/Hi%'#Ho.ogg")
        )


if __name__ == "__main__":
    unittest.main()
