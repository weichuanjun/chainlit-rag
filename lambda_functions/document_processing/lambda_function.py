"""
文档处理Lambda函数
负责文档上传、解析、分块和向量化
"""
import json
import os
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging
from io import BytesIO
import base64

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 初始化AWS客户端
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sqs_client = boto3.client('sqs')
secrets_client = boto3.client('secretsmanager')

# 环境变量
DOCUMENTS_TABLE = os.environ['DOCUMENTS_TABLE']
DOCUMENTS_BUCKET = os.environ['DOCUMENTS_BUCKET']
PROCESSING_QUEUE = os.environ['PROCESSING_QUEUE']
OPENAI_SECRET_ARN = os.environ['OPENAI_SECRET_ARN']

documents_table = dynamodb.Table(DOCUMENTS_TABLE)

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        # 检查是否是SQS触发
        if 'Records' in event:
            return handle_sqs_messages(event['Records'])
        
        # HTTP API请求处理
        http_method = event['httpMethod']
        path = event['path']
        
        logger.info(f"处理请求: {http_method} {path}")
        
        # 路由处理
        if http_method == 'POST' and path.endswith('/documents/upload'):
            return handle_upload_request(event)
        elif http_method == 'GET' and path.endswith('/documents'):
            return handle_list_documents(event)
        elif http_method == 'DELETE' and '/documents/' in path:
            return handle_delete_document(event)
        elif http_method == 'GET' and '/documents/' in path:
            return handle_get_document(event)
        else:
            return create_response(404, {'error': '未找到请求的资源'})
            
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return create_response(500, {'error': '服务器内部错误'})

def handle_upload_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """处理文档上传请求"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        body = json.loads(event.get('body', '{}'))
        filename = body.get('filename')
        file_type = body.get('file_type')
        file_size = body.get('file_size')
        tags = body.get('tags', [])
        
        if not filename or not file_type:
            return create_response(400, {'error': '文件名和文件类型不能为空'})
        
        # 验证文件类型
        allowed_types = ['application/pdf', 'text/plain', 'text/markdown', 
                        'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if file_type not in allowed_types:
            return create_response(400, {'error': '不支持的文件类型'})
        
        # 验证文件大小
        if file_size and file_size > 50 * 1024 * 1024:  # 50MB
            return create_response(400, {'error': '文件大小不能超过50MB'})
        
        # 生成文档ID和S3键
        document_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        s3_key = f"documents/{user_id}/{timestamp}_{filename}"
        
        # 创建文档记录
        document_data = {
            'document_id': document_id,
            'user_id': user_id,
            'filename': filename,
            'original_filename': filename,
            'file_type': file_type,
            'file_size': file_size or 0,
            's3_key': s3_key,
            's3_bucket': DOCUMENTS_BUCKET,
            'status': 'uploading',
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'chunk_count': 0,
            'vector_count': 0,
            'tags': tags,
            'metadata': {}
        }
        
        # 保存到数据库
        documents_table.put_item(Item=document_data)
        
        # 生成预签名上传URL
        try:
            response = s3_client.generate_presigned_post(
                Bucket=DOCUMENTS_BUCKET,
                Key=s3_key,
                Fields={'Content-Type': file_type},
                Conditions=[
                    {'Content-Type': file_type},
                    ['content-length-range', 1, 50 * 1024 * 1024]
                ],
                ExpiresIn=3600  # 1小时
            )
            
            return create_response(200, {
                'document_id': document_id,
                'upload_url': response['url'],
                'fields': response['fields'],
                'message': '上传URL生成成功'
            })
            
        except Exception as e:
            logger.error(f"生成预签名URL失败: {str(e)}")
            return create_response(500, {'error': '上传URL生成失败'})
            
    except Exception as e:
        logger.error(f"处理上传请求失败: {str(e)}")
        return create_response(500, {'error': '处理上传请求失败'})

def handle_list_documents(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取用户文档列表"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 解析查询参数
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '20'))
        last_key = query_params.get('last_key')
        
        # 构建查询参数
        scan_kwargs = {
            'FilterExpression': 'user_id = :user_id',
            'ExpressionAttributeValues': {':user_id': user_id},
            'Limit': min(limit, 100)  # 最大100个
        }
        
        if last_key:
            scan_kwargs['ExclusiveStartKey'] = {'document_id': last_key}
        
        # 查询文档
        response = documents_table.scan(**scan_kwargs)
        
        documents = response['Items']
        next_key = response.get('LastEvaluatedKey', {}).get('document_id')
        
        # 按创建时间排序
        documents.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return create_response(200, {
            'documents': documents,
            'total_count': len(documents),
            'has_more': bool(next_key),
            'next_key': next_key
        })
        
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        return create_response(500, {'error': '获取文档列表失败'})

def handle_delete_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """删除文档"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 提取文档ID
        path_parts = event['path'].split('/')
        document_id = path_parts[-1]
        
        # 获取文档信息
        response = documents_table.get_item(Key={'document_id': document_id})
        document = response.get('Item')
        
        if not document:
            return create_response(404, {'error': '文档不存在'})
        
        # 检查权限
        if document['user_id'] != user_id:
            return create_response(403, {'error': '无权限删除此文档'})
        
        # 删除S3文件
        try:
            s3_client.delete_object(Bucket=document['s3_bucket'], Key=document['s3_key'])
        except Exception as e:
            logger.warning(f"删除S3文件失败: {str(e)}")
        
        # 删除数据库记录
        documents_table.delete_item(Key={'document_id': document_id})
        
        # TODO: 删除向量数据库中的相关向量
        
        return create_response(200, {'message': '文档删除成功'})
        
    except Exception as e:
        logger.error(f"删除文档失败: {str(e)}")
        return create_response(500, {'error': '删除文档失败'})

def handle_get_document(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取文档详情"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 提取文档ID
        path_parts = event['path'].split('/')
        document_id = path_parts[-1]
        
        # 获取文档信息
        response = documents_table.get_item(Key={'document_id': document_id})
        document = response.get('Item')
        
        if not document:
            return create_response(404, {'error': '文档不存在'})
        
        # 检查权限
        if document['user_id'] != user_id:
            return create_response(403, {'error': '无权限访问此文档'})
        
        return create_response(200, {'document': document})
        
    except Exception as e:
        logger.error(f"获取文档详情失败: {str(e)}")
        return create_response(500, {'error': '获取文档详情失败'})

def handle_sqs_messages(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """处理SQS消息"""
    processed_count = 0
    failed_count = 0
    
    for record in records:
        try:
            # 解析消息
            message_body = json.loads(record['body'])
            document_id = message_body.get('document_id')
            
            if not document_id:
                logger.error("SQS消息缺少document_id")
                failed_count += 1
                continue
            
            # 处理文档
            success = process_document(document_id)
            if success:
                processed_count += 1
            else:
                failed_count += 1
                
        except Exception as e:
            logger.error(f"处理SQS消息失败: {str(e)}")
            failed_count += 1
    
    return {
        'processed': processed_count,
        'failed': failed_count
    }

def process_document(document_id: str) -> bool:
    """处理单个文档"""
    try:
        # 获取文档信息
        response = documents_table.get_item(Key={'document_id': document_id})
        document = response.get('Item')
        
        if not document:
            logger.error(f"文档不存在: {document_id}")
            return False
        
        # 更新状态为处理中
        update_document_status(document_id, 'processing')
        
        # 从S3下载文件
        file_content = download_file_from_s3(document['s3_bucket'], document['s3_key'])
        if not file_content:
            update_document_status(document_id, 'failed', '文件下载失败')
            return False
        
        # 解析文件内容
        text_content = extract_text_from_file(file_content, document['file_type'])
        if not text_content:
            update_document_status(document_id, 'failed', '文件解析失败')
            return False
        
        # 文本分块
        chunks = split_text_into_chunks(text_content)
        
        # 生成向量嵌入
        embeddings = generate_embeddings(chunks)
        if not embeddings:
            update_document_status(document_id, 'failed', '向量生成失败')
            return False
        
        # 存储向量（这里简化，实际应该调用向量数据库服务）
        # TODO: 调用向量数据库API存储embeddings
        
        # 更新文档状态
        updates = {
            'status': 'processed',
            'content_text': text_content[:2000],  # 保存前2000字符作为预览
            'chunk_count': len(chunks),
            'vector_count': len(embeddings),
            'processed_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }
        
        update_document_fields(document_id, updates)
        
        logger.info(f"文档处理成功: {document_id}")
        return True
        
    except Exception as e:
        logger.error(f"处理文档失败: {str(e)}")
        update_document_status(document_id, 'failed', str(e))
        return False

def download_file_from_s3(bucket: str, key: str) -> Optional[bytes]:
    """从S3下载文件"""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()
    except Exception as e:
        logger.error(f"从S3下载文件失败: {str(e)}")
        return None

def extract_text_from_file(file_content: bytes, file_type: str) -> Optional[str]:
    """从文件中提取文本"""
    try:
        if file_type == 'text/plain':
            return file_content.decode('utf-8')
        elif file_type == 'text/markdown':
            return file_content.decode('utf-8')
        elif file_type == 'application/pdf':
            return extract_text_from_pdf(file_content)
        elif file_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            return extract_text_from_docx(file_content)
        else:
            logger.error(f"不支持的文件类型: {file_type}")
            return None
    except Exception as e:
        logger.error(f"文本提取失败: {str(e)}")
        return None

def extract_text_from_pdf(file_content: bytes) -> str:
    """从PDF提取文本"""
    try:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"PDF文本提取失败: {str(e)}")
        return ""

def extract_text_from_docx(file_content: bytes) -> str:
    """从DOCX提取文本"""
    try:
        from docx import Document
        doc = Document(BytesIO(file_content))
        text = ""
        for paragraph in doc.paragraphs:
            text += paragraph.text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"DOCX文本提取失败: {str(e)}")
        return ""

def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """将文本分割成块"""
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        
        # 如果不是最后一块，尝试在句号处分割
        if end < text_length:
            # 查找最近的句号
            sentence_end = text.rfind('.', start, end)
            if sentence_end > start + chunk_size // 2:
                end = sentence_end + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        
        start = end - overlap
        if start <= 0:
            break
    
    return chunks

def generate_embeddings(chunks: List[str]) -> Optional[List[List[float]]]:
    """生成文本嵌入向量"""
    try:
        # 获取OpenAI API密钥
        openai_secret = get_secret(OPENAI_SECRET_ARN)
        api_key = json.loads(openai_secret)['api_key']
        
        # 这里应该调用OpenAI API生成嵌入
        # 为了简化，这里返回模拟数据
        logger.info(f"生成 {len(chunks)} 个文本块的嵌入向量")
        
        # TODO: 实际调用OpenAI嵌入API
        # 模拟返回
        embeddings = []
        for chunk in chunks:
            # 模拟1536维向量
            embedding = [0.0] * 1536
            embeddings.append(embedding)
        
        return embeddings
        
    except Exception as e:
        logger.error(f"生成嵌入向量失败: {str(e)}")
        return None

def get_secret(secret_arn: str) -> str:
    """获取Secrets Manager中的秘密"""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return response['SecretString']
    except Exception as e:
        logger.error(f"获取秘密失败: {str(e)}")
        raise

def update_document_status(document_id: str, status: str, error_message: str = None):
    """更新文档状态"""
    try:
        update_expression = "SET #status = :status, updated_at = :updated_at"
        expression_values = {
            ':status': status,
            ':updated_at': datetime.utcnow().isoformat()
        }
        expression_names = {'#status': 'status'}
        
        if error_message:
            update_expression += ", error_message = :error_message"
            expression_values[':error_message'] = error_message
        
        documents_table.update_item(
            Key={'document_id': document_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
    except Exception as e:
        logger.error(f"更新文档状态失败: {str(e)}")

def update_document_fields(document_id: str, updates: Dict[str, Any]):
    """更新文档字段"""
    try:
        update_expression = "SET "
        expression_values = {}
        
        for key, value in updates.items():
            update_expression += f"{key} = :{key}, "
            expression_values[f":{key}"] = value
        
        update_expression = update_expression.rstrip(', ')
        
        documents_table.update_item(
            Key={'document_id': document_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values
        )
    except Exception as e:
        logger.error(f"更新文档字段失败: {str(e)}")

def get_user_id_from_token(event: Dict[str, Any]) -> Optional[str]:
    """从JWT令牌中获取用户ID"""
    try:
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        
        token = auth_header[7:]  # 移除 "Bearer " 前缀
        
        # 这里应该验证JWT令牌并提取用户ID
        # 为了简化，这里返回模拟用户ID
        # TODO: 实际验证JWT令牌
        
        return "mock-user-id"
        
    except Exception as e:
        logger.error(f"提取用户ID失败: {str(e)}")
        return None

def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """创建HTTP响应"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization'
        },
        'body': json.dumps(body, ensure_ascii=False)
    }