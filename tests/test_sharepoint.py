import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from pharmacy_platform.sharepoint import (
    SharePointError,
    _document_text,
    read_configured_documents,
)


def configured_settings(paths: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        sharepoint_enabled=True,
        sharepoint_tenant_id="tenant",
        sharepoint_client_id="client",
        sharepoint_client_secret="secret",
        sharepoint_drive_id="drive",
        sharepoint_document_paths=paths,
    )


class SharePointDocumentTests(unittest.TestCase):
    def test_unconfigured_sharepoint_returns_no_documents(self) -> None:
        settings = SimpleNamespace(sharepoint_enabled=False)
        self.assertEqual(read_configured_documents(settings), [])

    def test_text_document_is_decoded(self) -> None:
        self.assertEqual(_document_text("guide.txt", b"Consigne de reception"), "Consigne de reception")

    def test_docx_text_is_extracted(self) -> None:
        content = BytesIO()
        with ZipFile(content, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                "<w:body><w:p><w:r><w:t>Reception</w:t></w:r></w:p>"
                "<w:p><w:r><w:t>Produits</w:t></w:r></w:p></w:body></w:document>",
            )
        self.assertEqual(_document_text("guide.docx", content.getvalue()), "Reception\nProduits")

    def test_parent_traversal_is_rejected(self) -> None:
        with self.assertRaises(SharePointError):
            read_configured_documents(configured_settings(["../private/secret.txt"]))

    def test_only_allowlisted_documents_are_downloaded(self) -> None:
        credential = MagicMock()
        credential.get_token.return_value.token = "access-token"
        response = MagicMock()
        response.__enter__.return_value.headers = {"Content-Length": "4"}
        response.__enter__.return_value.read.return_value = b"Plan"
        with (
            patch("pharmacy_platform.sharepoint.ClientSecretCredential", return_value=credential),
            patch("pharmacy_platform.sharepoint.urlopen", return_value=response) as urlopen,
        ):
            documents = read_configured_documents(configured_settings(["Ops/Plan.txt"]))

        self.assertEqual(documents, [{"path": "Ops/Plan.txt", "content": "Plan"}])
        self.assertEqual(urlopen.call_count, 1)
        self.assertIn("/root:/Ops/Plan.txt:/content", urlopen.call_args.args[0].full_url)


if __name__ == "__main__":
    unittest.main()
