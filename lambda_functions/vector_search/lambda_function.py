"""
向量搜索Lambda函数
提供文档向量搜索和相似度匹配服务
"""
import json
import os
import boto3
from typing import Dict, Any, List, Optional
import logging

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 初始化AWS客户端
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# 环境变量
DOCUMENTS_TABLE = os.environ['DOCUMENTS_TABLE']
OPENAI_SECRET_ARN = os.environ['OPENAI_SECRET_ARN']

documents_table = dynamodb.Table(DOCUMENTS_TABLE)

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        http_method = event['httpMethod']
        path = event['path']
        
        logger.info(f"处理请求: {http_method} {path}")
        
        # 路由处理
        if http_method == 'POST' and path.endswith('/search'):
            return handle_search_documents(event)
        elif http_method == 'GET' and path.endswith('/search/stats'):
            return handle_get_search_stats(event)
        elif http_method == 'POST' and path.endswith('/search/similar'):
            return handle_find_similar_documents(event)
        else:
            return create_response(404, {'error': '未找到请求的资源'})
            
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return create_response(500, {'error': '服务器内部错误'})

def handle_search_documents(event: Dict[str, Any]) -> Dict[str, Any]:
    """处理文档搜索请求"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', '').strip()
        top_k = min(body.get('top_k', 5), 20)  # 最多返回20个结果
        similarity_threshold = body.get('similarity_threshold', 0.7)
        document_ids = body.get('document_ids', [])
        file_types = body.get('file_types', [])
        
        if not query:
            return create_response(400, {'error': '搜索查询不能为空'})
        
        # 执行向量搜索
        search_results = perform_vector_search(
            query=query,
            user_id=user_id,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            document_ids=document_ids,
            file_types=file_types
        )
        
        return create_response(200, {
            'query': query,
            'results': search_results,
            'total_found': len(search_results),
            'search_params': {
                'top_k': top_k,
                'similarity_threshold': similarity_threshold,
                'document_filters': {
                    'document_ids': document_ids,
                    'file_types': file_types
                }
            }
        })
        
    except Exception as e:
        logger.error(f"文档搜索失败: {str(e)}")
        return create_response(500, {'error': '文档搜索失败'})

def handle_get_search_stats(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取搜索统计信息"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 获取用户的文档统计
        stats = get_user_document_stats(user_id)
        
        return create_response(200, stats)
        
    except Exception as e:
        logger.error(f"获取搜索统计失败: {str(e)}")
        return create_response(500, {'error': '获取统计信息失败'})

def handle_find_similar_documents(event: Dict[str, Any]) -> Dict[str, Any]:
    """查找相似文档"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        body = json.loads(event.get('body', '{}'))
        document_id = body.get('document_id')
        top_k = min(body.get('top_k', 5), 10)
        
        if not document_id:
            return create_response(400, {'error': '文档ID不能为空'})
        
        # 获取文档信息
        document = get_document_by_id(document_id, user_id)
        if not document:
            return create_response(404, {'error': '文档不存在或无权限访问'})
        
        # 查找相似文档
        similar_docs = find_similar_documents(document, user_id, top_k)
        
        return create_response(200, {
            'source_document': {
                'document_id': document['document_id'],
                'filename': document['filename'],
                'file_type': document['file_type']
            },
            'similar_documents': similar_docs,
            'total_found': len(similar_docs)
        })
        
    except Exception as e:
        logger.error(f"查找相似文档失败: {str(e)}")
        return create_response(500, {'error': '查找相似文档失败'})

def perform_vector_search(
    query: str,
    user_id: str,
    top_k: int,
    similarity_threshold: float,
    document_ids: List[str],
    file_types: List[str]
) -> List[Dict[str, Any]]:
    """执行向量搜索"""
    try:
        # 获取用户的处理完成的文档
        filter_expression = 'user_id = :user_id AND #status = :status'
        expression_values = {
            ':user_id': user_id,
            ':status': 'processed'
        }
        expression_names = {'#status': 'status'}
        
        # 添加文档ID过滤
        if document_ids:
            filter_expression += ' AND document_id IN (' + ','.join([f':doc_id_{i}' for i in range(len(document_ids))]) + ')'
            for i, doc_id in enumerate(document_ids):
                expression_values[f':doc_id_{i}'] = doc_id
        
        # 添加文件类型过滤
        if file_types:
            filter_expression += ' AND file_type IN (' + ','.join([f':file_type_{i}' for i in range(len(file_types))]) + ')'
            for i, file_type in enumerate(file_types):
                expression_values[f':file_type_{i}'] = file_type
        
        response = documents_table.scan(
            FilterExpression=filter_expression,
            ExpressionAttributeValues=expression_values,
            ExpressionAttributeNames=expression_names
        )
        
        documents = response['Items']
        
        if not documents:
            return []
        
        # 模拟向量搜索（实际应该使用嵌入向量进行相似度计算）
        search_results = []
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        for doc in documents:
            # 简单的关键词匹配和相似度计算
            content = doc.get('content_text', '').lower()
            content_words = set(content.split())
            
            # 计算词汇重叠度作为相似度
            overlap = len(query_words.intersection(content_words))
            total_words = len(query_words.union(content_words))
            similarity = overlap / total_words if total_words > 0 else 0
            
            # 加权计算（标题匹配给更高权重）
            filename_lower = doc.get('filename', '').lower()
            if any(word in filename_lower for word in query_words):
                similarity += 0.2
            
            # 添加基础相似度（避免完全为0）
            similarity = max(similarity, 0.1)
            
            if similarity >= similarity_threshold:
                # 提取相关片段
                relevant_chunk = extract_relevant_chunk(content, query_words)
                
                search_results.append({
                    'document_id': doc['document_id'],
                    'filename': doc['filename'],
                    'file_type': doc['file_type'],
                    'similarity_score': similarity,
                    'chunk_content': relevant_chunk,
                    'metadata': {
                        'file_size': doc.get('file_size', 0),
                        'created_at': doc.get('created_at'),
                        'chunk_count': doc.get('chunk_count', 0),
                        'tags': doc.get('tags', [])
                    }
                })
        
        # 按相似度排序并返回前top_k个结果
        search_results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return search_results[:top_k]
        
    except Exception as e:
        logger.error(f"向量搜索执行失败: {str(e)}")
        return []

def extract_relevant_chunk(content: str, query_words: set, chunk_size: int = 300) -> str:
    """提取包含查询词的相关文本片段"""
    try:
        content_lower = content.lower()
        
        # 查找第一个匹配的查询词位置
        best_pos = 0
        for word in query_words:
            pos = content_lower.find(word)
            if pos != -1:
                best_pos = pos
                break
        
        # 提取以匹配位置为中心的文本片段
        start_pos = max(0, best_pos - chunk_size // 2)
        end_pos = min(len(content), start_pos + chunk_size)
        
        chunk = content[start_pos:end_pos]
        
        # 如果不是从开头开始，添加省略号
        if start_pos > 0:
            chunk = '...' + chunk
        
        # 如果不是到结尾，添加省略号
        if end_pos < len(content):
            chunk = chunk + '...'
        
        return chunk.strip()
        
    except Exception as e:
        logger.error(f"提取相关片段失败: {str(e)}")
        return content[:300] + '...' if len(content) > 300 else content

def get_user_document_stats(user_id: str) -> Dict[str, Any]:
    """获取用户文档统计信息"""
    try:
        response = documents_table.scan(
            FilterExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id}
        )
        
        documents = response['Items']
        
        # 统计信息
        total_documents = len(documents)
        processed_documents = len([d for d in documents if d.get('status') == 'processed'])
        processing_documents = len([d for d in documents if d.get('status') == 'processing'])
        failed_documents = len([d for d in documents if d.get('status') == 'failed'])
        
        # 文件类型统计
        file_type_stats = {}
        total_size = 0
        total_chunks = 0
        
        for doc in documents:
            file_type = doc.get('file_type', 'unknown')
            file_type_stats[file_type] = file_type_stats.get(file_type, 0) + 1
            total_size += doc.get('file_size', 0)
            total_chunks += doc.get('chunk_count', 0)
        
        return {
            'total_documents': total_documents,
            'processed_documents': processed_documents,
            'processing_documents': processing_documents,
            'failed_documents': failed_documents,
            'total_file_size': total_size,
            'total_text_chunks': total_chunks,
            'file_type_distribution': file_type_stats,
            'average_chunks_per_document': total_chunks / max(processed_documents, 1),
            'searchable_documents': processed_documents
        }
        
    except Exception as e:
        logger.error(f"获取文档统计失败: {str(e)}")
        return {
            'total_documents': 0,
            'processed_documents': 0,
            'error': str(e)
        }

def get_document_by_id(document_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取文档"""
    try:
        response = documents_table.get_item(Key={'document_id': document_id})
        document = response.get('Item')
        
        if document and document.get('user_id') == user_id:
            return document
        return None
        
    except Exception as e:
        logger.error(f"获取文档失败: {str(e)}")
        return None

def find_similar_documents(
    source_document: Dict[str, Any],
    user_id: str,
    top_k: int
) -> List[Dict[str, Any]]:
    """查找与指定文档相似的其他文档"""
    try:
        # 获取用户的其他文档
        response = documents_table.scan(
            FilterExpression='user_id = :user_id AND document_id <> :source_id AND #status = :status',
            ExpressionAttributeValues={
                ':user_id': user_id,
                ':source_id': source_document['document_id'],
                ':status': 'processed'
            },
            ExpressionAttributeNames={'#status': 'status'}
        )
        
        other_documents = response['Items']
        
        if not other_documents:
            return []
        
        # 计算相似度
        source_content = source_document.get('content_text', '').lower()
        source_words = set(source_content.split())
        source_filename = source_document.get('filename', '').lower()
        
        similar_docs = []
        
        for doc in other_documents:
            doc_content = doc.get('content_text', '').lower()
            doc_words = set(doc_content.split())
            doc_filename = doc.get('filename', '').lower()
            
            # 计算内容相似度
            overlap = len(source_words.intersection(doc_words))
            total_words = len(source_words.union(doc_words))
            content_similarity = overlap / total_words if total_words > 0 else 0
            
            # 文件名相似度
            filename_similarity = 0
            if source_filename and doc_filename:
                source_name_words = set(source_filename.split())
                doc_name_words = set(doc_filename.split())
                name_overlap = len(source_name_words.intersection(doc_name_words))
                name_total = len(source_name_words.union(doc_name_words))
                filename_similarity = name_overlap / name_total if name_total > 0 else 0
            
            # 文件类型相似度
            type_similarity = 1.0 if source_document.get('file_type') == doc.get('file_type') else 0.5
            
            # 综合相似度
            overall_similarity = (
                content_similarity * 0.7 +
                filename_similarity * 0.2 +
                type_similarity * 0.1
            )
            
            if overall_similarity > 0.1:  # 最低相似度阈值
                similar_docs.append({
                    'document_id': doc['document_id'],
                    'filename': doc['filename'],
                    'file_type': doc['file_type'],
                    'similarity_score': overall_similarity,
                    'content_preview': doc.get('content_text', '')[:200],
                    'metadata': {
                        'file_size': doc.get('file_size', 0),
                        'created_at': doc.get('created_at'),
                        'chunk_count': doc.get('chunk_count', 0)
                    }
                })
        
        # 按相似度排序
        similar_docs.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similar_docs[:top_k]
        
    except Exception as e:
        logger.error(f"查找相似文档失败: {str(e)}")
        return []

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