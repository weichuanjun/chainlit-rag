"""
聊天处理Lambda函数
使用Agent引擎处理用户对话
"""
import json
import os
import boto3
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 初始化AWS客户端
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# 环境变量
CHAT_HISTORY_TABLE = os.environ['CHAT_HISTORY_TABLE']
DOCUMENTS_TABLE = os.environ['DOCUMENTS_TABLE']
OPENAI_SECRET_ARN = os.environ['OPENAI_SECRET_ARN']

chat_history_table = dynamodb.Table(CHAT_HISTORY_TABLE)
documents_table = dynamodb.Table(DOCUMENTS_TABLE)

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        http_method = event['httpMethod']
        path = event['path']
        
        logger.info(f"处理请求: {http_method} {path}")
        
        # 路由处理
        if http_method == 'POST' and path.endswith('/chat'):
            return handle_chat_message(event)
        elif http_method == 'GET' and path.endswith('/chat/history'):
            return handle_get_chat_history(event)
        elif http_method == 'GET' and path.endswith('/chat/conversations'):
            return handle_get_conversations(event)
        elif http_method == 'DELETE' and '/chat/conversations/' in path:
            return handle_delete_conversation(event)
        elif http_method == 'GET' and path.endswith('/chat/agents'):
            return handle_get_available_agents(event)
        else:
            return create_response(404, {'error': '未找到请求的资源'})
            
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return create_response(500, {'error': '服务器内部错误'})

def handle_chat_message(event: Dict[str, Any]) -> Dict[str, Any]:
    """处理聊天消息"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        body = json.loads(event.get('body', '{}'))
        message = body.get('message', '').strip()
        conversation_id = body.get('conversation_id')
        agent_workflow = body.get('agent_workflow', 'default_rag')
        context_documents = body.get('context_documents', [])
        
        if not message:
            return create_response(400, {'error': '消息内容不能为空'})
        
        # 如果没有对话ID，创建新对话
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            logger.info(f"创建新对话: {conversation_id}")
        
        # 保存用户消息
        user_message = {
            'message_id': str(uuid.uuid4()),
            'conversation_id': conversation_id,
            'user_id': user_id,
            'role': 'user',
            'content': message,
            'created_at': datetime.utcnow().isoformat(),
            'metadata': {
                'agent_workflow': agent_workflow,
                'context_documents': context_documents
            }
        }
        
        chat_history_table.put_item(Item=user_message)
        
        # 处理消息并生成回复
        response_data = process_message_with_agent(
            message=message,
            user_id=user_id,
            conversation_id=conversation_id,
            agent_workflow=agent_workflow,
            context_documents=context_documents
        )
        
        # 保存AI回复
        ai_message = {
            'message_id': str(uuid.uuid4()),
            'conversation_id': conversation_id,
            'user_id': user_id,
            'role': 'assistant',
            'content': response_data['response'],
            'created_at': datetime.utcnow().isoformat(),
            'agent_workflow': agent_workflow,
            'used_documents': response_data.get('used_documents', []),
            'reasoning_steps': response_data.get('reasoning_steps', []),
            'metadata': response_data.get('metadata', {})
        }
        
        chat_history_table.put_item(Item=ai_message)
        
        return create_response(200, {
            'message_id': ai_message['message_id'],
            'conversation_id': conversation_id,
            'content': response_data['response'],
            'used_documents': response_data.get('used_documents', []),
            'reasoning_steps': response_data.get('reasoning_steps', []),
            'agent_workflow': agent_workflow,
            'metadata': response_data.get('metadata', {})
        })
        
    except Exception as e:
        logger.error(f"处理聊天消息失败: {str(e)}")
        return create_response(500, {'error': '处理消息失败'})

def handle_get_chat_history(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取聊天历史"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        query_params = event.get('queryStringParameters') or {}
        conversation_id = query_params.get('conversation_id')
        limit = int(query_params.get('limit', '50'))
        
        if not conversation_id:
            return create_response(400, {'error': '缺少conversation_id参数'})
        
        # 获取对话消息
        response = chat_history_table.scan(
            FilterExpression='conversation_id = :conv_id AND user_id = :user_id',
            ExpressionAttributeValues={
                ':conv_id': conversation_id,
                ':user_id': user_id
            },
            Limit=limit
        )
        
        messages = response['Items']
        
        # 按时间排序
        messages.sort(key=lambda x: x.get('created_at', ''))
        
        return create_response(200, {
            'conversation_id': conversation_id,
            'messages': messages,
            'total_count': len(messages)
        })
        
    except Exception as e:
        logger.error(f"获取聊天历史失败: {str(e)}")
        return create_response(500, {'error': '获取聊天历史失败'})

def handle_get_conversations(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取用户的对话列表"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', '20'))
        
        # 获取用户的所有消息
        response = chat_history_table.scan(
            FilterExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id}
        )
        
        messages = response['Items']
        
        # 按对话ID分组
        conversations = {}
        for message in messages:
            conv_id = message['conversation_id']
            if conv_id not in conversations:
                conversations[conv_id] = {
                    'conversation_id': conv_id,
                    'user_id': user_id,
                    'messages': [],
                    'last_message_at': None,
                    'message_count': 0,
                    'title': '新对话',
                    'agent_workflow': message.get('agent_workflow', 'default_rag')
                }
            
            conversations[conv_id]['messages'].append(message)
            conversations[conv_id]['message_count'] += 1
            
            message_time = message.get('created_at')
            if not conversations[conv_id]['last_message_at'] or message_time > conversations[conv_id]['last_message_at']:
                conversations[conv_id]['last_message_at'] = message_time
                
                # 如果是用户消息，用作对话标题
                if message.get('role') == 'user':
                    content = message.get('content', '')
                    title = content[:30] + '...' if len(content) > 30 else content
                    conversations[conv_id]['title'] = title or '新对话'
        
        # 转换为列表并排序
        conv_list = list(conversations.values())
        conv_list.sort(key=lambda x: x['last_message_at'] or '', reverse=True)
        
        # 限制返回数量
        conv_list = conv_list[:limit]
        
        # 移除完整的消息列表，只保留摘要
        for conv in conv_list:
            # 保留最后一条消息作为预览
            if conv['messages']:
                last_message = max(conv['messages'], key=lambda x: x.get('created_at', ''))
                conv['preview'] = last_message.get('content', '')[:100]
            else:
                conv['preview'] = ''
            del conv['messages']
        
        return create_response(200, {
            'conversations': conv_list,
            'total_count': len(conv_list)
        })
        
    except Exception as e:
        logger.error(f"获取对话列表失败: {str(e)}")
        return create_response(500, {'error': '获取对话列表失败'})

def handle_delete_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """删除对话"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 提取对话ID
        path_parts = event['path'].split('/')
        conversation_id = path_parts[-1]
        
        # 获取对话中的所有消息
        response = chat_history_table.scan(
            FilterExpression='conversation_id = :conv_id AND user_id = :user_id',
            ExpressionAttributeValues={
                ':conv_id': conversation_id,
                ':user_id': user_id
            }
        )
        
        messages = response['Items']
        
        if not messages:
            return create_response(404, {'error': '对话不存在或无权限访问'})
        
        # 删除所有消息
        for message in messages:
            chat_history_table.delete_item(Key={'message_id': message['message_id']})
        
        return create_response(200, {
            'message': '对话删除成功',
            'deleted_messages': len(messages)
        })
        
    except Exception as e:
        logger.error(f"删除对话失败: {str(e)}")
        return create_response(500, {'error': '删除对话失败'})

def handle_get_available_agents(event: Dict[str, Any]) -> Dict[str, Any]:
    """获取可用的Agent列表"""
    try:
        # 验证用户身份
        user_id = get_user_id_from_token(event)
        if not user_id:
            return create_response(401, {'error': '未授权访问'})
        
        # 返回可用的Agent列表（从配置文件读取）
        agents = [
            {
                'id': 'default_rag',
                'name': '默认RAG助手',
                'description': '基础的检索增强生成助手，适合一般问答',
                'capabilities': ['文档检索', '问答生成', '上下文理解']
            },
            {
                'id': 'analytical_agent',
                'name': '分析型助手',
                'description': '专门用于数据分析和深度解答，提供结构化回答',
                'capabilities': ['深度分析', '证据聚合', '结构化回答', '多步推理']
            },
            {
                'id': 'conversational_agent',
                'name': '对话型助手',
                'description': '支持多轮对话的友好助手，记忆对话历史',
                'capabilities': ['对话记忆', '上下文跟踪', '友好交互', '澄清询问']
            }
        ]
        
        return create_response(200, {'agents': agents})
        
    except Exception as e:
        logger.error(f"获取Agent列表失败: {str(e)}")
        return create_response(500, {'error': '获取Agent列表失败'})

def process_message_with_agent(
    message: str,
    user_id: str,
    conversation_id: str,
    agent_workflow: str,
    context_documents: List[str]
) -> Dict[str, Any]:
    """使用Agent引擎处理消息"""
    try:
        # 这里应该调用Agent引擎
        # 为了简化，先返回模拟响应
        
        # 模拟文档检索
        retrieved_docs = simulate_document_retrieval(message, user_id, context_documents)
        
        # 模拟AI回复生成
        response = simulate_ai_response(message, retrieved_docs, agent_workflow)
        
        return {
            'response': response,
            'used_documents': [doc['document_id'] for doc in retrieved_docs],
            'reasoning_steps': [
                {'step': 'query_preprocessing', 'description': '处理用户查询'},
                {'step': 'document_retrieval', 'description': f'检索到{len(retrieved_docs)}个相关文档'},
                {'step': 'response_generation', 'description': '生成AI回答'}
            ],
            'metadata': {
                'agent_workflow': agent_workflow,
                'retrieval_count': len(retrieved_docs)
            }
        }
        
    except Exception as e:
        logger.error(f"Agent处理失败: {str(e)}")
        return {
            'response': '抱歉，我在处理您的消息时遇到了问题，请稍后重试。',
            'used_documents': [],
            'reasoning_steps': [],
            'metadata': {'error': str(e)}
        }

def simulate_document_retrieval(query: str, user_id: str, context_documents: List[str]) -> List[Dict[str, Any]]:
    """模拟文档检索"""
    try:
        # 获取用户的文档
        response = documents_table.scan(
            FilterExpression='user_id = :user_id AND #status = :status',
            ExpressionAttributeValues={
                ':user_id': user_id,
                ':status': 'processed'
            },
            ExpressionAttributeNames={'#status': 'status'}
        )
        
        documents = response['Items']
        
        # 简单的关键词匹配（实际应该使用向量搜索）
        relevant_docs = []
        query_lower = query.lower()
        
        for doc in documents[:3]:  # 最多返回3个文档
            if context_documents and doc['document_id'] not in context_documents:
                continue
                
            # 简单的相关性评分
            content = doc.get('content_text', '').lower()
            score = 0.5 + (0.3 if any(word in content for word in query_lower.split()) else 0)
            
            relevant_docs.append({
                'document_id': doc['document_id'],
                'filename': doc['filename'],
                'content_preview': doc.get('content_text', '')[:200],
                'similarity_score': score
            })
        
        return relevant_docs
        
    except Exception as e:
        logger.error(f"文档检索模拟失败: {str(e)}")
        return []

def simulate_ai_response(query: str, retrieved_docs: List[Dict[str, Any]], agent_workflow: str) -> str:
    """模拟AI回复生成"""
    try:
        if not retrieved_docs:
            return "抱歉，我在您的知识库中没有找到相关信息。请尝试上传相关文档或重新表述您的问题。"
        
        # 根据不同的Agent工作流生成不同风格的回答
        if agent_workflow == 'analytical_agent':
            response = f"""基于对您的问题"{query}"的分析，我找到了以下相关信息：

## 主要发现
根据检索到的{len(retrieved_docs)}个文档，我为您整理了以下要点：

## 支持证据
"""
            for i, doc in enumerate(retrieved_docs, 1):
                response += f"{i}. 来源：{doc['filename']}\n   内容：{doc['content_preview'][:100]}...\n\n"
            
            response += "## 总结\n基于以上信息，我建议您..."
            
        elif agent_workflow == 'conversational_agent':
            response = f"""我理解您询问的是关于"{query}"的问题。

让我基于您的知识库为您解答：

{retrieved_docs[0]['content_preview'][:200]}...

如果您需要更详细的信息，我可以为您查找更多相关内容。还有什么我可以帮助您的吗？"""
            
        else:  # default_rag
            response = f"""根据您的问题，我在知识库中找到了以下相关信息：

{retrieved_docs[0]['content_preview'][:300]}...

这些信息来自您的文档：{retrieved_docs[0]['filename']}。

希望这个回答对您有帮助。如果您需要更多详细信息，请告诉我。"""
        
        return response
        
    except Exception as e:
        logger.error(f"AI回复生成模拟失败: {str(e)}")
        return "抱歉，我在生成回答时遇到了问题。"

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

def get_secret(secret_arn: str) -> str:
    """获取Secrets Manager中的秘密"""
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return response['SecretString']
    except Exception as e:
        logger.error(f"获取秘密失败: {str(e)}")
        raise

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