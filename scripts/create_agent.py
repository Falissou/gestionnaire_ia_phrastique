"""Create the four pharmacy stock-management agents in Microsoft Foundry."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pharmacy_platform.config import AGENT_ROLES, Settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--agent",
        default="all",
        help="Create all agents, or one configured Foundry agent by name.",
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
    else:
        try:
            selected = [(args.agent, AGENT_ROLES[list(AGENT_ROLES)[names.index(args.agent)]])]
        except ValueError:
            parser.error(f"Unknown agent {args.agent!r}. Configured agents: {', '.join(names)}")

    try:
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import PromptAgentDefinition
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

            if existing:
                print(f"{name} already exists (version {existing.version}); left unchanged.")
                continue

            created = project.agents.create_version(
                agent_name=name,
                definition=PromptAgentDefinition(
                    model=settings.foundry_model_deployment,
                    instructions=instructions,
                ),
            )
            print(f"Created {created.name} (version {created.version}).")


if __name__ == "__main__":
    main()
