"""Create the four pharmacy stock-management agents in Microsoft Foundry."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pharmacy_platform.config import AGENT_ROLES, Settings  # noqa: E402
from pharmacy_platform.foundry_tools import (  # noqa: E402
    AGENT_TOOLS,
    GESTION_AGENT_TOOLS,
    create_foundry_tools,
    create_foundry_voice_tools,
    instructions_for_role,
)

WEB_SEARCH_TOOL_TYPES = {
    "web_search",
    "web_search_2025_08_26",
    "web_search_preview",
    "web_search_preview_2025_03_11",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="all",
        help="Create all agents, or one configured Foundry agent by name.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Create a new version of existing agents with the SQLite function tools.",
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.foundry_project_endpoint or not settings.foundry_model_deployment:
        raise SystemExit(
            "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT are required in .env."
        )

    names = settings.foundry_agent_names
    if args.agent == "all":
        selected = list(zip(names, AGENT_ROLES.values()))
    elif args.agent == settings.foundry_voice_agent_name:
        selected = [(args.agent, AGENT_ROLES[names[3]])]
    else:
        try:
            selected = [(args.agent, AGENT_ROLES[list(AGENT_ROLES)[names.index(args.agent)]])]
        except ValueError:
            parser.error(f"Unknown agent {args.agent!r}. Configured agents: {', '.join(names)}")

    try:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition, VoiceAgentDefinition
        from azure.core.exceptions import ResourceNotFoundError
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise SystemExit(
            "Foundry dependencies are missing. Install them with: pip install -r requirements.txt"
        ) from exc

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=credential) as project,
    ):
        for name, instructions in selected:
            try:
                existing = project.agents.get(agent_name=name)
            except ResourceNotFoundError:
                existing = None

            if existing and not args.update:
                print(f"{name} already exists (version {existing.version}); left unchanged.")
                continue

            application_tool_names = {
                tool["name"] for tool in (*AGENT_TOOLS, *GESTION_AGENT_TOOLS)
            }
            command_agent = name == names[0]
            gestion_agent = name in {names[3], settings.foundry_voice_agent_name}
            existing_version = existing.versions.latest if existing else None
            existing_definition = (
                getattr(existing_version, "definition", None) if existing_version else None
            )
            existing_tools = getattr(existing_definition, "tools", None) or []
            replace_existing_search = command_agent and bool(
                settings.foundry_web_search_connection_id
            )
            if existing:
                preserved_tools = [
                    tool
                    for tool in existing_tools
                    if getattr(tool, "name", None) not in application_tool_names
                    and not (
                        replace_existing_search
                        and getattr(tool, "type", None) in WEB_SEARCH_TOOL_TYPES
                    )
                ]
            else:
                preserved_tools = []
            has_search_tool = any(
                getattr(tool, "type", None) in WEB_SEARCH_TOOL_TYPES
                for tool in preserved_tools
            )
            add_search_tool = command_agent and not has_search_tool
            if isinstance(existing_definition, VoiceAgentDefinition):
                tools = [
                    *preserved_tools,
                    *create_foundry_voice_tools(enable_inventory_email=gestion_agent),
                ]
                voice_definition = existing_definition.as_dict()
                voice_definition["instructions"] = instructions_for_role(instructions)
                voice_definition["tools"] = tools
                definition = VoiceAgentDefinition(**voice_definition)
            else:
                tools = create_foundry_tools(
                    settings.foundry_web_search_connection_id if add_search_tool else None,
                    settings.foundry_web_search_instance_name,
                    enable_web_search=add_search_tool,
                    enable_inventory_email=gestion_agent,
                )
                tools = [*preserved_tools, *tools]
                definition = PromptAgentDefinition(
                    model=settings.foundry_model_deployment,
                    instructions=instructions_for_role(instructions),
                    tools=tools,
                )

            created = project.agents.create_version(
                agent_name=name,
                definition=definition,
            )
            print(f"Created {created.name} (version {created.version}).")


if __name__ == "__main__":
    main()
