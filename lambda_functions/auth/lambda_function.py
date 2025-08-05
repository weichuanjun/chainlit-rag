"""
用户认证Lambda函数
"""
import json
import os
import boto3
import jwt
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

# 配置日志
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# 初始化AWS客户端
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])

# JWT配置
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key')
JWT_ALGORITHM = 'HS256'
TOKEN_EXPIRY_HOURS = 24

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        # 解析请求
        http_method = event['httpMethod']
        path = event['path']
        body = json.loads(event.get('body', '{}'))
        
        logger.info(f"处理请求: {http_method} {path}")
        
        # 路由处理
        if http_method == 'POST' and path.endswith('/auth/login'):
            return handle_login(body)
        elif http_method == 'POST' and path.endswith('/auth/register'):
            return handle_register(body)
        elif http_method == 'POST' and path.endswith('/auth/verify'):
            return handle_verify_token(event)
        elif http_method == 'POST' and path.endswith('/auth/refresh'):
            return handle_refresh_token(event)
        else:
            return create_response(404, {'error': '未找到请求的资源'})
            
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return create_response(500, {'error': '服务器内部错误'})

def handle_login(body: Dict[str, Any]) -> Dict[str, Any]:
    """处理用户登录"""
    try:
        email = body.get('email')
        password = body.get('password')
        
        if not email or not password:
            return create_response(400, {'error': '邮箱和密码不能为空'})
        
        # 查找用户
        user = get_user_by_email(email)
        if not user:
            return create_response(401, {'error': '邮箱或密码错误'})
        
        # 验证密码
        if not verify_password(password, user['password_hash']):
            return create_response(401, {'error': '邮箱或密码错误'})
        
        # 检查用户状态
        if not user.get('is_active', True):
            return create_response(401, {'error': '账户已被禁用'})
        
        # 更新最后登录时间
        update_last_login(user['user_id'])
        
        # 生成JWT令牌
        access_token = generate_jwt_token(user)
        refresh_token = generate_refresh_token(user)
        
        # 返回用户信息和令牌
        return create_response(200, {
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': TOKEN_EXPIRY_HOURS * 3600,
            'user': {
                'user_id': user['user_id'],
                'email': user['email'],
                'username': user['username'],
                'full_name': user.get('full_name'),
                'avatar_url': user.get('avatar_url'),
                'role': user.get('role', 'user')
            }
        })
        
    except Exception as e:
        logger.error(f"登录处理失败: {str(e)}")
        return create_response(500, {'error': '登录失败'})

def handle_register(body: Dict[str, Any]) -> Dict[str, Any]:
    """处理用户注册"""
    try:
        email = body.get('email')
        username = body.get('username')
        password = body.get('password')
        full_name = body.get('full_name')
        
        # 验证必填字段
        if not email or not username or not password:
            return create_response(400, {'error': '邮箱、用户名和密码不能为空'})
        
        # 验证邮箱格式
        if '@' not in email:
            return create_response(400, {'error': '邮箱格式不正确'})
        
        # 验证密码强度
        if len(password) < 6:
            return create_response(400, {'error': '密码长度至少6位'})
        
        # 检查用户是否已存在
        existing_user = get_user_by_email(email)
        if existing_user:
            return create_response(409, {'error': '邮箱已被注册'})
        
        # 创建用户
        user_id = create_user_id()
        password_hash = hash_password(password)
        
        user_data = {
            'user_id': user_id,
            'email': email,
            'username': username,
            'password_hash': password_hash,
            'full_name': full_name,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'is_active': True,
            'role': 'user',
            'preferences': {}
        }
        
        # 保存到数据库
        try:
            users_table.put_item(
                Item=user_data,
                ConditionExpression='attribute_not_exists(user_id) AND attribute_not_exists(email)'
            )
        except users_table.meta.client.exceptions.ConditionalCheckFailedException:
            return create_response(409, {'error': '用户已存在'})
        
        # 生成JWT令牌
        access_token = generate_jwt_token(user_data)
        refresh_token = generate_refresh_token(user_data)
        
        logger.info(f"用户注册成功: {email}")
        
        return create_response(201, {
            'message': '注册成功',
            'access_token': access_token,
            'refresh_token': refresh_token,
            'token_type': 'Bearer',
            'expires_in': TOKEN_EXPIRY_HOURS * 3600,
            'user': {
                'user_id': user_id,
                'email': email,
                'username': username,
                'full_name': full_name,
                'role': 'user'
            }
        })
        
    except Exception as e:
        logger.error(f"注册处理失败: {str(e)}")
        return create_response(500, {'error': '注册失败'})

def handle_verify_token(event: Dict[str, Any]) -> Dict[str, Any]:
    """验证JWT令牌"""
    try:
        token = extract_token_from_headers(event.get('headers', {}))
        if not token:
            return create_response(401, {'error': '缺少访问令牌'})
        
        # 验证令牌
        payload = verify_jwt_token(token)
        if not payload:
            return create_response(401, {'error': '无效的访问令牌'})
        
        # 获取用户信息
        user = get_user_by_id(payload['user_id'])
        if not user or not user.get('is_active', True):
            return create_response(401, {'error': '用户不存在或已被禁用'})
        
        return create_response(200, {
            'valid': True,
            'user': {
                'user_id': user['user_id'],
                'email': user['email'],
                'username': user['username'],
                'full_name': user.get('full_name'),
                'role': user.get('role', 'user')
            }
        })
        
    except Exception as e:
        logger.error(f"令牌验证失败: {str(e)}")
        return create_response(401, {'error': '令牌验证失败'})

def handle_refresh_token(event: Dict[str, Any]) -> Dict[str, Any]:
    """刷新访问令牌"""
    try:
        body = json.loads(event.get('body', '{}'))
        refresh_token = body.get('refresh_token')
        
        if not refresh_token:
            return create_response(400, {'error': '缺少刷新令牌'})
        
        # 验证刷新令牌
        payload = verify_jwt_token(refresh_token)
        if not payload or payload.get('token_type') != 'refresh':
            return create_response(401, {'error': '无效的刷新令牌'})
        
        # 获取用户信息
        user = get_user_by_id(payload['user_id'])
        if not user or not user.get('is_active', True):
            return create_response(401, {'error': '用户不存在或已被禁用'})
        
        # 生成新的访问令牌
        access_token = generate_jwt_token(user)
        
        return create_response(200, {
            'access_token': access_token,
            'token_type': 'Bearer',
            'expires_in': TOKEN_EXPIRY_HOURS * 3600
        })
        
    except Exception as e:
        logger.error(f"令牌刷新失败: {str(e)}")
        return create_response(401, {'error': '令牌刷新失败'})

# 辅助函数

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """根据邮箱获取用户"""
    try:
        response = users_table.scan(
            FilterExpression='email = :email',
            ExpressionAttributeValues={':email': email}
        )
        
        if response['Items']:
            return response['Items'][0]
        return None
        
    except Exception as e:
        logger.error(f"查询用户失败: {str(e)}")
        return None

def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取用户"""
    try:
        response = users_table.get_item(Key={'user_id': user_id})
        return response.get('Item')
        
    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}")
        return None

def update_last_login(user_id: str):
    """更新最后登录时间"""
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET last_login = :timestamp',
            ExpressionAttributeValues={':timestamp': datetime.utcnow().isoformat()}
        )
    except Exception as e:
        logger.error(f"更新登录时间失败: {str(e)}")

def create_user_id() -> str:
    """生成用户ID"""
    import uuid
    return str(uuid.uuid4())

def hash_password(password: str) -> str:
    """加密密码"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_jwt_token(user: Dict[str, Any]) -> str:
    """生成JWT访问令牌"""
    payload = {
        'user_id': user['user_id'],
        'email': user['email'],
        'username': user['username'],
        'role': user.get('role', 'user'),
        'token_type': 'access',
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def generate_refresh_token(user: Dict[str, Any]) -> str:
    """生成JWT刷新令牌"""
    payload = {
        'user_id': user['user_id'],
        'token_type': 'refresh',
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=30)  # 30天有效期
    }
    
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT令牌已过期")
        return None
    except jwt.InvalidTokenError:
        logger.warning("无效的JWT令牌")
        return None

def extract_token_from_headers(headers: Dict[str, str]) -> Optional[str]:
    """从请求头中提取令牌"""
    auth_header = headers.get('Authorization') or headers.get('authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]  # 移除 "Bearer " 前缀
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