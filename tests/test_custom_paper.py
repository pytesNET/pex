"""Custom-paper regression tests; never submit to a real printer."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfWriter
from pypdf.generic import FloatObject, NameObject, RectangleObject
from pex.services import printer


class CustomPaperTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.file = Path(self.folder.name) / 'label.pdf'
        self.pdf_driver = patch.object(printer, '_is_windows_pdf_printer', return_value=False)
        self.pdf_driver.start()
        self.addCleanup(self.pdf_driver.stop)

    def pdf(self, sizes, rotation=0, user_unit=1, encrypted=False):
        writer = PdfWriter()
        for width, height in sizes:
            page = writer.add_blank_page(width=width / printer.PT_TO_MM,
                                         height=height / printer.PT_TO_MM)
            if rotation:
                page.rotate(rotation)
            if user_unit != 1:
                page[NameObject('/UserUnit')] = FloatObject(user_unit)
        if encrypted:
            writer.encrypt('password')
        writer.write(self.file)

    def test_accepts_a6_portrait_without_a_driver_form(self):
        self.pdf([(105, 148)])
        api = MagicMock()
        api.GetPrinter.return_value = {'pPortName': 'PORT'}
        api.DeviceCapabilities.side_effect = [[9], [{'x': 2100, 'y': 2970}]]
        with patch.object(printer, 'win32print', api, create=True), patch.object(printer, '_get_sumatra_path', return_value='sumatra.exe'), patch.object(printer, '_timeout', return_value=10), patch.object(printer.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            printer._print_on_windows(str(self.file), 'Adobe PDF', (105, 148), 'portrait', 2)
            self.assertEqual(run.call_args.args[0], ['sumatra.exe', '-silent', '-print-to', 'Adobe PDF', '-print-settings', 'noscale,2x,paperkind=0', str(self.file)])
            api.SetPrinter.assert_not_called()
            api.AddForm.assert_not_called()

    def test_custom_landscape_and_multiple_identical_pages(self):
        self.pdf([(100, 50), (100, 50)])
        printer._validate_pdf_paper(str(self.file), (50, 100), 'landscape')

    def test_rotated_pdf_uses_effective_page_size(self):
        self.pdf([(105, 148)], rotation=90)
        printer._validate_pdf_paper(str(self.file), (105, 148), 'landscape')

    def test_user_unit_is_included(self):
        self.pdf([(52.5, 74)], user_unit=2)
        printer._validate_pdf_paper(str(self.file), (105, 148), 'portrait')

    def test_half_millimetre_tolerance(self):
        self.pdf([(105.2, 147.9)])
        printer._validate_pdf_paper(str(self.file), (105, 148), 'portrait')

    def test_rejects_wrong_size_orientation_or_mixed_pages(self):
        for sizes, orientation in [([(210, 297)], 'portrait'), ([(148, 105)], 'portrait'), ([(105, 148), (210, 297)], 'portrait')]:
            with self.subTest(sizes=sizes, orientation=orientation):
                self.pdf(sizes)
                with self.assertRaises(ValueError):
                    printer._validate_pdf_paper(str(self.file), (105, 148), orientation)

    def test_rejects_empty_encrypted_and_invalid_pdf(self):
        for sizes, encrypted in [([], False), ([(105, 148)], True)]:
            self.pdf(sizes, encrypted=encrypted)
            with self.assertRaises(ValueError):
                printer._validate_pdf_paper(str(self.file), (105, 148), 'portrait')
        self.file.write_bytes(b'%PDF-1.4 broken')
        with self.assertRaises(ValueError):
            printer._validate_pdf_paper(str(self.file), (105, 148), 'portrait')

    def test_invalid_pdf_never_reaches_print_submission(self):
        self.pdf([(210, 297)])
        with patch.object(printer, '_windows_paper', return_value=None), patch.object(printer.subprocess, 'run') as run:
            with self.assertRaises(ValueError):
                printer._print_on_windows(str(self.file), 'Adobe PDF', (105, 148), 'portrait', 1)
            run.assert_not_called()

    def test_inconsistent_driver_data_still_fails(self):
        api = MagicMock()
        api.GetPrinter.return_value = {'pPortName': 'PORT'}
        api.DeviceCapabilities.side_effect = [[9], []]
        with patch.object(printer, 'win32print', api, create=True), self.assertRaises(ValueError):
            printer._windows_paper('P', (105, 148))


if __name__ == '__main__':
    unittest.main()
