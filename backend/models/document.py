"""
文档数据模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel
import uuid

class Document(BaseModel):
    """文档模型"""
    document_id: str = None
    user_id: str
    filename: str
    original_filename: str
    file_type: str  # pdf, txt, docx, md
    file_size: int  # bytes
    s3_key: str
    s3_bucket: str
    status: Literal["uploading", "processing", "processed", "failed"] = "uploading"
    content_text: Optional[str] = None
    metadata: Dict[str, Any] = {}
    created_at: datetime = None
    updated_at: datetime = None
    processed_at: Optional[datetime] = None
    chunk_count: int = 0
    vector_count: int = 0
    tags: List[str] = []
    
    def __init__(self, **data):
        if not data.get('document_id'):
            data['document_id'] = str(uuid.uuid4())
        if not data.get('created_at'):
            data['created_at'] = datetime.utcnow()
        if not data.get('updated_at'):
            data['updated_at'] = datetime.utcnow()
        super().__init__(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "document_id": self.document_id,
            "user_id": self.user_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "s3_key": self.s3_key,
            "s3_bucket": self.s3_bucket,
            "status": self.status,
            "content_text": self.content_text,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "chunk_count": self.chunk_count,
            "vector_count": self.vector_count,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Document':
        """从字典创建文档对象"""
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if data.get('processed_at'):
            data['processed_at'] = datetime.fromisoformat(data['processed_at'])
        return cls(**data)

class DocumentChunk(BaseModel):
    """文档分块模型"""
    chunk_id: str = None
    document_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any] = {}
    token_count: int = 0
    embedding_vector: Optional[List[float]] = None
    created_at: datetime = None
    
    def __init__(self, **data):
        if not data.get('chunk_id'):
            data['chunk_id'] = str(uuid.uuid4())
        if not data.get('created_at'):
            data['created_at'] = datetime.utcnow()
        super().__init__(**data)

class DocumentUploadRequest(BaseModel):
    """文档上传请求"""
    filename: str
    file_type: str
    file_size: int
    tags: Optional[List[str]] = []

class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    document_id: str
    upload_url: str
    fields: Dict[str, str]

class DocumentSearchRequest(BaseModel):
    """文档搜索请求"""
    query: str
    user_id: Optional[str] = None
    document_ids: Optional[List[str]] = None
    file_types: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    limit: int = 10
    similarity_threshold: float = 0.7

class DocumentSearchResult(BaseModel):
    """文档搜索结果"""
    document_id: str
    filename: str
    chunk_content: str
    similarity_score: float
    metadata: Dict[str, Any] = {}
    
class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[Document]
    total_count: int
    has_more: bool