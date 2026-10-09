import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pharmacy_platform import main
from pharmacy_platform.foundry_tools import (
    GESTION_AGENT_TOOLS,
    create_foundry_tools,
    create_foundry_voice_tools,
    instructions_for_role,
)
from pharmacy_platform.sharepoint import SharePointError


class AgentToolTests(unittest.TestCase):
    def _mock_foundry(self, response_text="Réponse stock."):
        response = SimpleNamespace(id="response-1", output=[], output_text=response_text)
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.return_value = response
        client.conversations.create.return_value = SimpleNamespace(id="conversation-1")
        project = MagicMock()
        project.__enter__.return_value = project
        project.get_openai_client.return_value = client
        credential = MagicMock()
        credential.__enter__.return_value = credential
        return credential, project, client

    def test_inventory_question_uses_sqlite_context_without_sharepoint(self) -> None:
        credential, project, client = self._mock_foundry()
        snapshot = {
            "products": [{"name": "Produit test", "quantity": 0, "min_quantity": 5}],
            "commands": [],
            "movements": [],
            "truncated": False,
        }
        tool_call = SimpleNamespace(
            type="function_call",
            name="get_inventory_snapshot",
            arguments="{}",
            call_id="snapshot-1",
        )
        client.responses.create.side_effect = [
            SimpleNamespace(id="response-1", output=[tool_call], output_text=""),
            SimpleNamespace(id="response-2", output=[], output_text="Réponse stock."),
        ]
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch("pharmacy_platform.main.read_configured_documents", side_effect=AssertionError("SharePoint should not be read")),
            patch("pharmacy_platform.main._inventory_snapshot", return_value=snapshot),
            patch("azure.ai.projects.AIProjectClient", return_value=project),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
        ):
            result = main._foundry_reply("GestionAgent", "Quels produits sont en stock critique ?")

        self.assertEqual(result["reply"], "Réponse stock.")
        self.assertEqual(result["sharepoint_sources"], [])
        request = client.responses.create.call_args_list[0].kwargs
        self.assertNotIn("model", request)
        self.assertNotIn("tools", request)
        self.assertEqual(
            request["extra_body"],
            {"agent_reference": {"name": "GestionAgent", "type": "agent_reference"}},
        )
        self.assertEqual(request["input"], "Quels produits sont en stock critique ?")
        self.assertEqual(request["conversation"], "conversation-1")
        self.assertEqual(project.get_openai_client.call_args.kwargs, {})
        function_output = client.responses.create.call_args_list[1].kwargs["input"][0]
        self.assertEqual(function_output["type"], "function_call_output")
        snapshot_result = json.loads(function_output["output"])
        self.assertEqual(snapshot_result["products"][0]["quantity"], 0)
        client.conversations.delete.assert_called_once_with(conversation_id="conversation-1")

    def test_explicit_sharepoint_question_surfaces_missing_configuration(self) -> None:
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch(
                "pharmacy_platform.main.read_configured_documents",
                side_effect=SharePointError("Configuration SharePoint manquante."),
            ) as read_documents,
        ):
            with self.assertRaisesRegex(main.HTTPException, "Configuration SharePoint manquante"):
                main._foundry_reply("GestionAgent", "Que dit le document SharePoint sur les réceptions ?")
        read_documents.assert_called_once_with(main.settings)

    def test_coordinator_prompt_does_not_trigger_sharepoint_for_stock_question(self) -> None:
        question = "Quelle sont les produits avec un stock critique?"
        self.assertFalse(main._requests_reference_documents(question))

        def specialist_reply(name, _message, *, request_reference_documents=None):
            return {"reply": f"Analyse de {name}", "web_sources": []}

        with (
            patch("pharmacy_platform.main._inventory_snapshot", return_value={}),
            patch("pharmacy_platform.main._foundry_reply", side_effect=specialist_reply) as call_agent,
        ):
            prompt, _reports = main._coordinator_prompt(question)

        self.assertTrue(main._requests_reference_documents(prompt))
        self.assertEqual(call_agent.call_count, 3)
        self.assertTrue(all(
            call.kwargs["request_reference_documents"] is False
            for call in call_agent.call_args_list
        ))

    def test_coordinator_sends_original_question_sharepoint_intent_to_foundry(self) -> None:
        question = "Quelle sont les produits avec un stock critique?"
        with (
            patch(
                "pharmacy_platform.main._coordinator_prompt",
                return_value=("Demande\nDocuments de référence: []", []),
            ),
            patch("pharmacy_platform.main._foundry_reply", return_value={"reply": "Réponse"}) as call_agent,
        ):
            result = main.coordinator_chat(main.ChatInput(message=question))

        self.assertEqual(result["reply"], "Réponse")
        self.assertEqual(call_agent.call_args.args[0], main.settings.foundry_agent_names[3])
        self.assertIs(call_agent.call_args.kwargs["request_reference_documents"], False)
        self.assertNotIn(
            "/api/chat/voice",
            {route.path for route in main.app.routes},
        )

    def test_synthetic_coordinator_prompt_does_not_read_sharepoint(self) -> None:
        credential, project, _client = self._mock_foundry()
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch(
                "pharmacy_platform.main.read_configured_documents",
                side_effect=AssertionError("Synthetic prompt must not request SharePoint"),
            ),
            patch("azure.ai.projects.AIProjectClient", return_value=project),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
        ):
            result = main._foundry_reply(
                "GestionAgent",
                "Demande utilisateur: Quels produits?\nDocuments de référence: []",
                request_reference_documents=False,
            )

        self.assertEqual(result["reply"], "Réponse stock.")
        self.assertEqual(result["sharepoint_sources"], [])

    def test_missing_azure_credentials_returns_actionable_error(self) -> None:
        from azure.core.exceptions import ClientAuthenticationError

        credential = MagicMock()
        credential.__enter__.side_effect = ClientAuthenticationError("sensitive auth details")
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch("pharmacy_platform.main.read_configured_documents", return_value=[]),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
            self.assertRaises(main.HTTPException) as context,
        ):
            main._foundry_reply("GestionAgent", "Quels produits sont en stock critique ?")
        self.assertEqual(context.exception.status_code, 503)
        self.assertIn("az login", context.exception.detail)
        self.assertNotIn("sensitive auth details", context.exception.detail)

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
        client.conversations.create.return_value = SimpleNamespace(id="conversation-2")
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
        self.assertEqual(
            client.responses.create.call_args_list[0].kwargs["extra_body"],
            {"agent_reference": {"name": "GestionAgent", "type": "agent_reference"}},
        )

    def test_foundry_bad_request_includes_safe_provider_detail(self) -> None:
        from openai import BadRequestError

        credential, project, client = self._mock_foundry()
        error = BadRequestError(
            "Bad request",
            response=MagicMock(status_code=400, headers={}),
            body={
                "error": {
                    "code": "invalid_payload",
                    "message": "Invalid deployment request.",
                    "param": "model",
                }
            },
        )
        client.responses.create.side_effect = error
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch("pharmacy_platform.main.read_configured_documents", return_value=[]),
            patch("azure.ai.projects.AIProjectClient", return_value=project),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
            self.assertRaises(main.HTTPException) as context,
        ):
            main._foundry_reply("GestionAgent", "Quels produits sont en stock critique ?")
        self.assertEqual(context.exception.status_code, 502)
        self.assertIn("invalid_payload", context.exception.detail)
        self.assertIn("model", context.exception.detail)
        self.assertIn("Invalid deployment request", context.exception.detail)

    def test_agent_definition_contains_sqlite_function_tools_and_policy(self) -> None:
        from azure.ai.projects.models import PromptAgentDefinition

        tools = create_foundry_tools()
        agent = PromptAgentDefinition(
            model="deployment",
            instructions=instructions_for_role("Gestionnaire"),
            tools=tools,
        )
        self.assertEqual(
            {tool.name for tool in agent.tools},
            {
                "get_inventory_snapshot",
                "propose_product",
                "propose_command",
                "propose_movement",
            },
        )
        self.assertIn("appelle get_inventory_snapshot", agent.instructions)
        self.assertIn("confirmer dans l'interface", agent.instructions)
        self.assertIn("pas de Markdown", agent.instructions)
        self.assertIn("une ou deux phrases suffisent", agent.instructions)
        self.assertIn("bases de connaissances Foundry", agent.instructions)
        self.assertIn("rechercher des fournisseurs en ligne", agent.instructions)

    def test_inventory_email_tool_is_only_added_when_requested(self) -> None:
        from azure.ai.projects.models import PromptAgentDefinition

        standard_tools = create_foundry_tools()
        gestion_tools = create_foundry_tools(enable_inventory_email=True)
        self.assertNotIn(
            GESTION_AGENT_TOOLS[0]["name"],
            {tool.name for tool in standard_tools},
        )
        gestion_agent = PromptAgentDefinition(
            model="deployment",
            instructions=instructions_for_role("Gestionnaire"),
            tools=gestion_tools,
        )
        self.assertIn(
            GESTION_AGENT_TOOLS[0]["name"],
            {tool.name for tool in gestion_agent.tools},
        )

    def test_voice_tools_include_inventory_tools_and_email(self) -> None:
        from azure.ai.projects.models import VoiceAgentDefinition, VoiceModelType

        voice_tools = create_foundry_voice_tools(enable_inventory_email=True)
        definition = VoiceAgentDefinition(
            model_type=VoiceModelType.MANAGED,
            model="gpt-realtime",
            instructions="Instructions du test",
            tools=voice_tools,
        )
        names = {tool.name for tool in definition.tools}
        self.assertEqual(
            names,
            {
                "get_inventory_snapshot",
                "propose_product",
                "propose_command",
                "propose_movement",
                "send_inventory_report_email",
            },
        )
        self.assertNotIn(
            GESTION_AGENT_TOOLS[0]["name"],
            {tool.name for tool in create_foundry_voice_tools()},
        )
        preserved = VoiceAgentDefinition(
            **{
                **definition.as_dict(),
                "instructions": "Instructions mises à jour",
                "tools": create_foundry_voice_tools(enable_inventory_email=True),
            }
        )
        self.assertEqual(preserved.model, "gpt-realtime")
        self.assertEqual(preserved.model_type, VoiceModelType.MANAGED)
        self.assertEqual(preserved.instructions, "Instructions mises à jour")

    def test_foundry_reply_rejects_voice_agents_without_realtime_session(self) -> None:
        from azure.ai.projects.models import VoiceAgentDefinition, VoiceModelType

        credential, project, client = self._mock_foundry()
        project.agents.get.return_value.versions.latest.definition = VoiceAgentDefinition(
            model_type=VoiceModelType.MANAGED,
            model="gpt-realtime",
            instructions="Instructions du test",
        )
        with (
            patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
            patch("pharmacy_platform.main.read_configured_documents", return_value=[]),
            patch("azure.ai.projects.AIProjectClient", return_value=project),
            patch("azure.identity.DefaultAzureCredential", return_value=credential),
        ):
            with self.assertRaises(main.HTTPException) as context:
                main._foundry_reply("GestionAgent", "Bonjour")

        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("mode Voice", context.exception.detail)
        client.responses.create.assert_not_called()
        project.beta.voice_agents.realtime.connect.assert_not_called()

    def test_command_agent_can_be_created_with_foundry_web_search(self) -> None:
        from azure.ai.projects.models import PromptAgentDefinition

        tools = create_foundry_tools(
            "web-search-connection",
            "pharmastock",
            enable_web_search=True,
        )
        agent = PromptAgentDefinition(
            model="deployment",
            instructions=instructions_for_role("CommandeStockAgent"),
            tools=tools,
        )
        self.assertIn("rechercher des fournisseurs en ligne", agent.instructions)
        search_tool = next(tool for tool in agent.tools if tool.type == "web_search")
        self.assertEqual(
            search_tool.as_dict()["custom_search_configuration"],
            {
                "project_connection_id": "web-search-connection",
                "instance_name": "pharmastock",
            },
        )

    def test_coordinator_queries_each_specialist_with_current_snapshot(self) -> None:
        snapshot = {"products": [{"name": "Produit test", "quantity": 0}], "commands": [], "movements": []}

        def specialist_reply(name, _message, *, request_reference_documents=None):
            return {"reply": f"Analyse de {name}", "web_sources": []}

        with (
            patch("pharmacy_platform.main._inventory_snapshot", return_value=snapshot),
            patch("pharmacy_platform.main._foundry_reply", side_effect=specialist_reply) as call_agent,
        ):
            prompt, reports = main._coordinator_prompt("Que faut-il commander ?")

        self.assertEqual(call_agent.call_count, 3)
        self.assertEqual(len(reports), 3)
        self.assertIn('"quantity": 0', prompt)
        self.assertIn("Analyse de CommandeStockAgent", prompt)
        command_agent_message = call_agent.call_args_list[0].args[1]
        self.assertIn("recherche en ligne", command_agent_message)
        self.assertIn("cite les URL", command_agent_message)
        movement_agent_call = next(
            call
            for call in call_agent.call_args_list
            if call.args[0] == main.settings.foundry_agent_names[1]
        )
        movement_agent_message = movement_agent_call.args[1]
        self.assertIn("quantités totales déplacées", movement_agent_message)
        self.assertIn("movement_summary", movement_agent_message)
        self.assertIn(
            f"compte rendu de {main.settings.foundry_agent_names[1]}",
            prompt,
        )

    def test_inventory_snapshot_summarizes_full_movement_history_and_sorts_recent(self) -> None:
        movements = [
            {"id": "old", "type": "entree", "quantity": 4, "date": "2024-01-01", "product_name": "Produit A"},
            {"id": "recent", "type": "sortie", "quantity": 2, "date": "2026-10-05", "product_name": "Produit A"},
            {"id": "older", "type": "sortie", "quantity": 3, "date": "2025-02-01", "product_name": "Produit B"},
        ]
        with (
            patch.object(main.store, "products", return_value=[]),
            patch.object(main.store, "commands", return_value=[]),
            patch.object(main.store, "movements", return_value=movements),
        ):
            snapshot = main._inventory_snapshot()

        self.assertEqual(snapshot["movement_history_count"], 3)
        self.assertEqual(snapshot["movement_summary"]["entree"]["movement_count"], 1)
        self.assertEqual(snapshot["movement_summary"]["entree"]["total_quantity"], 4)
        self.assertEqual(snapshot["movement_summary"]["sortie"]["movement_count"], 2)
        self.assertEqual(snapshot["movement_summary"]["sortie"]["total_quantity"], 5)
        self.assertEqual(snapshot["movements"][0]["id"], "recent")

    def test_inventory_email_tool_sends_report_to_configured_recipients(self) -> None:
        products = [
            {
                "product_code": "MED001",
                "name": "Produit critique",
                "quantity": 0,
                "min_quantity": 3,
                "unit_price": 250,
            },
            {
                "product_code": "MED002",
                "name": "Produit normal",
                "quantity": 8,
                "min_quantity": 3,
                "unit_price": 100,
            },
        ]
        with (
            patch.object(main.settings, "smtp_host", "smtp.example.test"),
            patch.object(main.settings, "smtp_from", "pharmacie@example.test"),
            patch.object(
                main.settings,
                "smtp_recipients",
                ["gestion@example.test", "direction@example.test"],
            ),
            patch.object(main.store, "products", return_value=products),
            patch("pharmacy_platform.main.make_alerts", return_value=[]),
            patch("pharmacy_platform.main._deliver_email") as deliver_email,
        ):
            result = main._send_inventory_report_email()

        self.assertEqual(result["recipient_count"], 2)
        self.assertEqual(result["product_count"], 2)
        self.assertEqual(result["critical_count"], 1)
        email = deliver_email.call_args.args[0]
        self.assertEqual(
            email["To"],
            "gestion@example.test, direction@example.test",
        )
        self.assertIn("MED001 | 0 | 3", email.get_content())
        self.assertIn("Unités en stock : 8", email.get_content())

    def test_only_gestion_agent_can_execute_inventory_email_tool(self) -> None:
        tool_call = SimpleNamespace(
            type="function_call",
            name="send_inventory_report_email",
            arguments="{}",
            call_id="email-1",
        )

        def invoke(agent_name):
            credential, project, client = self._mock_foundry()
            client.responses.create.side_effect = [
                SimpleNamespace(id="response-1", output=[tool_call], output_text=""),
                SimpleNamespace(id="response-2", output=[], output_text="Terminé."),
            ]
            with (
                patch.object(main.settings, "foundry_project_endpoint", "https://example.test"),
                patch("pharmacy_platform.main.read_configured_documents", return_value=[]),
                patch("azure.ai.projects.AIProjectClient", return_value=project),
                patch("azure.identity.DefaultAzureCredential", return_value=credential),
                patch(
                    "pharmacy_platform.main._send_inventory_report_email",
                    return_value={"sent": True},
                ) as send_email,
            ):
                main._foundry_reply(agent_name, "Envoie l'état du stock par e-mail.")
            output = client.responses.create.call_args_list[1].kwargs["input"][0]
            return json.loads(output["output"]), send_email

        success, send_email = invoke("GestionAgent")
        self.assertEqual(success, {"sent": True})
        send_email.assert_called_once_with()

        denied, send_email = invoke("EntreesSortiesAgent")
        self.assertEqual(denied, {"error": "Cet outil est réservé à GestionAgent."})
        send_email.assert_not_called()

    def test_web_search_citations_are_returned_as_source_links(self) -> None:
        citation = SimpleNamespace(
            url_citation=SimpleNamespace(
                url="https://supplier.example/products",
                title="Fournisseur officiel",
            )
        )
        response = SimpleNamespace(output=[
            SimpleNamespace(content=[
                SimpleNamespace(annotations=[citation, citation]),
            ]),
        ])
        self.assertEqual(
            main._response_web_sources(response),
            [{
                "title": "Fournisseur officiel",
                "url": "https://supplier.example/products",
            }],
        )

    def test_recommendations_include_reorder_quantities_without_duplicate_open_orders(self) -> None:
        products = [
            {"id": "p1", "name": "Rupture", "quantity": 0, "min_quantity": 5},
            {"id": "p2", "name": "Déjà commandé", "quantity": 1, "min_quantity": 4},
        ]
        commands = [{
            "product_name": "déjà commandé",
            "status": "Commandée",
        }]
        with (
            patch.object(main.store, "products", return_value=products),
            patch.object(main.store, "commands", return_value=commands),
            patch("pharmacy_platform.main.make_alerts", return_value=[]),
        ):
            result = main.recommendations()

        self.assertEqual(
            result["orders"],
            [{
                "product_id": "p1",
                "product_name": "Rupture",
                "product_code": None,
                "supplier": None,
                "unit_price": None,
                "current_quantity": 0,
                "min_quantity": 5,
                "quantity": 5,
                "priority": "critical",
            }],
        )

    def test_agent_reply_removes_markdown_bold_markers(self) -> None:
        self.assertEqual(
            main._plain_agent_reply("Le stock contient **50 produits**.\n\n**À noter :** aucun zéro."),
            "Le stock contient 50 produits.\n\nÀ noter : aucun zéro.",
        )


if __name__ == "__main__":
    unittest.main()
