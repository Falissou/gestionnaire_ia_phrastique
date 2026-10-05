"""Read explicitly configured documents from a SharePoint document library."""

from io import BytesIO
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import ClientSecretCredential
from pypdf.errors import PdfReadError
from pypdf import PdfReader

from pharmacy_platform.config import Settings

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
MAX_DOCUMENTS = 10
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_TEXT = 80_000


class SharePointError(RuntimeError):
    """A SharePoint document could not be retrieved or parsed."""


def _document_text(path: str, content: bytes) -> str:
    extension = PurePosixPath(path).suffix.lower()
    try:
        if extension in {".txt", ".md"}:
            return content.decode("utf-8-sig")
        if extension == ".docx":
            with ZipFile(BytesIO(content)) as archive:
                document = ElementTree.fromstring(archive.read("word/document.xml"))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            return "\n".join(
                "".join(text.text or "" for text in paragraph.findall(".//w:t", namespace))
                for paragraph in document.findall(".//w:p", namespace)
            )
        if extension == ".pdf":
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages[:100])
    except (BadZipFile, KeyError, UnicodeDecodeError, ValueError, ElementTree.ParseError, PdfReadError) as exc:
        raise SharePointError(f"Le document SharePoint {path!r} est illisible.") from exc
    raise SharePointError(
        f"Format non pris en charge pour {path!r}; utilisez .docx, .pdf, .txt ou .md."
    )


def read_configured_documents(settings: Settings) -> list[dict[str, str]]:
    """Download only the configured library-relative file paths."""
    if not settings.sharepoint_enabled:
        return []
    required = (
        settings.sharepoint_tenant_id,
        settings.sharepoint_client_id,
        settings.sharepoint_client_secret,
        settings.sharepoint_drive_id,
        settings.sharepoint_document_paths,
    )
    if not all(required):
        raise SharePointError(
            "La configuration SharePoint est incomplète; renseignez le tenant, "
            "l'application, la bibliothèque et les chemins des documents."
        )
    paths = settings.sharepoint_document_paths
    if len(paths) > MAX_DOCUMENTS:
        raise SharePointError(f"Configurez au plus {MAX_DOCUMENTS} documents SharePoint.")
    for path in paths:
        if path.startswith("/") or ".." in PurePosixPath(path).parts:
            raise SharePointError("Les chemins SharePoint doivent rester relatifs à la bibliothèque.")

    documents = []
    total_text = 0
    try:
        with ClientSecretCredential(
            tenant_id=settings.sharepoint_tenant_id,
            client_id=settings.sharepoint_client_id,
            client_secret=settings.sharepoint_client_secret,
        ) as credential:
            token = credential.get_token(GRAPH_SCOPE).token
            for path in paths:
                encoded_path = quote(path, safe="/")
                url = (
                    "https://graph.microsoft.com/v1.0/drives/"
                    f"{quote(settings.sharepoint_drive_id, safe='')}/root:/{encoded_path}:/content"
                )
                request = Request(url, headers={"Authorization": f"Bearer {token}"})
                with urlopen(request, timeout=20) as response:
                    if int(response.headers.get("Content-Length", "0") or 0) > MAX_DOCUMENT_BYTES:
                        raise SharePointError(f"Le document {path!r} dépasse la taille autorisée.")
                    content = response.read(MAX_DOCUMENT_BYTES + 1)
                if len(content) > MAX_DOCUMENT_BYTES:
                    raise SharePointError(f"Le document {path!r} dépasse la taille autorisée.")
                text = _document_text(path, content).strip()
                total_text += len(text)
                if total_text > MAX_TOTAL_TEXT:
                    raise SharePointError(
                        f"Le contenu des documents dépasse la limite de {MAX_TOTAL_TEXT} caractères."
                    )
                documents.append({"path": path, "content": text})
    except SharePointError:
        raise
    except (ClientAuthenticationError, HTTPError, URLError, OSError, ValueError) as exc:
        raise SharePointError(
            "Impossible de récupérer les documents SharePoint; vérifiez les identifiants, "
            "les autorisations Microsoft Graph et les chemins configurés."
        ) from exc
    return documents
