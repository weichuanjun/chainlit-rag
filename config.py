"""
应用配置文件
"""
import os
from typing import Dict, Any

class Config:
    # OpenAI配置
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-ada-002")
    
    # AWS配置
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    
    # 应用配置
    JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
    APP_NAME = os.getenv("APP_NAME", "chainlit-rag-kb")
    
    # DynamoDB表名
    DYNAMODB_USERS_TABLE = os.getenv("DYNAMODB_USERS_TABLE", "rag-users")
    DYNAMODB_CHAT_HISTORY_TABLE = os.getenv("DYNAMODB_CHAT_HISTORY_TABLE", "rag-chat-history")
    DYNAMODB_DOCUMENTS_TABLE = os.getenv("DYNAMODB_DOCUMENTS_TABLE", "rag-documents")
    
    # S3配置
    S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "rag-documents-bucket")
    
    # 向量数据库配置
    VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "faiss")  # faiss, pinecone, opensearch
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
    PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "")
    PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "rag-knowledge-base")
    
    # API Gateway
    API_GATEWAY_URL = os.getenv("API_GATEWAY_URL", "")
    
    # Agent配置路径
    AGENT_CONFIG_PATH = os.getenv("AGENT_CONFIG_PATH", "configs/agent_config.yaml")

# 单例配置实例
config = Config()