"""
聊天数据模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel
import uuid

class ChatMessage(BaseModel):
    """聊天消息模型"""
    message_id: str = None
    conversation_id: str
    user_id: str
    role: Literal["user", "assistant", "system"] = "user"
    content: str
    metadata: Dict[str, Any] = {}
    created_at: datetime = None
    
    # Agent相关字段
    agent_workflow: Optional[str] = None
    used_documents: List[str] = []  # 使用的文档ID列表
    reasoning_steps: List[Dict[str, Any]] = []  # Agent推理步骤
    
    def __init__(self, **data):
        if not data.get('message_id'):
            data['message_id'] = str(uuid.uuid4())
        if not data.get('created_at'):
            data['created_at'] = datetime.utcnow()
        super().__init__(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "agent_workflow": self.agent_workflow,
            "used_documents": self.used_documents,
            "reasoning_steps": self.reasoning_steps
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChatMessage':
        """从字典创建消息对象"""
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)

class Conversation(BaseModel):
    """对话会话模型"""
    conversation_id: str = None
    user_id: str
    title: str = "新对话"
    agent_workflow: str = "default_rag"
    created_at: datetime = None
    updated_at: datetime = None
    message_count: int = 0
    is_archived: bool = False
    metadata: Dict[str, Any] = {}
    
    def __init__(self, **data):
        if not data.get('conversation_id'):
            data['conversation_id'] = str(uuid.uuid4())
        if not data.get('created_at'):
            data['created_at'] = datetime.utcnow()
        if not data.get('updated_at'):
            data['updated_at'] = datetime.utcnow()
        super().__init__(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "title": self.title,
            "agent_workflow": self.agent_workflow,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.message_count,
            "is_archived": self.is_archived,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Conversation':
        """从字典创建会话对象"""
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        return cls(**data)

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    conversation_id: Optional[str] = None
    agent_workflow: str = "default_rag"
    context_documents: Optional[List[str]] = None  # 指定使用的文档ID

class ChatResponse(BaseModel):
    """聊天响应"""
    message_id: str
    conversation_id: str
    content: str
    used_documents: List[Dict[str, Any]] = []
    reasoning_steps: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}

class ConversationSummary(BaseModel):
    """对话摘要"""
    conversation_id: str
    title: str
    agent_workflow: str
    message_count: int
    last_message_at: datetime
    preview: str  # 最后几条消息的预览

class ChatHistoryRequest(BaseModel):
    """聊天历史请求"""
    conversation_id: str
    limit: int = 50
    offset: int = 0

class ConversationListRequest(BaseModel):
    """对话列表请求"""
    limit: int = 20
    offset: int = 0
    include_archived: bool = False