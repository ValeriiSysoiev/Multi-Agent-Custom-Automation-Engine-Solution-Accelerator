import datetime
from datetime import timezone
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from azure.ai.agents.models import (ResponseFormatJsonSchema,
                                    ResponseFormatJsonSchemaType)
from context.cosmos_memory_kernel import CosmosMemoryContext
from event_utils import track_event_if_configured
from kernel_agents.agent_base import BaseAgent
from kernel_tools.generic_tools import GenericTools
from kernel_tools.chat_tools import ChatTools
from kernel_tools.ingestion_tools import IngestionTools
from kernel_tools.dedup_tools import DeduplicationTools
from kernel_tools.enrichment_tools import EnrichmentTools
from kernel_tools.waiver_tools import WaiverTools
from kernel_tools.reporting_tools import ReportingTools
from kernel_tools.triage_tools import TriageTools
from kernel_tools.remediation_tools import RemediationTools
from kernel_tools.verification_tools import VerificationTools
from models.messages_kernel import (
    AgentMessage,
    AgentType,
    HumanFeedbackStatus,
    InputTask,
    Plan,
    PlannerResponsePlan,
    PlanStatus,
    Step,
    StepStatus,
)
from semantic_kernel.functions import KernelFunction
from semantic_kernel.functions.kernel_arguments import KernelArguments


class PlannerAgent(BaseAgent):
    """Planner agent implementation using Semantic Kernel.

    This agent creates and manages plans based on user tasks, breaking them down into steps
    that can be executed by specialized agents to achieve the user's goal.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        memory_store: CosmosMemoryContext,
        tools: Optional[List[KernelFunction]] = None,
        system_message: Optional[str] = None,
        agent_name: str = AgentType.PLANNER.value,
        available_agents: List[str] = None,
        agent_instances: Optional[Dict[str, BaseAgent]] = None,
        client=None,
        definition=None,
    ) -> None:
        """Initialize the Planner Agent.

        Args:
            session_id: The current session identifier
            user_id: The user identifier
            memory_store: The Cosmos memory context
            tools: Optional list of tools for this agent
            system_message: Optional system message for the agent
            agent_name: Optional name for the agent (defaults to "PlannerAgent")
            config_path: Optional path to the configuration file
            available_agents: List of available agent names for creating steps
            agent_tools_list: List of available tools across all agents
            agent_instances: Dictionary of agent instances available to the planner
            client: Optional client instance (passed to BaseAgent)
            definition: Optional definition instance (passed to BaseAgent)
        """
        # Default system message if not provided
        if not system_message:
            system_message = self.default_system_message(agent_name)

        # Initialize the base agent
        super().__init__(
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            memory_store=memory_store,
            tools=tools,
            system_message=system_message,
            client=client,
            definition=definition,
        )

        # Store additional planner-specific attributes
        self._available_agents = available_agents or [
            AgentType.HUMAN.value,
            AgentType.GENERIC.value,
            AgentType.INGESTION.value,
            AgentType.DEDUPLICATION.value,
            AgentType.ENRICHMENT.value,
            AgentType.TRIAGE.value,
            AgentType.REMEDIATION.value,
            AgentType.VERIFICATION.value,
            AgentType.WAIVER.value,
            AgentType.REPORTING.value,
            AgentType.CHAT.value,
        ]
        self._agent_tools_list = {
            AgentType.GENERIC: GenericTools.generate_tools_json_doc(),
            AgentType.INGESTION: IngestionTools.generate_tools_json_doc(),
            AgentType.DEDUPLICATION: DeduplicationTools.generate_tools_json_doc(),
            AgentType.ENRICHMENT: EnrichmentTools.generate_tools_json_doc(),
            AgentType.TRIAGE: TriageTools.generate_tools_json_doc(),
            AgentType.REMEDIATION: RemediationTools.generate_tools_json_doc(),
            AgentType.VERIFICATION: VerificationTools.generate_tools_json_doc(),
            AgentType.WAIVER: WaiverTools.generate_tools_json_doc(),
            AgentType.REPORTING: ReportingTools.generate_tools_json_doc(),
            AgentType.CHAT: ChatTools.generate_tools_json_doc(),
        }

        self._agent_instances = agent_instances or {}

    @staticmethod
    def default_system_message(agent_name=None) -> str:
        """Get the default system message for the agent.
        Args:
            agent_name: The name of the agent (optional)
        Returns:
            The default system message for the agent
        """
        return "You are a Planner agent responsible for creating and managing plans. You analyze tasks, break them down into steps, and assign them to the appropriate specialized agents."

    @classmethod
    async def create(
        cls,
        **kwargs: Dict[str, Any],
    ) -> None:
        """Asynchronously create the PlannerAgent.

        Creates the Azure AI Agent for planning operations.

        Returns:
            None
        """

        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        memory_store = kwargs.get("memory_store")
        tools = kwargs.get("tools", None)
        system_message = kwargs.get("system_message", None)
        agent_name = kwargs.get("agent_name")
        available_agents = kwargs.get("available_agents", None)
        agent_instances = kwargs.get("agent_instances", None)
        client = kwargs.get("client")

        # Create the instruction template

        try:
            logging.info("Initializing PlannerAgent from async init azure AI Agent")

            # Create the Azure AI Agent using AppConfig with string instructions
            agent_definition = await cls._create_azure_ai_agent_definition(
                agent_name=agent_name,
                instructions=cls._get_template(),  # Pass the formatted string, not an object
                temperature=0.0,
                response_format=ResponseFormatJsonSchemaType(
                    json_schema=ResponseFormatJsonSchema(
                        name=PlannerResponsePlan.__name__,
                        description=f"respond with {PlannerResponsePlan.__name__.lower()}",
                        schema=PlannerResponsePlan.model_json_schema(),
                    )
                ),
            )

            return cls(
                session_id=session_id,
                user_id=user_id,
                memory_store=memory_store,
                tools=tools,
                system_message=system_message,
                agent_name=agent_name,
                available_agents=available_agents,
                agent_instances=agent_instances,
                client=client,
                definition=agent_definition,
            )

        except Exception as e:
            logging.error(f"Failed to create Azure AI Agent for PlannerAgent: {e}")
            raise

    async def handle_input_task(self, input_task: InputTask) -> str:
        """Handle the initial input task from the user.

        Args:
            kernel_arguments: Contains the input_task_json string

        Returns:
            Status message
        """
        # Parse the input task
        logging.info("Handling input task")

        plan, steps = await self._create_structured_plan(input_task)

        logging.info(f"Plan created: {plan}")
        logging.info(f"Steps created: {steps}")

        if steps:
            # Add a message about the created plan
            await self._memory_store.add_item(
                AgentMessage(
                    session_id=input_task.session_id,
                    user_id=self._user_id,
                    plan_id=plan.id,
                    content=f"Generated a plan with {len(steps)} steps. Click the checkmark beside each step to complete it, click the x to reject this step.",
                    source=AgentType.PLANNER.value,
                    step_id="",
                )
            )

            track_event_if_configured(
                f"Planner - Generated a plan with {len(steps)} steps and added plan into the cosmos",
                {
                    "session_id": input_task.session_id,
                    "user_id": self._user_id,
                    "plan_id": plan.id,
                    "content": f"Generated a plan with {len(steps)} steps. Click the checkmark beside each step to complete it, click the x to reject this step.",
                    "source": AgentType.PLANNER.value,
                },
            )

            # If human clarification is needed, add a message requesting it
            if (
                hasattr(plan, "human_clarification_request")
                and plan.human_clarification_request
            ):
                await self._memory_store.add_item(
                    AgentMessage(
                        session_id=input_task.session_id,
                        user_id=self._user_id,
                        plan_id=plan.id,
                        content=f"I require additional information before we can proceed: {plan.human_clarification_request}",
                        source=AgentType.PLANNER.value,
                        step_id="",
                    )
                )

                track_event_if_configured(
                    "Planner - Additional information requested and added into the cosmos",
                    {
                        "session_id": input_task.session_id,
                        "user_id": self._user_id,
                        "plan_id": plan.id,
                        "content": f"I require additional information before we can proceed: {plan.human_clarification_request}",
                        "source": AgentType.PLANNER.value,
                    },
                )

        return f"Plan '{plan.id}' created successfully with {len(steps)} steps"

    async def handle_plan_clarification(self, kernel_arguments: KernelArguments) -> str:
        """Handle human clarification for a plan.

        Args:
            kernel_arguments: Contains session_id and human_clarification

        Returns:
            Status message
        """
        session_id = kernel_arguments["session_id"]
        human_clarification = kernel_arguments["human_clarification"]

        # Retrieve and update the plan
        plan = await self._memory_store.get_plan_by_session(session_id)
        if not plan:
            return f"No plan found for session {session_id}"

        plan.human_clarification_response = human_clarification
        await self._memory_store.update_plan(plan)

        # Add a record of the clarification
        await self._memory_store.add_item(
            AgentMessage(
                session_id=session_id,
                user_id=self._user_id,
                plan_id="",
                content=f"{human_clarification}",
                source=AgentType.HUMAN.value,
                step_id="",
            )
        )

        track_event_if_configured(
            "Planner - Store HumanAgent clarification and added into the cosmos",
            {
                "session_id": session_id,
                "user_id": self._user_id,
                "content": f"{human_clarification}",
                "source": AgentType.HUMAN.value,
            },
        )

        # Add a confirmation message
        await self._memory_store.add_item(
            AgentMessage(
                session_id=session_id,
                user_id=self._user_id,
                plan_id="",
                content="Thanks. The plan has been updated.",
                source=AgentType.PLANNER.value,
                step_id="",
            )
        )

        track_event_if_configured(
            "Planner - Updated with HumanClarification and added into the cosmos",
            {
                "session_id": session_id,
                "user_id": self._user_id,
                "content": "Thanks. The plan has been updated.",
                "source": AgentType.PLANNER.value,
            },
        )

        return "Plan updated with human clarification"

    async def _create_structured_plan(
        self, input_task: InputTask
    ) -> Tuple[Plan, List[Step]]:
        """Create a structured plan with steps based on the input task.

        Args:
            input_task: The input task from the user

        Returns:
            Tuple containing the created plan and list of steps
        """
        try:
            # Generate the instruction for the LLM

            # Get template variables as a dictionary
            args = self._generate_args(input_task.description)

            # Create kernel arguments - make sure we explicitly emphasize the task
            kernel_args = KernelArguments(**args)

            thread = None
            # thread = self.client.agents.create_thread(thread_id=input_task.session_id)
            async_generator = self.invoke(
                arguments=kernel_args,
                settings={
                    "temperature": 0.0,  # Keep temperature low for consistent planning
                    "max_tokens": 10096,  # Ensure we have enough tokens for the full plan
                },
                thread=thread,
            )

            # Call invoke with proper keyword arguments and JSON response schema
            response_content = ""

            # Collect the response from the async generator
            async for chunk in async_generator:
                if chunk is not None:
                    response_content += str(chunk)

            logging.info(f"Response content length: {len(response_content)}")

            # Check if response is empty or whitespace
            if not response_content or response_content.isspace():
                raise ValueError("Received empty response from Azure AI Agent")

            # Parse the JSON response directly to PlannerResponsePlan
            parsed_result = None

            # Try various parsing approaches in sequence
            try:
                # 1. First attempt: Try to parse the raw response directly
                parsed_result = PlannerResponsePlan.parse_raw(response_content)
                if parsed_result is None:
                    # If all parsing attempts fail, create a fallback plan from the text content
                    logging.info(
                        "All parsing attempts failed, creating fallback plan from text content"
                    )
                    raise ValueError("Failed to parse JSON response")

            except Exception as parsing_exception:
                logging.exception(f"Error during parsing attempts: {parsing_exception}")
                raise ValueError("Failed to parse JSON response")

            # At this point, we have a valid parsed_result

            # Extract plan details
            initial_goal = parsed_result.initial_goal
            steps_data = parsed_result.steps
            summary = parsed_result.summary_plan_and_steps
            human_clarification_request = parsed_result.human_clarification_request

            # Create the Plan instance
            plan = Plan(
                id=str(uuid.uuid4()),
                session_id=input_task.session_id,
                user_id=self._user_id,
                initial_goal=initial_goal,
                overall_status=PlanStatus.in_progress,
                summary=summary,
                human_clarification_request=human_clarification_request,
            )

            # Store the plan
            await self._memory_store.add_plan(plan)

            # Create steps from the parsed data
            steps = []
            user_scope = None
            if getattr(input_task, "metadata", None):
                user_scope = input_task.metadata.get("user_scope")

            for step_data in steps_data:
                action = step_data.action
                agent_name = step_data.agent

                # Validate agent name
                if agent_name not in self._available_agents:
                    logging.warning(
                        f"Invalid agent name: {agent_name}, defaulting to {AgentType.GENERIC.value}"
                    )
                    agent_name = AgentType.GENERIC.value

                # Create the step
                step = Step(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    session_id=input_task.session_id,
                    user_id=self._user_id,
                    action=action,
                    agent=agent_name,
                    status=StepStatus.planned,
                    human_approval_status=HumanFeedbackStatus.requested,
                    metadata=user_scope,
                )

                # Store the step
                await self._memory_store.add_step(step)
                steps.append(step)

                try:
                    track_event_if_configured(
                        "Planner - Added planned individual step into the cosmos",
                        {
                            "plan_id": plan.id,
                            "action": action,
                            "agent": agent_name,
                            "status": StepStatus.planned,
                            "session_id": input_task.session_id,
                            "user_id": self._user_id,
                            "human_approval_status": HumanFeedbackStatus.requested,
                        },
                    )
                except Exception as event_error:
                    # Don't let event tracking errors break the main flow
                    logging.warning(f"Error in event tracking: {event_error}")

            return plan, steps

        except Exception as e:
            error_message = str(e)
            if "Rate limit is exceeded" in error_message:
                logging.warning("Rate limit hit. Consider retrying after some delay.")
                raise
            else:
                logging.exception(f"Error creating structured plan: {e}")

            # Create a fallback dummy plan when parsing fails
            logging.info("Creating fallback dummy plan due to parsing error")

            # Create a dummy plan with the original task description
            dummy_plan = Plan(
                id=str(uuid.uuid4()),
                session_id=input_task.session_id,
                user_id=self._user_id,
                initial_goal=input_task.description,
                overall_status=PlanStatus.in_progress,
                summary=f"Plan created for: {input_task.description}",
                human_clarification_request=None,
                timestamp=datetime.datetime.now(timezone.utc).isoformat(),
            )

            # Store the dummy plan
            await self._memory_store.add_plan(dummy_plan)

            # Create a dummy step for analyzing the task
            dummy_step = Step(
                id=str(uuid.uuid4()),
                plan_id=dummy_plan.id,
                session_id=input_task.session_id,
                user_id=self._user_id,
                action="Analyze the task: " + input_task.description,
                agent=AgentType.GENERIC.value,  # Using the correct value from AgentType enum
                status=StepStatus.planned,
                human_approval_status=HumanFeedbackStatus.requested,
                timestamp=datetime.datetime.now(timezone.utc).isoformat(),
                metadata=(getattr(input_task, "metadata", {}) or {}).get("user_scope"),
            )

            # Store the dummy step
            await self._memory_store.add_step(dummy_step)

            # Add a second step to request human clarification
            clarification_step = Step(
                id=str(uuid.uuid4()),
                plan_id=dummy_plan.id,
                session_id=input_task.session_id,
                user_id=self._user_id,
                action=f"Provide more details about: {input_task.description}",
                agent=AgentType.HUMAN.value,
                status=StepStatus.planned,
                human_approval_status=HumanFeedbackStatus.requested,
                timestamp=datetime.datetime.now(timezone.utc).isoformat(),
                metadata=(getattr(input_task, "metadata", {}) or {}).get("user_scope"),
            )

            # Store the clarification step
            await self._memory_store.add_step(clarification_step)

            # Log the event
            try:
                track_event_if_configured(
                    "Planner - Created fallback dummy plan due to parsing error",
                    {
                        "session_id": input_task.session_id,
                        "user_id": self._user_id,
                        "error": str(e),
                        "description": input_task.description,
                        "source": AgentType.PLANNER.value,
                    },
                )
            except Exception as event_error:
                logging.warning(
                    f"Error in event tracking during fallback: {event_error}"
                )

            return dummy_plan, [dummy_step, clarification_step]

    def _generate_args(self, objective: str) -> any:
        """Generate instruction for the LLM to create a plan.

        Args:
            objective: The user's objective

        Returns:
            Dictionary containing the variables to populate the template
        """
        # Create a list of available agents
        agents_str = ", ".join(self._available_agents)

        # Create list of available tools in JSON-like format
        tools_list = []

        for agent_name, tools in self._agent_tools_list.items():
            if agent_name in self._available_agents:
                tools_list.append(tools)

        tools_str = tools_list

        # Return a dictionary with template variables
        return {
            "objective": objective,
            "agents_str": agents_str,
            "tools_str": tools_str,
        }

    @staticmethod
    def _get_template():
        """Generate the instruction template for the LLM."""
        # Build the instruction with proper format placeholders for .format() method

        instruction_template = """
            You are the Planner for the AI Vulnerability Management platform. Coordinate the specialised agents so vulnerabilities move from ingestion through remediation, verification, waivers, and reporting.

            Your objective is:
            {{$objective}}

            Available agents:
            {{$agents_str}}

            Agent responsibilities:
            - Ingestion_Agent gathers scanner results (Defender for Cloud, Qualys) and normalises them.
            - Deduplication_Agent reconciles duplicate findings across scanners and time windows.
            - Enrichment_Agent attaches asset ownership, business context, and threat intelligence.
            - Triage_Agent produces risk scores and recommended treatments.
            - Remediation_Agent creates actionable tickets grouped by remediation unit.
            - Verification_Agent validates evidence, reruns scans, and reopens gaps when necessary.
            - Waiver_Agent manages exception requests, expiries, and escalations.
            - Reporting_Agent publishes dataset exports and refreshes dashboards.
            - Chat_Agent summarises status for stakeholders. Use Generic_Agent for minor reasoning and Human_Agent when manual action is unavoidable.

            Functions available to each agent:
            {{$tools_str}}

            Planning rules:
            1. First step: confirm missing prerequisites from the requestor so downstream agents have required data.
            2. Prefer the pipeline order (ingest → deduplicate → enrich → triage → remediation → verification → waiver/reporting) unless the task clearly targets a subset.
            3. Each action must specify the agent and function to call (e.g., "Run ingestion cycle. Function: run_ingestion_cycle").
            4. If information is missing, populate human_clarification_request with a concise question.
            5. Use Generic_Agent only when a general LLM can complete the task; otherwise route to Human_Agent.
            6. Keep plans to six steps or fewer and avoid redundant work.
            7. Summaries must be fewer than 50 words.

            Return the plan using the provided JSON schema.
            """
        return instruction_template
