import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pharmacy_platform import main


class AgentToolTests(unittest.TestCase):
    def test_excel_addition_is_only_proposed_until_user_confirms(self) -> None:
        proposal_call = SimpleNamespace(
            type="function_call",
            name="propose_product",
            arguments=(
                '{"name":"Gants","category":"Consommable","quantity":20,'
                '"min_quantity":5,"unit_price":1.5,"expiry_date":null}'
            ),
            call_id="call-1",
        )
        proposal_response = SimpleNamespace(id="response-1", output=[proposal_call], output_text="")
        final_response = SimpleNamespace(id="response-2", output=[], output_text="Voici la proposition.")
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.side_effect = [proposal_response, final_response]
        project = MagicMock()
        project.__enter__.return_value = project
        project.get_openai_client.return_value = client
        credential = MagicMock()
        credential.__enter__.return_value = credential

        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch("pharmacy_platform.main.read_configured_documents", return_value=[]),
            patch("azure.ai.projects.AIProjectClient", return_value=project),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
            patch.object(main.store, "add_product") as add_product,
        ):
            result = main._foundry_reply("GestionAgent", "Ajoute 20 gants.")

        self.assertEqual(result["reply"], "Voici la proposition.")
        self.assertEqual(result["proposals"], [{
            "type": "product",
            "data": {
                "name": "Gants",
                "category": "Consommable",
                "quantity": 20,
                "min_quantity": 5,
                "unit_price": 1.5,
                "expiry_date": None,
            },
        }])
        add_product.assert_not_called()
        self.assertEqual(client.responses.create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
