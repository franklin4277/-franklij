"""Service layer for the Gateway API."""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from mini_agent.agent import Agent
from mini_agent.cli import initialize_base_tools, add_workspace_tools
from mini_agent.config import Config
from mini_agent.llm import LLMClient
from mini_agent.schema import LLMProvider
from mini_agent.retry import RetryConfig as RetryConfigBase

class SessionManager:
    """Manages agent sessions."""

    def __init__(self):
        self._sessions: Dict[str, Agent] = {}
        self._session_info: Dict[str, Dict] = {}

    async def create_session(self, workspace_dir: Optional[str] = None, system_prompt: Optional[str] = None) -> Dict:
        """Create a new agent session."""
        session_id = str(uuid.uuid4())
        
        # Load configuration
        config_path = Config.get_default_config_path()
        if not config_path.exists():
            raise FileNotFoundError("Configuration file not found. Please configure Mini-Agent first.")
        
        config = Config.from_yaml(config_path)
        
        # Determine workspace
        if workspace_dir:
            ws_path = Path(workspace_dir).expanduser().absolute()
        else:
            # Use default workspace or create a unique one per session?
            # For now, let's use a subdirectory in default workspace to avoid conflicts if needed
            # Or just use the default workspace from config
            ws_path = Path(config.agent.workspace_dir).expanduser().absolute()
            
        ws_path.mkdir(parents=True, exist_ok=True)

        # Initialize LLM client
        retry_config = RetryConfigBase(
            enabled=config.llm.retry.enabled,
            max_retries=config.llm.retry.max_retries,
            initial_delay=config.llm.retry.initial_delay,
            max_delay=config.llm.retry.max_delay,
            exponential_base=config.llm.retry.exponential_base,
            retryable_exceptions=(Exception,),
        )

        provider = LLMProvider.ANTHROPIC if config.llm.provider.lower() == "anthropic" else LLMProvider.OPENAI

        llm_client = LLMClient(
            api_key=config.llm.api_key,
            provider=provider,
            api_base=config.llm.api_base,
            model=config.llm.model,
            retry_config=retry_config if config.llm.retry.enabled else None,
        )

        # Initialize tools
        tools, skill_loader = await initialize_base_tools(config)
        add_workspace_tools(tools, config, ws_path)

        # Determine system prompt
        if system_prompt:
            prompt_text = system_prompt
        else:
            system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
            if system_prompt_path and system_prompt_path.exists():
                prompt_text = system_prompt_path.read_text(encoding="utf-8")
            else:
                prompt_text = "You are Mini-Agent, an intelligent assistant powered by MiniMax M2.5."

        # Inject Skills Metadata
        if skill_loader:
            skills_metadata = skill_loader.get_skills_metadata_prompt()
            if skills_metadata:
                prompt_text = prompt_text.replace("{SKILLS_METADATA}", skills_metadata)
            else:
                prompt_text = prompt_text.replace("{SKILLS_METADATA}", "")
        else:
            prompt_text = prompt_text.replace("{SKILLS_METADATA}", "")

        # Create Agent
        agent = Agent(
            llm_client=llm_client,
            system_prompt=prompt_text,
            tools=tools,
            max_steps=config.agent.max_steps,
            workspace_dir=str(ws_path),
        )

        self._sessions[session_id] = agent
        
        info = {
            "session_id": session_id,
            "workspace_dir": str(ws_path),
            "created_at": datetime.now().isoformat(),
        }
        self._session_info[session_id] = info
        
        return info

    def get_agent(self, session_id: str) -> Optional[Agent]:
        """Get agent instance by session ID."""
        return self._sessions.get(session_id)

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get session information."""
        return self._session_info.get(session_id)

    def close_session(self, session_id: str) -> bool:
        """Close a session and cleanup."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            del self._session_info[session_id]
            return True
        return False

# Singleton instance
session_manager = SessionManager()
