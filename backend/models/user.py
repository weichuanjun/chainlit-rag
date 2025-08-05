"""
用户数据模型
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr
import uuid

class User(BaseModel):
    """用户模型"""
    user_id: str = None
    email: EmailStr
    username: str
    password_hash: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    last_login: Optional[datetime] = None
    is_active: bool = True
    role: str = "user"  # user, admin
    preferences: Dict[str, Any] = {}
    
    def __init__(self, **data):
        if not data.get('user_id'):
            data['user_id'] = str(uuid.uuid4())
        if not data.get('created_at'):
            data['created_at'] = datetime.utcnow()
        if not data.get('updated_at'):
            data['updated_at'] = datetime.utcnow()
        super().__init__(**data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，用于DynamoDB存储"""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "username": self.username,
            "password_hash": self.password_hash,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "is_active": self.is_active,
            "role": self.role,
            "preferences": self.preferences
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """从字典创建用户对象"""
        if data.get('created_at'):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if data.get('last_login'):
            data['last_login'] = datetime.fromisoformat(data['last_login'])
        return cls(**data)

class UserLogin(BaseModel):
    """用户登录请求"""
    email: EmailStr
    password: str

class UserRegister(BaseModel):
    """用户注册请求"""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None

class UserProfile(BaseModel):
    """用户公开资料"""
    user_id: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    role: str

class UserUpdate(BaseModel):
    """用户信息更新"""
    username: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None