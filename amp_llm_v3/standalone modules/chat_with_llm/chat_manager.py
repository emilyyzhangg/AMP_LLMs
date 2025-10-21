"""
Conversation Manager
====================

Manages conversation histories and persistence.
"""
import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from chat_config import config

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversation histories and state"""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize conversation manager.
        
        Args:
            storage_dir: Directory for storing conversations (overrides config)
        """
        self.storage_dir = storage_dir or config.CONVERSATION_DIR
        self.storage_dir.mkdir(exist_ok=True)
        
        self.conversations: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Conversation manager initialized (storage: {self.storage_dir})")
    
    def create_conversation(
        self,
        model: str,
        conversation_id: Optional[str] = None
    ) -> str:
        """
        Create a new conversation or resume existing.
        
        Args:
            model: Model name to use
            conversation_id: Optional existing conversation to resume
            
        Returns:
            Conversation ID
        """
        if conversation_id and conversation_id in self.conversations:
            logger.info(f"Resuming conversation: {conversation_id}")
            return conversation_id
        
        conv_id = conversation_id or str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        self.conversations[conv_id] = {
            "model": model,
            "created_at": now,
            "updated_at": now,
            "messages": []
        }
        
        logger.info(f"Created conversation: {conv_id} with model: {model}")
        return conv_id
    
    def add_message(self, conversation_id: str, role: str, content: str):
        """
        Add a message to conversation.
        
        Args:
            conversation_id: Conversation ID
            role: 'user' or 'assistant'
            content: Message content
            
        Raises:
            ValueError: If conversation not found
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.conversations[conversation_id]["messages"].append(message)
        self.conversations[conversation_id]["updated_at"] = message["timestamp"]
        
        logger.debug(f"Added {role} message to {conversation_id} ({len(content)} chars)")
    
    def get_messages(self, conversation_id: str) -> List[Dict[str, str]]:
        """
        Get all messages in conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            List of messages
            
        Raises:
            ValueError: If conversation not found
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return self.conversations[conversation_id]["messages"]
    
    def get_model(self, conversation_id: str) -> str:
        """
        Get model for conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Model name
            
        Raises:
            ValueError: If conversation not found
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return self.conversations[conversation_id]["model"]
    
    def list_conversations(self) -> List[Dict[str, Any]]:
        """
        List all conversations.
        
        Returns:
            List of conversation metadata
        """
        result = []
        for conv_id, conv_data in self.conversations.items():
            result.append({
                "conversation_id": conv_id,
                "model": conv_data["model"],
                "created_at": conv_data["created_at"],
                "updated_at": conv_data["updated_at"],
                "message_count": len(conv_data["messages"])
            })
        
        logger.debug(f"Listed {len(result)} conversations")
        return result
    
    def get_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get full conversation data.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Complete conversation data
            
        Raises:
            ValueError: If conversation not found
        """
        if conversation_id not in self.conversations:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        return {
            "conversation_id": conversation_id,
            **self.conversations[conversation_id]
        }
    
    def delete_conversation(self, conversation_id: str):
        """
        Delete a conversation.
        
        Args:
            conversation_id: Conversation ID
        """
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
            
            # Also delete saved file if exists
            file_path = self.storage_dir / f"{conversation_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted conversation file: {file_path}")
            
            logger.info(f"Deleted conversation: {conversation_id}")
    
    def save_conversation(self, conversation_id: str):
        """
        Save conversation to disk.
        
        Args:
            conversation_id: Conversation ID
        """
        if conversation_id not in self.conversations:
            logger.warning(f"Cannot save non-existent conversation: {conversation_id}")
            return
        
        file_path = self.storage_dir / f"{conversation_id}.json"
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(
                    self.get_conversation(conversation_id),
                    f,
                    indent=2,
                    ensure_ascii=False
                )
            logger.info(f"Saved conversation to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save conversation: {e}")
    
    def load_conversation(self, conversation_id: str) -> bool:
        """
        Load conversation from disk.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            True if loaded successfully
        """
        file_path = self.storage_dir / f"{conversation_id}.json"
        
        if not file_path.exists():
            logger.warning(f"Conversation file not found: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Remove conversation_id from data before storing
            conv_id = data.pop("conversation_id", conversation_id)
            self.conversations[conv_id] = data
            
            logger.info(f"Loaded conversation from {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load conversation: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get conversation statistics.
        
        Returns:
            Statistics dictionary
        """
        total_messages = sum(
            len(conv["messages"]) 
            for conv in self.conversations.values()
        )
        
        models_used = set(
            conv["model"] 
            for conv in self.conversations.values()
        )
        
        return {
            "total_conversations": len(self.conversations),
            "total_messages": total_messages,
            "models_used": list(models_used),
            "active_conversations": len(self.conversations)
        }