#!/usr/bin/env python3
"""
数据库初始化脚本
确保数据库连接正常并执行必要的初始化操作
"""
import os
import sys
import time
import psycopg2
from psycopg2 import sql
import logging

# 添加项目根目录到Python路径
sys.path.append('/app')

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_config():
    """获取数据库配置"""
    return {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'chainlit_rag'),
        'user': os.getenv('POSTGRES_USER', 'rag_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'rag_password'),
    }

def wait_for_database(max_retries=30, retry_interval=2):
    """等待数据库就绪"""
    db_config = get_db_config()
    
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(**db_config)
            conn.close()
            logger.info("✅ 数据库连接成功")
            return True
        except psycopg2.OperationalError as e:
            if attempt < max_retries - 1:
                logger.info(f"⏳ 等待数据库就绪... (尝试 {attempt + 1}/{max_retries})")
                time.sleep(retry_interval)
            else:
                logger.error(f"❌ 数据库连接失败: {e}")
                return False
    return False

def execute_sql_file(filepath):
    """执行SQL文件"""
    db_config = get_db_config()
    
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                with open(filepath, 'r', encoding='utf-8') as f:
                    sql_content = f.read()
                
                # 执行SQL
                cursor.execute(sql_content)
                conn.commit()
                logger.info(f"✅ 成功执行SQL文件: {filepath}")
                return True
                
    except Exception as e:
        logger.error(f"❌ 执行SQL文件失败: {e}")
        return False

def check_tables():
    """检查表是否创建成功"""
    db_config = get_db_config()
    
    expected_tables = [
        'users', 'documents', 'conversations', 
        'chat_messages', 'document_chunks'
    ]
    
    try:
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                """)
                
                existing_tables = [row[0] for row in cursor.fetchall()]
                
                missing_tables = set(expected_tables) - set(existing_tables)
                
                if missing_tables:
                    logger.warning(f"⚠️  缺少表: {missing_tables}")
                    return False
                else:
                    logger.info("✅ 所有必需的表都已创建")
                    return True
                    
    except Exception as e:
        logger.error(f"❌ 检查表时出错: {e}")
        return False

def create_directories():
    """创建必要的目录"""
    directories = [
        '/app/data',
        '/app/uploads',
        '/app/logs',
        '/app/data/vector_index'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"📁 创建目录: {directory}")

def initialize_vector_storage():
    """初始化向量存储"""
    try:
        vector_index_path = '/app/data/vector_index'
        metadata_path = os.path.join(vector_index_path, 'metadata.json')
        
        # 创建元数据文件
        if not os.path.exists(metadata_path):
            import json
            initial_metadata = {
                "created_at": time.time(),
                "version": "1.0",
                "document_count": 0,
                "vector_count": 0
            }
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(initial_metadata, f, indent=2)
            
            logger.info("✅ 向量存储元数据初始化完成")
        
    except Exception as e:
        logger.error(f"❌ 向量存储初始化失败: {e}")

def main():
    """主初始化函数"""
    logger.info("🚀 开始数据库初始化...")
    
    # 1. 等待数据库就绪
    if not wait_for_database():
        logger.error("❌ 数据库初始化失败：无法连接到数据库")
        sys.exit(1)
    
    # 2. 创建必要目录
    create_directories()
    
    # 3. 检查表是否已存在
    if check_tables():
        logger.info("✅ 数据库表已存在，跳过初始化")
    else:
        # 4. 执行初始化SQL
        sql_file = '/app/docker/init.sql'
        if os.path.exists(sql_file):
            if not execute_sql_file(sql_file):
                logger.error("❌ SQL初始化失败")
                sys.exit(1)
        else:
            logger.warning(f"⚠️  未找到SQL初始化文件: {sql_file}")
    
    # 5. 再次检查表
    if not check_tables():
        logger.error("❌ 数据库表创建失败")
        sys.exit(1)
    
    # 6. 初始化向量存储
    initialize_vector_storage()
    
    logger.info("🎉 数据库初始化完成！")

if __name__ == '__main__':
    main()