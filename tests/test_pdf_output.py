"""File-output integration tests; no driver or physical printer is invoked."""
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfReader, PdfWriter
from pex import config
from pex.services import printer, server
from pex.utils import deep_get


class PdfOutputTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.pdf = self.root / 'source.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=105 / printer.PT_TO_MM, height=148 / printer.PT_TO_MM)
        writer.write(self.pdf)
        self.original = self.pdf.read_bytes()
        self.root_patch = patch.object(config, 'ROOT_PATH', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def tearDown(self):
        manager = server.app.extensions.pop('pex_jobs', None)
        if manager:
            manager.close()

    def test_both_pdf_drivers_export_exact_original_without_sumatra(self):
        for driver in ['Adobe PDF Converter', 'Microsoft Print To PDF']:
            with self.subTest(driver=driver):
                api = MagicMock()
                api.GetPrinter.return_value = {'pDriverName': driver}
                with patch.object(printer, 'win32print', api, create=True), patch.object(printer.subprocess, 'run') as run:
                    result = printer._print_on_windows(str(self.pdf), 'Renamed virtual queue', (105,148), 'portrait', 1)
                    run.assert_not_called()
                    api.SetPrinter.assert_not_called()
                    self.assertEqual(result['backend'], 'pdf-file')
                    output = Path(result['output_file'])
                    self.assertEqual(output.parent, self.root / 'output')
                    self.assertEqual(output.read_bytes(), self.original)
                    self.assertEqual(self.pdf.read_bytes(), self.original)
        self.assertEqual(len(list((self.root / 'output').glob('*.pdf'))), 2)

    def test_multiple_copies_repeat_original_pages(self):
        result = printer._save_pdf_output(str(self.pdf), (105,148), 'portrait', 3)
        reader = PdfReader(result['output_file'])
        self.assertEqual(len(reader.pages), 3)
        printer._validate_pdf_paper(result['output_file'], (105,148), 'portrait')

    def test_invalid_dimensions_create_no_output(self):
        with self.assertRaises(ValueError):
            printer._save_pdf_output(str(self.pdf), (100,50), 'landscape', 1)
        self.assertFalse((self.root / 'output').exists())

    def test_existing_destination_is_never_overwritten_or_deleted(self):
        directory = self.root / 'output'
        directory.mkdir()
        destination = directory / 'pex-collision.pdf'
        destination.write_bytes(b'keep existing file')
        with patch.object(printer.uuid, 'uuid4', return_value=SimpleNamespace(hex='collision')):
            with self.assertRaises(FileExistsError):
                printer._save_pdf_output(str(self.pdf), (105,148), 'portrait', 1)
        self.assertEqual(destination.read_bytes(), b'keep existing file')

    def test_physical_driver_is_not_a_pdf_destination(self):
        api = MagicMock()
        api.GetPrinter.return_value = {'pDriverName': 'HP Universal Printing PCL 6'}
        with patch.object(printer, 'win32print', api, create=True):
            self.assertFalse(printer._is_windows_pdf_printer('Physical printer'))

    def test_http_api_exports_and_replays_without_duplicate_files(self):
        settings = config._default_config()
        settings['server'].update(token='test-token', cors=[])
        settings['printer_default'] = 'Virtual queue'
        settings['printers'] = {}
        api = MagicMock()
        api.GetPrinter.return_value = {'pDriverName': 'Adobe PDF Converter'}
        with patch.object(config, 'get_option', side_effect=lambda key, default=None: deep_get(settings, key, default)), patch.object(printer, 'list_printers', return_value=['Virtual queue']), patch.object(printer, 'win32print', api, create=True), patch.object(printer.subprocess, 'run') as run:
            client = server.app.test_client()
            outputs = []
            for _ in range(2):
                response = client.post('/pex/print', data={'file': (io.BytesIO(self.original), 'label.pdf'), 'printer': 'Virtual queue', 'paper_format': 'A6'}, headers={'Authorization': 'Bearer test-token', 'Idempotency-Key': 'one-pdf-output'})
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual(response.json['result']['message'], 'PDF saved to file.')
                job = response.json['result']['job']
                self.assertEqual(job['state'], 'submitted')
                self.assertEqual(job['result']['backend'], 'pdf-file')
                outputs.append(job['result']['output_file'])
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(Path(outputs[0]).read_bytes(), self.original)
            self.assertEqual(len(list((self.root / 'output').glob('*.pdf'))), 1)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
