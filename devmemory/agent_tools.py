"""
Universal agent memory tools - works with any AI coding agent
(Cursor, Claude, Copilot, Mistral, etc.)
"""

from typing import List, Dict, Any, Optional
from devmemory.core.ams_client import AMSClient
from devmemory.core.config import DevMemoryConfig


class AgentMemoryTools:
    """Universal memory interface for all AI coding agents"""
    
    def __init__(self, namespace: Optional[str] = None):
        """Initialize memory tools for a specific namespace/project"""
        config = DevMemoryConfig.load()
        self.client = AMSClient(base_url=config.ams_endpoint)
        self.namespace = namespace or config.get_active_namespace()
        
    def search_project_memory(
        self,
        query: str,
        limit: int = 5,
        topics: Optional[List[str]] = None,
        memory_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Universal search interface for all agents
        
        Args:
            query: Natural language search query
            limit: Maximum results to return
            topics: Filter by specific topics
            memory_types: Filter by memory types (semantic, episodic, etc.)
            
        Returns:
            List of memory results with text, score, topics, etc.
        """
        try:
            results = self.client.search_memories(
                text=query,
                limit=limit,
                namespace=self.namespace,
                topics=topics,
                memory_type=memory_types[0] if memory_types else None
            )
            
            # Convert to universal format
            return [{
                "text": r.text,
                "score": r.score,
                "topics": r.topics,
                "memory_type": r.memory_type,
                "source": "devmemory"
            } for r in results]
            
        except Exception as e:
            return [{"error": f"Memory search failed: {e}", "source": "devmemory"}]
    
    def get_hierarchical_context(self, task_description: str) -> Dict[str, Any]:
        """
        Get hierarchical context for any coding task
        Returns structured context at all levels
        """
        context = {
            "project": [],
            "architecture": [],
            "commits": [],
            "coordination": {}
        }
        
        try:
            # Level 1: Project Summaries
            context["project"] = self.search_project_memory(
                query=f"{task_description} project summary",
                topics=["project-summary"],
                limit=3
            )
            
            # Level 2: Architecture Summaries
            context["architecture"] = self.search_project_memory(
                query=f"{task_description} architecture patterns",
                topics=["architecture-summary"],
                limit=3
            )
            
            # Level 3: Commit-Level Details
            context["commits"] = self.search_project_memory(
                query=task_description,
                limit=5
            )
            
            # Level 4: Coordination Status
            try:
                sessions = self.client.list_sessions(namespace=self.namespace)
                context["coordination"]["active_sessions"] = sessions
            except:
                context["coordination"]["active_sessions"] = []
                
        except Exception as e:
            context["error"] = f"Context generation failed: {e}"
            
        return context
    
    def store_agent_learning(
        self,
        learning: str,
        learning_type: str = "semantic",
        topics: Optional[List[str]] = None,
        entities: Optional[List[str]] = None
    ) -> bool:
        """
        Universal method for agents to store what they've learned
        """
        try:
            memory = {
                "text": learning,
                "memory_type": learning_type,
                "topics": topics or [],
                "entities": entities or [],
                "namespace": self.namespace,
                "user_id": "agent"
            }
            
            result = self.client.create_memories([memory])
            return result.get("count", 0) > 0
            
        except Exception:
            return False
    
    def get_agent_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve reusable skills/methods from memory
        """
        try:
            skills = self.search_project_memory(
                query=f"reusable skill: {skill_name}",
                topics=["skills", "methods"],
                limit=1
            )
            
            return skills[0] if skills else None
            
        except Exception:
            return None
    
    def store_agent_skill(
        self,
        skill_name: str,
        skill_description: str,
        implementation: str,
        use_cases: List[str]
    ) -> bool:
        """
        Store reusable skills/methods for all agents
        """
        try:
            skill_memory = {
                "text": f"Skill: {skill_name}\n\n{skill_description}\n\nImplementation:\n{implementation}\n\nUse Cases:\n- " + "\n- ".join(use_cases),
                "memory_type": "semantic",
                "topics": ["skills", "methods", "reusable"],
                "entities": [skill_name.lower()],
                "namespace": self.namespace
            }
            
            result = self.client.create_memories([skill_memory])
            return result.get("count", 0) > 0
            
        except Exception:
            return False


def get_universal_agent_tools(namespace: Optional[str] = None) -> AgentMemoryTools:
    """
    Factory function to get memory tools for any agent
    """
    return AgentMemoryTools(namespace=namespace)


# Pre-configured tools for common agents
class ClaudeMemoryTools(AgentMemoryTools):
    """Memory tools optimized for Claude agents"""
    def __init__(self):
        super().__init__()
        # Claude-specific optimizations would go here


class CopilotMemoryTools(AgentMemoryTools):
    """Memory tools optimized for GitHub Copilot"""
    def __init__(self):
        super().__init__()
        # Copilot-specific optimizations would go here


class MistralMemoryTools(AgentMemoryTools):
    """Memory tools optimized for Mistral agents"""
    def __init__(self):
        super().__init__()
        # Mistral-specific optimizations would go here
