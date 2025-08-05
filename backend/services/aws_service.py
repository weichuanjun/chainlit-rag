"""
AWS服务管理器
包括S3、DynamoDB、Lambda等服务的操作
"""
import boto3
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import logging
from botocore.exceptions import ClientError
import asyncio
from concurrent.futures import ThreadPoolExecutor

from backend.models.user import User
from backend.models.document import Document
from backend.models.chat import ChatMessage, Conversation
from config import config

logger = logging.getLogger(__name__)

class AWSService:
    """AWS服务管理器"""
    
    def __init__(self):
        self.session = boto3.Session(
            aws_access_key_id=config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
            region_name=config.AWS_REGION
        )
        
        self.s3_client = self.session.client('s3')
        self.dynamodb = self.session.resource('dynamodb')
        self.lambda_client = self.session.client('lambda')
        
        # DynamoDB表
        self.users_table = self.dynamodb.Table(config.DYNAMODB_USERS_TABLE)
        self.chat_history_table = self.dynamodb.Table(config.DYNAMODB_CHAT_HISTORY_TABLE)
        self.documents_table = self.dynamodb.Table(config.DYNAMODB_DOCUMENTS_TABLE)
        
        # S3存储桶
        self.s3_bucket = config.S3_BUCKET_NAME
        
        # 线程池用于异步操作
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    # =========================
    # S3 操作
    # =========================
    
    async def generate_presigned_upload_url(
        self, 
        filename: str, 
        file_type: str, 
        user_id: str,
        expires_in: int = 3600
    ) -> Tuple[str, Dict[str, str]]:
        """
        生成S3预签名上传URL
        
        Args:
            filename: 文件名
            file_type: 文件类型
            user_id: 用户ID
            expires_in: URL过期时间（秒）
            
        Returns:
            (upload_url, form_fields)
        """
        try:
            # 生成S3键名
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            s3_key = f"documents/{user_id}/{timestamp}_{filename}"
            
            # 生成预签名POST URL
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.s3_client.generate_presigned_post(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Fields={"Content-Type": file_type},
                    Conditions=[
                        {"Content-Type": file_type},
                        ["content-length-range", 1, 50 * 1024 * 1024]  # 1B到50MB
                    ],
                    ExpiresIn=expires_in
                )
            )
            
            return response['url'], response['fields']
            
        except Exception as e:
            logger.error(f"生成S3预签名URL失败: {str(e)}")
            raise
    
    async def download_file_from_s3(self, s3_key: str) -> bytes:
        """
        从S3下载文件
        
        Args:
            s3_key: S3对象键
            
        Returns:
            文件内容
        """
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.s3_client.get_object(Bucket=self.s3_bucket, Key=s3_key)
            )
            return response['Body'].read()
            
        except Exception as e:
            logger.error(f"从S3下载文件失败: {str(e)}")
            raise
    
    async def delete_file_from_s3(self, s3_key: str) -> bool:
        """
        从S3删除文件
        
        Args:
            s3_key: S3对象键
            
        Returns:
            是否成功删除
        """
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.s3_client.delete_object(Bucket=self.s3_bucket, Key=s3_key)
            )
            return True
            
        except Exception as e:
            logger.error(f"从S3删除文件失败: {str(e)}")
            return False
    
    # =========================
    # DynamoDB 用户操作
    # =========================
    
    async def create_user(self, user: User) -> bool:
        """创建用户"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.users_table.put_item(
                    Item=user.to_dict(),
                    ConditionExpression='attribute_not_exists(user_id)'
                )
            )
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                logger.warning(f"用户已存在: {user.user_id}")
                return False
            logger.error(f"创建用户失败: {str(e)}")
            return False
    
    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.users_table.get_item(Key={'user_id': user_id})
            )
            
            if 'Item' in response:
                return User.from_dict(response['Item'])
            return None
            
        except Exception as e:
            logger.error(f"获取用户失败: {str(e)}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.users_table.scan(
                    FilterExpression='email = :email',
                    ExpressionAttributeValues={':email': email}
                )
            )
            
            if response['Items']:
                return User.from_dict(response['Items'][0])
            return None
            
        except Exception as e:
            logger.error(f"根据邮箱获取用户失败: {str(e)}")
            return None
    
    async def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """更新用户信息"""
        try:
            # 构建更新表达式
            update_expression = "SET "
            expression_values = {}
            
            for key, value in updates.items():
                if key not in ['user_id']:  # 不允许更新主键
                    update_expression += f"{key} = :{key}, "
                    expression_values[f":{key}"] = value
            
            update_expression = update_expression.rstrip(', ')
            update_expression += ", updated_at = :updated_at"
            expression_values[":updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.users_table.update_item(
                    Key={'user_id': user_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values
                )
            )
            return True
            
        except Exception as e:
            logger.error(f"更新用户失败: {str(e)}")
            return False
    
    # =========================
    # DynamoDB 文档操作
    # =========================
    
    async def create_document(self, document: Document) -> bool:
        """创建文档记录"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.documents_table.put_item(Item=document.to_dict())
            )
            return True
            
        except Exception as e:
            logger.error(f"创建文档记录失败: {str(e)}")
            return False
    
    async def get_document_by_id(self, document_id: str) -> Optional[Document]:
        """获取文档"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.documents_table.get_item(Key={'document_id': document_id})
            )
            
            if 'Item' in response:
                return Document.from_dict(response['Item'])
            return None
            
        except Exception as e:
            logger.error(f"获取文档失败: {str(e)}")
            return None
    
    async def get_user_documents(
        self, 
        user_id: str, 
        limit: int = 50, 
        last_key: Optional[str] = None
    ) -> Tuple[List[Document], Optional[str]]:
        """获取用户的文档列表"""
        try:
            scan_kwargs = {
                'FilterExpression': 'user_id = :user_id',
                'ExpressionAttributeValues': {':user_id': user_id},
                'Limit': limit
            }
            
            if last_key:
                scan_kwargs['ExclusiveStartKey'] = {'document_id': last_key}
            
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.documents_table.scan(**scan_kwargs)
            )
            
            documents = [Document.from_dict(item) for item in response['Items']]
            next_key = response.get('LastEvaluatedKey', {}).get('document_id')
            
            return documents, next_key
            
        except Exception as e:
            logger.error(f"获取用户文档列表失败: {str(e)}")
            return [], None
    
    async def update_document(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """更新文档"""
        try:
            update_expression = "SET "
            expression_values = {}
            
            for key, value in updates.items():
                if key not in ['document_id']:
                    update_expression += f"{key} = :{key}, "
                    expression_values[f":{key}"] = value
            
            update_expression = update_expression.rstrip(', ')
            update_expression += ", updated_at = :updated_at"
            expression_values[":updated_at"] = datetime.utcnow().isoformat()
            
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.documents_table.update_item(
                    Key={'document_id': document_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_values
                )
            )
            return True
            
        except Exception as e:
            logger.error(f"更新文档失败: {str(e)}")
            return False
    
    async def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.documents_table.delete_item(Key={'document_id': document_id})
            )
            return True
            
        except Exception as e:
            logger.error(f"删除文档失败: {str(e)}")
            return False
    
    # =========================
    # DynamoDB 聊天记录操作
    # =========================
    
    async def save_chat_message(self, message: ChatMessage) -> bool:
        """保存聊天消息"""
        try:
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.chat_history_table.put_item(Item=message.to_dict())
            )
            return True
            
        except Exception as e:
            logger.error(f"保存聊天消息失败: {str(e)}")
            return False
    
    async def get_conversation_messages(
        self, 
        conversation_id: str, 
        limit: int = 50
    ) -> List[ChatMessage]:
        """获取对话消息"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.chat_history_table.scan(
                    FilterExpression='conversation_id = :conv_id',
                    ExpressionAttributeValues={':conv_id': conversation_id},
                    Limit=limit
                )
            )
            
            messages = [ChatMessage.from_dict(item) for item in response['Items']]
            # 按时间排序
            messages.sort(key=lambda x: x.created_at)
            
            return messages
            
        except Exception as e:
            logger.error(f"获取对话消息失败: {str(e)}")
            return []
    
    async def get_user_conversations(
        self, 
        user_id: str, 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """获取用户的对话列表"""
        try:
            # 由于DynamoDB的限制，这里使用聚合查询
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.chat_history_table.scan(
                    FilterExpression='user_id = :user_id',
                    ExpressionAttributeValues={':user_id': user_id}
                )
            )
            
            # 按对话ID分组
            conversations = {}
            for item in response['Items']:
                conv_id = item['conversation_id']
                if conv_id not in conversations:
                    conversations[conv_id] = {
                        'conversation_id': conv_id,
                        'user_id': user_id,
                        'messages': [],
                        'last_message_at': None,
                        'message_count': 0
                    }
                
                message = ChatMessage.from_dict(item)
                conversations[conv_id]['messages'].append(message)
                conversations[conv_id]['message_count'] += 1
                
                if not conversations[conv_id]['last_message_at'] or message.created_at > conversations[conv_id]['last_message_at']:
                    conversations[conv_id]['last_message_at'] = message.created_at
            
            # 转换为列表并排序
            conv_list = list(conversations.values())
            conv_list.sort(key=lambda x: x['last_message_at'], reverse=True)
            
            return conv_list[:limit]
            
        except Exception as e:
            logger.error(f"获取用户对话列表失败: {str(e)}")
            return []
    
    # =========================
    # Lambda 函数调用
    # =========================
    
    async def invoke_lambda_function(
        self, 
        function_name: str, 
        payload: Dict[str, Any],
        invocation_type: str = 'RequestResponse'
    ) -> Dict[str, Any]:
        """调用Lambda函数"""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.lambda_client.invoke(
                    FunctionName=function_name,
                    InvocationType=invocation_type,
                    Payload=json.dumps(payload)
                )
            )
            
            if 'Payload' in response:
                payload_data = response['Payload'].read()
                return json.loads(payload_data)
            
            return {"statusCode": response['StatusCode']}
            
        except Exception as e:
            logger.error(f"调用Lambda函数失败: {str(e)}")
            return {"error": str(e)}
    
    # =========================
    # 健康检查和统计
    # =========================
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        health = {
            "s3": False,
            "dynamodb": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # 检查S3
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.s3_client.head_bucket(Bucket=self.s3_bucket)
            )
            health["s3"] = True
        except Exception as e:
            logger.error(f"S3健康检查失败: {str(e)}")
        
        try:
            # 检查DynamoDB
            await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.users_table.table_status
            )
            health["dynamodb"] = True
        except Exception as e:
            logger.error(f"DynamoDB健康检查失败: {str(e)}")
        
        return health