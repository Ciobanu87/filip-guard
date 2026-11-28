"""Offline source-integrity guards; no host mutation or child execution."""
from hashlib import sha256
import io
import tarfile
import unittest
from unittest.mock import patch
import deployment.oracle_autofix_native_pilot as pilot


class NativePilotGuards(unittest.TestCase):
    def test_wrong_source_is_refused_before_extraction(self):
        with self.assertRaises(ValueError):pilot.archive_files(b'unreviewed source')
    def test_traversal_and_links_are_refused_even_for_a_checked_container(self):
        for name,kind in (('../escape',tarfile.REGTYPE),('linked',tarfile.SYMTYPE)):
            output=io.BytesIO()
            with tarfile.open(fileobj=output,mode='w') as archive:
                member=tarfile.TarInfo(name);member.type=kind
                if kind==tarfile.SYMTYPE:member.linkname='/srv/filip-guard/state'
                archive.addfile(member)
            raw=output.getvalue()
            with patch.object(pilot,'SOURCE_BYTES',len(raw)),patch.object(pilot,'SOURCE_SHA256',sha256(raw).hexdigest()):
                with self.assertRaisesRegex(ValueError,'Unsafe candidate entry'):pilot.archive_files(raw)
