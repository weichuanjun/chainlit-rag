"""
Docker环境配置
"""
import os

class DockerConfig:
    # 应用模式
    APP_MODE = "docker"
    
    # 数据库配置
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'postgres')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', 5432))
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'chainlit_rag')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'rag_user')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'rag_password')
    
    # Redis配置
    REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', 'redis_password')
    
    # OpenAI配置
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
    OPENAI_EMBEDDING_MODEL = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-ada-002')
    
    # API配置 - 在Docker容器内部，API服务器运行在localhost:5000
    API_GATEWAY_URL = os.getenv('API_BASE_URL', 'http://localhost:5000')
    
    # 应用配置
    JWT_SECRET = os.getenv('JWT_SECRET', 'docker-jwt-secret-change-in-production')
    APP_NAME = 'chainlit-rag-docker'
    
    # 向量数据库配置
    VECTOR_DB_TYPE = 'faiss'
    
    # 路径配置
    FILE_UPLOAD_PATH = os.getenv('FILE_UPLOAD_PATH', '/app/uploads')
    VECTOR_INDEX_PATH = os.getenv('VECTOR_INDEX_PATH', '/app/data/vector_index')
    
    # AWS配置（Docker模式下不使用）
    AWS_REGION = 'us-east-1'
    AWS_ACCESS_KEY_ID = 'docker-mode'
    AWS_SECRET_ACCESS_KEY = 'docker-mode'
    
    # 表名（PostgreSQL）
    DYNAMODB_USERS_TABLE = 'users'
    DYNAMODB_CHAT_HISTORY_TABLE = 'chat_messages'
    DYNAMODB_DOCUMENTS_TABLE = 'documents'
    
    # S3配置（Docker模式下使用本地存储）
    S3_BUCKET_NAME = 'local-storage'
    
    # Agent配置
    AGENT_CONFIG_PATH = '/app/configs/agent_config.yaml'
    
    # 调试设置
    DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# 单例配置实例
docker_config = DockerConfig()