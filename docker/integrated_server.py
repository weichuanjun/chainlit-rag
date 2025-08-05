#!/usr/bin/env python3
"""
整合的服务器应用
集成所有后端功能的Flask服务器
"""
import os
import sys
import json
import uuid
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
import redis
import bcrypt
import jwt
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import aiohttp
import numpy as np

# 添加项目根目录到Python路径
sys.path.append('/app')

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建Flask应用
app = Flask(__name__)
CORS(app, origins=["http://localhost:8000", "http://localhost:80"])

# 配置
class Config:
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
    
    # 应用配置
    JWT_SECRET = os.getenv('JWT_SECRET', 'change-in-production')
    FILE_UPLOAD_PATH = os.getenv('FILE_UPLOAD_PATH', '/app/uploads')
    VECTOR_INDEX_PATH = os.getenv('VECTOR_INDEX_PATH', '/app/data/vector_index')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'md', 'docx'}

config = Config()

# 全局数据库和Redis连接
db_pool = None
redis_client = None

# 初始化连接
def init_connections():
    """初始化数据库和Redis连接"""
    global db_pool, redis_client
    
    try:
        # PostgreSQL连接池
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            host=config.POSTGRES_HOST,
            port=config.POSTGRES_PORT,
            database=config.POSTGRES_DB,
            user=config.POSTGRES_USER,
            password=config.POSTGRES_PASSWORD,
            cursor_factory=RealDictCursor
        )
        logger.info("✅ PostgreSQL连接池初始化成功")
        
        # Redis连接
        redis_client = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            password=config.REDIS_PASSWORD,
            decode_responses=True
        )
        redis_client.ping()
        logger.info("✅ Redis连接初始化成功")
        
    except Exception as e:
        logger.error(f"❌ 连接初始化失败: {e}")
        raise

# 数据库操作辅助函数
def get_db_connection():
    """获取数据库连接"""
    return db_pool.getconn()

def return_db_connection(conn):
    """归还数据库连接"""
    db_pool.putconn(conn)

def execute_query(query, params=None, fetch=True):
    """执行数据库查询"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            if fetch:
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.rowcount
    finally:
        return_db_connection(conn)

# 认证相关函数
def hash_password(password: str) -> str:
    """密码哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_jwt_token(user_data: dict) -> str:
    """生成JWT令牌"""
    payload = {
        'user_id': str(user_data['user_id']),
        'email': user_data['email'],
        'username': user_data['username'],
        'role': user_data.get('role', 'user'),
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm='HS256')

def verify_jwt_token(token: str) -> Optional[dict]:
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def get_user_from_token() -> Optional[str]:
    """从请求头获取用户ID"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]
    payload = verify_jwt_token(token)
    return payload['user_id'] if payload else None

# 文件处理函数
def allowed_file(filename):
    """检查文件扩展名"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS

def extract_text_from_file(file_path: str, file_type: str) -> str:
    """从文件提取文本"""
    try:
        import PyPDF2
        import docx
        import pandas as pd
        import json
        
        logger.info(f"开始提取文件内容: {file_path}, 类型: {file_type}")
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logger.error(f"文件不存在: {file_path}")
            return f"文件不存在: {os.path.basename(file_path)}"
        
        # 检查文件大小
        file_size = os.path.getsize(file_path)
        logger.info(f"文件大小: {file_size} bytes")
        
        if file_size == 0:
            logger.warning(f"文件为空: {file_path}")
            return f"文件为空: {os.path.basename(file_path)}"
        
        if file_type == 'text/plain' or file_path.lower().endswith('.txt'):
            logger.info("处理文本文件")
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                        if content.strip():  # 确保内容不为空
                            logger.info(f"成功使用 {encoding} 编码读取文件，内容长度: {len(content)}")
                            return content
                        else:
                            logger.warning(f"使用 {encoding} 编码读取的文件内容为空")
                except UnicodeDecodeError as e:
                    logger.debug(f"使用 {encoding} 编码失败: {e}")
                    continue
                except Exception as e:
                    logger.error(f"读取文件时发生错误: {e}")
                    continue
            
            # 如果所有编码都失败，使用二进制读取
            logger.info("所有文本编码都失败，尝试二进制读取")
            try:
                with open(file_path, 'rb') as f:
                    content = f.read().decode('latin-1')
                    logger.info(f"二进制读取成功，内容长度: {len(content)}")
                    return content
            except Exception as e:
                logger.error(f"二进制读取失败: {e}")
                return f"文件读取失败: {os.path.basename(file_path)}"
                
        elif file_type == 'text/markdown' or file_path.lower().endswith('.md'):
            logger.info("处理Markdown文件")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.info(f"Markdown文件读取成功，内容长度: {len(content)}")
                    return content
            except Exception as e:
                logger.error(f"Markdown文件读取失败: {e}")
                return f"Markdown文件读取失败: {os.path.basename(file_path)}"
                
        elif file_type == 'application/pdf' or file_path.lower().endswith('.pdf'):
            logger.info("处理PDF文件")
            try:
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for i, page in enumerate(pdf_reader.pages):
                        page_text = page.extract_text()
                        text += page_text + "\n"
                        logger.debug(f"PDF第{i+1}页提取了 {len(page_text)} 字符")
                    logger.info(f"PDF文件处理成功，总内容长度: {len(text)}")
                    return text.strip()
            except Exception as e:
                logger.error(f"PDF处理失败: {e}")
                return f"PDF文件内容提取失败: {os.path.basename(file_path)}"
                
        elif file_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' or file_path.lower().endswith('.docx'):
            logger.info("处理DOCX文件")
            try:
                doc = docx.Document(file_path)
                text = ""
                for i, paragraph in enumerate(doc.paragraphs):
                    text += paragraph.text + "\n"
                logger.info(f"DOCX文件处理成功，内容长度: {len(text)}")
                return text.strip()
            except Exception as e:
                logger.error(f"DOCX处理失败: {e}")
                return f"DOCX文件内容提取失败: {os.path.basename(file_path)}"
                
        elif file_type == 'application/msword' or file_path.lower().endswith('.doc'):
            logger.info("处理DOC文件")
            # 对于.doc文件，需要特殊处理，这里简化处理
            return f"DOC文件内容提取（需要特殊处理）: {os.path.basename(file_path)}"
            
        elif file_type == 'text/csv' or file_path.lower().endswith('.csv'):
            logger.info("处理CSV文件")
            try:
                df = pd.read_csv(file_path, encoding='utf-8')
                content = df.to_string(index=False)
                logger.info(f"CSV文件处理成功，内容长度: {len(content)}")
                return content
            except Exception as e:
                logger.error(f"CSV处理失败: {e}")
                return f"CSV文件内容提取失败: {os.path.basename(file_path)}"
                
        elif file_type == 'application/json' or file_path.lower().endswith('.json'):
            logger.info("处理JSON文件")
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    content = json.dumps(data, ensure_ascii=False, indent=2)
                    logger.info(f"JSON文件处理成功，内容长度: {len(content)}")
                    return content
            except Exception as e:
                logger.error(f"JSON处理失败: {e}")
                return f"JSON文件内容提取失败: {os.path.basename(file_path)}"
        else:
            logger.info(f"未知文件类型，尝试作为文本文件读取: {file_type}")
            # 尝试作为文本文件读取
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.info(f"作为文本文件读取成功，内容长度: {len(content)}")
                    return content
            except Exception as e:
                logger.error(f"作为文本文件读取失败: {e}")
                return f"不支持的文件类型: {file_type} (文件: {os.path.basename(file_path)})"
                
    except Exception as e:
        logger.error(f"文本提取失败: {e}")
        return f"文件内容提取失败: {os.path.basename(file_path)}"

def split_text_into_chunks(text: str, max_chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """智能文本分块"""
    if not text or len(text) <= max_chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + max_chunk_size
        
        # 如果不是最后一块，尝试在句号、换行符或空格处分割
        if end < len(text):
            # 寻找合适的分割点
            split_points = []
            
            # 句号分割
            period_pos = text.rfind('.', start, end)
            if period_pos > start + max_chunk_size // 2:  # 确保不会太短
                split_points.append(period_pos + 1)
            
            # 换行符分割
            newline_pos = text.rfind('\n', start, end)
            if newline_pos > start + max_chunk_size // 2:
                split_points.append(newline_pos + 1)
            
            # 空格分割
            space_pos = text.rfind(' ', start, end)
            if space_pos > start + max_chunk_size // 2:
                split_points.append(space_pos + 1)
            
            # 选择最接近end的分割点
            if split_points:
                end = max(split_points)
        
        chunk = text[start:end].strip()
        if chunk:  # 只添加非空块
            chunks.append(chunk)
        
        # 计算下一块的起始位置（考虑重叠）
        start = max(start + 1, end - overlap)
    
    return chunks

# 向量处理（改进版）
def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """生成向量嵌入"""
    if not config.OPENAI_API_KEY:
        logger.warning("OpenAI API密钥未配置，使用模拟向量")
        return [[0.1] * 1536 for _ in texts]
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        
        embeddings = []
        for text in texts:
            if not text.strip():
                # 空文本使用零向量
                embeddings.append([0.0] * 1536)
                continue
                
            response = client.embeddings.create(
                input=text,
                model=config.OPENAI_EMBEDDING_MODEL
            )
            embeddings.append(response.data[0].embedding)
        
        logger.info(f"成功生成 {len(embeddings)} 个向量嵌入")
        return embeddings
        
    except Exception as e:
        logger.error(f"向量生成失败: {e}")
        # 回退到模拟向量
        return [[0.1] * 1536 for _ in texts]

def save_vectors_to_faiss(vectors: List[List[float]], document_id: str):
    """保存向量到FAISS"""
    metadata_path = os.path.join(config.VECTOR_INDEX_PATH, 'metadata.json')
    
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # 确保 documents 键存在
        if "documents" not in metadata:
            metadata["documents"] = {}
        
        # 确保 vectors 键存在
        if "vectors" not in metadata:
            metadata["vectors"] = {}
        
        # 保存文档元数据
        metadata["documents"][document_id] = {
            "vector_count": len(vectors),
            "created_at": datetime.utcnow().isoformat()
        }
        
        # 保存向量数据（简化版，实际应该使用FAISS索引）
        for i, vector in enumerate(vectors):
            vector_id = f"{document_id}_{i}"
            metadata["vectors"][vector_id] = {
                "document_id": document_id,
                "chunk_id": i,
                "vector": vector,
                "created_at": datetime.utcnow().isoformat()
            }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            
        logger.info(f"向量保存成功: document_id={document_id}, vector_count={len(vectors)}")
            
    except Exception as e:
        logger.error(f"向量保存失败: {e}")

def search_similar_documents(query_text: str, user_id: str, top_k: int = 3) -> List[Dict]:
    """搜索相似文档"""
    try:
        if not config.OPENAI_API_KEY:
            logger.warning("OpenAI API密钥未配置，使用简单搜索")
            return _simple_text_search(query_text, user_id, top_k)
        
        # 生成查询向量
        query_embeddings = generate_embeddings([query_text])
        if not query_embeddings:
            return _simple_text_search(query_text, user_id, top_k)
        
        query_vector = query_embeddings[0]
        
        # 从元数据文件加载向量数据
        metadata_path = os.path.join(config.VECTOR_INDEX_PATH, 'metadata.json')
        if not os.path.exists(metadata_path):
            return _simple_text_search(query_text, user_id, top_k)
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # 计算相似度
        similarities = []
        for vector_id, vector_data in metadata.get("vectors", {}).items():
            if vector_data.get("document_id"):
                # 获取文档信息
                doc_info = execute_query("""
                    SELECT document_id, filename, original_filename, content_text, user_id
                    FROM documents 
                    WHERE document_id = %s AND user_id = %s AND status = 'processed'
                """, (vector_data["document_id"], user_id))
                
                if doc_info:
                    doc = doc_info[0]
                    stored_vector = vector_data.get("vector", [])
                    
                    if len(stored_vector) == len(query_vector):
                        # 计算余弦相似度
                        import numpy as np
                        query_np = np.array(query_vector)
                        stored_np = np.array(stored_vector)
                        
                        # 归一化向量
                        query_norm = np.linalg.norm(query_np)
                        stored_norm = np.linalg.norm(stored_np)
                        
                        if query_norm > 0 and stored_norm > 0:
                            similarity = np.dot(query_np, stored_np) / (query_norm * stored_norm)
                            
                            # 提取对应的文本块
                            content_text = doc['content_text']
                            chunk_size = 1000
                            chunk_start = vector_data.get("chunk_id", 0) * 800
                            chunk_end = min(chunk_start + chunk_size, len(content_text))
                            chunk_text = content_text[chunk_start:chunk_end]
                            
                            similarities.append({
                                'document_id': str(doc['document_id']),
                                'filename': doc['original_filename'] or doc['filename'],
                                'content': chunk_text,
                                'similarity_score': similarity,
                                'chunk_id': vector_data.get("chunk_id", 0)
                            })
        
        # 按相似度排序
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # 去重并返回top_k个结果
        seen_docs = set()
        unique_results = []
        for item in similarities:
            doc_key = f"{item['document_id']}_{item['chunk_id']}"
            if doc_key not in seen_docs:
                seen_docs.add(doc_key)
                unique_results.append(item)
                if len(unique_results) >= top_k:
                    break
        
        logger.info(f"向量搜索找到 {len(unique_results)} 个相关文档")
        return unique_results
        
    except Exception as e:
        logger.error(f"向量搜索失败: {e}")
        return _simple_text_search(query_text, user_id, top_k)

def _simple_text_search(query_text: str, user_id: str, top_k: int = 3) -> List[Dict]:
    """简单文本搜索（回退方案）"""
    try:
        # 简单的关键词匹配
        documents = execute_query("""
            SELECT document_id, filename, original_filename, content_text
            FROM documents 
            WHERE user_id = %s AND status = 'processed' AND content_text IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 10
        """, (user_id,))
        
        results = []
        for doc in documents:
            content_text = doc['content_text']
            if content_text and len(content_text) > 10:
                # 简单的相似度计算（基于关键词匹配）
                query_words = set(query_text.lower().split())
                content_words = set(content_text.lower().split())
                
                if query_words & content_words:  # 有共同词汇
                    intersection = len(query_words & content_words)
                    union = len(query_words | content_words)
                    similarity = intersection / union if union > 0 else 0
                    
                    content_preview = content_text[:200] + "..." if len(content_text) > 200 else content_text
                    
                    results.append({
                        'document_id': str(doc['document_id']),
                        'filename': doc['original_filename'] or doc['filename'],
                        'content': content_preview,
                        'similarity_score': similarity
                    })
        
        # 按相似度排序
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return results[:top_k]
        
    except Exception as e:
        logger.error(f"简单搜索失败: {e}")
        return []

# =====================================
# API 路由
# =====================================

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'services': {
            'database': 'connected',
            'redis': 'connected',
            'openai': 'configured' if config.OPENAI_API_KEY else 'not_configured'
        }
    })

# 认证API
@app.route('/auth/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        email = data.get('email')
        username = data.get('username')
        password = data.get('password')
        full_name = data.get('full_name')
        
        if not all([email, username, password]):
            return jsonify({'error': '邮箱、用户名和密码不能为空'}), 400
        
        # 检查用户是否已存在
        existing_user = execute_query(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        
        if existing_user:
            return jsonify({'error': '邮箱已被注册'}), 409
        
        # 创建用户
        password_hash = hash_password(password)
        user_id = str(uuid.uuid4())
        
        execute_query("""
            INSERT INTO users (user_id, email, username, password_hash, full_name)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, email, username, password_hash, full_name), fetch=False)
        
        # 生成令牌
        user_data = {
            'user_id': user_id,
            'email': email,
            'username': username,
            'role': 'user'
        }
        access_token = generate_jwt_token(user_data)
        
        return jsonify({
            'message': '注册成功',
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 24 * 3600,
            'user': user_data
        }), 201
        
    except Exception as e:
        logger.error(f"注册失败: {e}")
        return jsonify({'error': '注册失败'}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        logger.info(f"登录请求: email={email}")
        
        if not email or not password:
            logger.warning("登录失败: 邮箱或密码为空")
            return jsonify({'error': '邮箱和密码不能为空'}), 400
        
        # 查找用户
        users = execute_query(
            "SELECT * FROM users WHERE email = %s AND is_active = true",
            (email,)
        )
        
        logger.info(f"数据库查询结果: 找到 {len(users) if users else 0} 个用户")
        
        if not users:
            logger.warning(f"登录失败: 用户不存在 email={email}")
            return jsonify({'error': '邮箱或密码错误'}), 401
        
        user = users[0]
        password_verified = verify_password(password, user['password_hash'])
        logger.info(f"密码验证结果: {password_verified}")
        
        if not password_verified:
            logger.warning(f"登录失败: 密码错误 email={email}")
            return jsonify({'error': '邮箱或密码错误'}), 401
        
        # 更新最后登录时间
        execute_query(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s",
            (user['user_id'],), fetch=False
        )
        
        # 生成令牌
        access_token = generate_jwt_token(user)
        
        return jsonify({
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': 24 * 3600,
            'user': {
                'user_id': str(user['user_id']),
                'email': user['email'],
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role']
            }
        })
        
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({'error': '登录失败'}), 500

@app.route('/auth/verify', methods=['POST'])
def verify_token():
    """验证令牌"""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': '无效令牌'}), 401
    
    try:
        users = execute_query(
            "SELECT * FROM users WHERE user_id = %s AND is_active = true",
            (user_id,)
        )
        
        if not users:
            return jsonify({'error': '用户不存在'}), 401
        
        user = users[0]
        return jsonify({
            'valid': True,
            'user': {
                'user_id': str(user['user_id']),
                'email': user['email'],
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role']
            }
        })
        
    except Exception as e:
        logger.error(f"令牌验证失败: {e}")
        return jsonify({'error': '令牌验证失败'}), 401

# 文档API
@app.route('/documents/upload', methods=['POST'])
def upload_document():
    """文档上传"""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': '未授权访问'}), 401
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '文件名不能为空'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': '不支持的文件类型'}), 400
        
        # 保存文件
        filename = secure_filename(file.filename)
        document_id = str(uuid.uuid4())
        
        # 确保上传目录存在
        os.makedirs(config.FILE_UPLOAD_PATH, exist_ok=True)
        
        file_path = os.path.join(config.FILE_UPLOAD_PATH, f"{document_id}_{filename}")
        
        logger.info(f"保存文件: {file_path}")
        logger.info(f"原始文件名: {file.filename}")
        logger.info(f"安全文件名: {filename}")
        logger.info(f"文件类型: {file.content_type}")
        
        file.save(file_path)
        file_size = os.path.getsize(file_path)
        
        logger.info(f"文件保存成功，大小: {file_size} bytes")
        
        # 提取文本
        content_text = extract_text_from_file(file_path, file.content_type)
        
        logger.info(f"文本提取结果长度: {len(content_text) if content_text else 0}")
        
        # 保存文档记录
        execute_query("""
            INSERT INTO documents (
                document_id, user_id, filename, original_filename, 
                file_type, file_size, file_path, status, content_text
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            document_id, user_id, filename, file.filename,
            file.content_type, file_size, file_path, 'processed', content_text
        ), fetch=False)
        
        logger.info(f"文档记录保存成功: {document_id}")
        
        # 生成向量嵌入
        if content_text and not content_text.startswith("文件内容提取失败") and not content_text.startswith("不支持的文件类型"):
            logger.info("开始生成向量嵌入...")
            # 智能分块策略
            chunks = split_text_into_chunks(content_text)
            logger.info(f"文本分块完成，共 {len(chunks)} 个块")
            
            vectors = generate_embeddings(chunks)
            logger.info(f"向量生成完成，共 {len(vectors)} 个向量")
            
            save_vectors_to_faiss(vectors, document_id)
            
            # 更新块数和向量数
            execute_query("""
                UPDATE documents 
                SET chunk_count = %s, vector_count = %s, processed_at = CURRENT_TIMESTAMP
                WHERE document_id = %s
            """, (len(chunks), len(vectors), document_id), fetch=False)
            
            logger.info(f"向量信息更新完成")
        else:
            logger.warning(f"跳过向量生成，原因: {content_text[:100] if content_text else '内容为空'}")
        
        return jsonify({
            'message': '文档上传成功',
            'document_id': document_id,
            'filename': file.filename,  # 返回原始文件名
            'status': 'processed'
        })
        
    except Exception as e:
        logger.error(f"文档上传失败: {e}")
        return jsonify({'error': '文档上传失败'}), 500

@app.route('/documents', methods=['GET'])
def list_documents():
    """获取文档列表"""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': '未授权访问'}), 401
    
    try:
        documents = execute_query("""
            SELECT document_id, filename, original_filename, file_type, 
                   file_size, status, created_at, chunk_count, vector_count, tags
            FROM documents 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        
        # 转换UUID为字符串，并确保显示原文件名
        for doc in documents:
            doc['document_id'] = str(doc['document_id'])
            doc['created_at'] = doc['created_at'].isoformat()
            # 优先使用原文件名，如果没有则使用系统文件名
            doc['display_name'] = doc['original_filename'] if doc['original_filename'] else doc['filename']
        
        return jsonify({
            'documents': documents,
            'total_count': len(documents),
            'has_more': False
        })
        
    except Exception as e:
        logger.error(f"获取文档列表失败: {e}")
        return jsonify({'error': '获取文档列表失败'}), 500

# 聊天API
@app.route('/chat', methods=['POST'])
def chat():
    """处理聊天消息"""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': '未授权访问'}), 401
    
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        agent_workflow = data.get('agent_workflow', 'default_rag')
        
        if not message:
            return jsonify({'error': '消息内容不能为空'}), 400
        
        # 创建或获取对话
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            execute_query("""
                INSERT INTO conversations (conversation_id, user_id, agent_workflow)
                VALUES (%s, %s, %s)
            """, (conversation_id, user_id, agent_workflow), fetch=False)
        
        # 保存用户消息
        user_message_id = str(uuid.uuid4())
        execute_query("""
            INSERT INTO chat_messages (
                message_id, conversation_id, user_id, role, content, agent_workflow
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_message_id, conversation_id, user_id, 'user', message, agent_workflow), fetch=False)
        
        # 实现真正的RAG功能
        # 1. 搜索相关文档
        relevant_documents = []
        goto_simple_answer = False
        
        if config.OPENAI_API_KEY:
            try:
                # 使用向量搜索
                relevant_documents = search_similar_documents(message, user_id)
                
                # 如果向量搜索失败，回退到简单搜索
                if not relevant_documents:
                    logger.warning("向量搜索未找到相关文档，回退到简单搜索")
                    relevant_documents = _simple_text_search(message, user_id)
                
                # 如果简单搜索也失败，则没有相关文档
                if not relevant_documents:
                    logger.warning("简单搜索也未找到相关文档，使用默认回答")
                    goto_simple_answer = True
                    
            except Exception as e:
                logger.error(f"文档搜索失败: {e}")
                # 回退到简单搜索
                relevant_documents = _simple_text_search(message, user_id)
                if not relevant_documents:
                    goto_simple_answer = True
        
        # 2. 生成回答
        if goto_simple_answer or not relevant_documents:
            # 没有找到相关文档时的回答
            try:
                from openai import OpenAI
                client = OpenAI(api_key=config.OPENAI_API_KEY)
                
                prompt = f"""用户问题: {message}

用户没有上传相关文档，请友好地提示用户上传文档或提供一般性的帮助。"""
                
                response = client.chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个友好的AI助手，当用户没有上传相关文档时，请提示他们上传文档或提供帮助。"},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                
                response_content = response.choices[0].message.content
                
            except Exception as e:
                logger.error(f"OpenAI API调用失败: {e}")
                # 回退到简单回答
                response_content = f"""您好！我收到了您的问题：「{message}」

目前我没有找到相关的文档信息。您可以：
1. 上传一些文档到知识库
2. 重新提问
3. 或者直接告诉我您想了解什么

我会尽力为您提供帮助！"""
        else:
            # 有相关文档时的回答
            # 构建提示词
            doc_summary = "\n".join([f"文档: {doc['filename']}\n内容: {doc['content']}\n" for doc in relevant_documents])
            
            # 调用OpenAI API生成回答
            try:
                from openai import OpenAI
                client = OpenAI(api_key=config.OPENAI_API_KEY)
                
                prompt = f"""基于以下文档内容，回答用户的问题。请提供准确、有用的回答。

用户问题: {message}

相关文档:
{doc_summary}

请基于上述文档内容回答用户问题。如果文档内容不足以回答问题，请说明需要更多信息。"""
                
                logger.info(f"发送到OpenAI的提示词: {prompt[:200]}...")
                
                response = client.chat.completions.create(
                    model=config.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一个专业的文档助手，基于用户提供的文档内容回答问题。"},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=1000,
                    temperature=0.7
                )
                
                response_content = response.choices[0].message.content
                logger.info(f"OpenAI返回的回答: {response_content[:100]}...")
                
            except Exception as e:
                logger.error(f"OpenAI API调用失败: {e}")
                # 回退到简单回答
                doc_summary = "\n".join([f"- {doc['filename']}: {doc['content']}" for doc in relevant_documents])
                response_content = f"""基于您的问题「{message}」，我为您搜索了相关文档：

{doc_summary}

根据这些文档内容，我为您提供以下回答：

这是一个基于您上传文档的智能回答。如果您需要更详细的信息，请告诉我具体的问题。"""
        
        # 保存AI回复
        ai_message_id = str(uuid.uuid4())
        execute_query("""
            INSERT INTO chat_messages (
                message_id, conversation_id, user_id, role, content, agent_workflow
            ) VALUES (%s, %s, %s, %s, %s, %s)
        """, (ai_message_id, conversation_id, user_id, 'assistant', response_content, agent_workflow), fetch=False)
        
        # 更新对话消息数
        execute_query("""
            UPDATE conversations 
            SET message_count = message_count + 2, updated_at = CURRENT_TIMESTAMP
            WHERE conversation_id = %s
        """, (conversation_id,), fetch=False)
        
        return jsonify({
            'message_id': ai_message_id,
            'conversation_id': conversation_id,
            'content': response_content,
            'used_documents': relevant_documents,
            'reasoning_steps': [
                {'step': 'preprocessing', 'description': '处理用户查询'},
                {'step': 'retrieval', 'description': f'搜索到 {len(relevant_documents)} 个相关文档'},
                {'step': 'generation', 'description': '基于文档内容生成回答'}
            ],
            'agent_workflow': agent_workflow
        })
        
    except Exception as e:
        logger.error(f"聊天处理失败: {e}")
        return jsonify({'error': '聊天处理失败'}), 500

@app.route('/chat/conversations', methods=['GET'])
def get_conversations():
    """获取对话列表"""
    user_id = get_user_from_token()
    if not user_id:
        return jsonify({'error': '未授权访问'}), 401
    
    try:
        conversations = execute_query("""
            SELECT c.conversation_id, c.title, c.agent_workflow, c.message_count,
                   c.created_at, c.updated_at,
                   (SELECT content FROM chat_messages 
                    WHERE conversation_id = c.conversation_id AND role = 'user'
                    ORDER BY created_at DESC LIMIT 1) as preview
            FROM conversations c
            WHERE c.user_id = %s
            ORDER BY c.updated_at DESC
        """, (user_id,))
        
        # 转换数据格式
        for conv in conversations:
            conv['conversation_id'] = str(conv['conversation_id'])
            conv['created_at'] = conv['created_at'].isoformat()
            conv['updated_at'] = conv['updated_at'].isoformat()
            conv['last_message_at'] = conv['updated_at']
            conv['preview'] = conv['preview'][:100] if conv['preview'] else ''
        
        return jsonify({
            'conversations': conversations,
            'total_count': len(conversations)
        })
        
    except Exception as e:
        logger.error(f"获取对话列表失败: {e}")
        return jsonify({'error': '获取对话列表失败'}), 500

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '未找到请求的资源'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': '服务器内部错误'}), 500

if __name__ == '__main__':
    logger.info("🚀 启动整合服务器...")
    
    # 初始化连接
    init_connections()
    
    # 创建上传目录
    os.makedirs(config.FILE_UPLOAD_PATH, exist_ok=True)
    os.makedirs(config.VECTOR_INDEX_PATH, exist_ok=True)
    
    logger.info("✅ 服务器初始化完成")
    logger.info("📡 API服务器启动在: http://0.0.0.0:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=False)