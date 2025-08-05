"""
Chainlit RAG知识库系统前端应用
"""
import chainlit as cl
import aiohttp
import asyncio
from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 加载配置
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 检测运行环境并加载相应配置
APP_MODE = os.getenv('APP_MODE', 'local')

if APP_MODE == 'docker':
    try:
        from docker.docker_config import docker_config as config
        print("🐳 使用Docker容器配置")
    except ImportError:
        print("❌ Docker配置加载失败，回退到默认配置")
        from config import config
elif APP_MODE == 'local':
    try:
        from local_config import local_config as config
        print("🔧 使用本地开发配置")
    except ImportError:
        print("❌ 本地配置加载失败，回退到默认配置")
        from config import config
else:
    from config import config
    print("☁️ 使用生产环境配置")

# API基础URL
API_BASE_URL = config.API_GATEWAY_URL

# 全局会话存储
user_sessions = {}

@cl.on_chat_start
async def start():
    """聊天开始时的初始化"""
    logger.info("新的聊天会话开始")
    
    # 立即显示固定菜单
    logger.info("聊天开始时立即显示固定菜单")
    await show_fixed_menu()
    
    # 检查用户认证状态
    user_info = await check_authentication()
    
    if not user_info:
        # 显示登录界面
        await show_login_interface()
    else:
        # 用户已登录，显示主界面
        await show_main_interface(user_info)

async def show_fixed_menu():
    """显示固定在输入框上方的菜单"""
    try:
        logger.info("开始显示固定菜单...")
        
        # 创建固定的菜单消息，包含一些内容来确保显示
        menu_actions = [
            cl.Action(name="view_documents", value="documents", label="📚 文档库"),
            cl.Action(name="view_chat_history", value="history", label="💬 聊天历史"),
            cl.Action(name="select_agent", value="agent", label="🤖 选择Agent"),
            cl.Action(name="logout", value="logout", label="🚪 登出")
        ]
        
        # 发送包含内容的菜单消息，确保显示
        menu_content = "**功能菜单** - 请选择您需要的功能：\n\n💡 **提示**: 您可以直接在聊天中上传文件，系统会自动添加到知识库"
        menu_msg = await cl.Message(content=menu_content, actions=menu_actions).send()
        logger.info("✅ 固定菜单已显示")
        
        # 确保菜单消息被正确发送
        if menu_msg:
            logger.info("菜单消息发送成功")
        else:
            logger.warning("菜单消息发送可能失败")
            
    except Exception as e:
        logger.error(f"显示固定菜单失败: {str(e)}")
        # 尝试发送一个简单的消息
        try:
            await cl.Message(content="菜单加载中...").send()
        except:
            pass

@cl.on_message
async def main(message: cl.Message):
    """处理用户消息"""
    try:
        user_session = get_user_session()
        
        if not user_session or not user_session.get('authenticated'):
            await cl.Message(content="请先登录后再进行对话。").send()
            await show_login_interface()
            return
        
        # 记录消息详情
        has_content = bool(message.content and message.content.strip())
        has_elements = bool(message.elements)
        logger.info(f"收到用户消息: 内容={has_content}, 附件={has_elements}")
        
        if has_content:
            logger.info(f"消息内容: {message.content[:50]}...")
        
        # 如果有附件，优先处理文件上传
        if has_elements:
            logger.info(f"检测到文件附件: {len(message.elements)} 个文件")
            
            # 处理每个文件
            for i, element in enumerate(message.elements):
                try:
                    logger.info(f"处理文件 {i+1}/{len(message.elements)}: {getattr(element, 'name', 'unknown')}")
                    await handle_file_upload(user_session, element)
                except Exception as e:
                    logger.error(f"处理文件 {i+1} 时发生错误: {str(e)}")
                    await cl.Message(content=f"❌ 处理文件时发生错误: {str(e)}").send()
            
            # 如果同时有文本内容，也处理文本
            if has_content:
                logger.info("文件上传后，继续处理文本内容...")
                # 继续执行下面的文本处理逻辑
            else:
                # 只有文件，没有文本，显示固定菜单后返回
                logger.info("只有文件上传，没有文本内容，显示固定菜单")
                await show_fixed_menu()
                return
        
        # 如果没有附件且内容为空，提示用户
        if not has_content and not has_elements:
            await cl.Message(content="💡 请输入您的问题，或者上传文件到知识库。").send()
            await show_fixed_menu()
            return
        
        # 检查特殊命令
        if message.content.strip().lower() == "创建示例文档":
            await create_sample_document(user_session)
            await show_fixed_menu()
            return
        
        # 检查是否是文档内容（简单的启发式判断）
        if len(message.content) > 100 and not message.content.endswith('?'):
            # 可能是文档内容，尝试作为文档上传
            await handle_text_document_upload(user_session, message.content)
            await show_fixed_menu()
            return
        
        # 显示思考状态
        thinking_msg = cl.Message(content="🤔 正在思考...")
        await thinking_msg.send()
        
        # 处理用户消息
        logger.info("开始处理用户消息...")
        response = await process_user_message(message.content, user_session)
        logger.info(f"收到API响应: {response.get('content', '')[:100]}...")
        
        # 更新思考消息为实际回复
        thinking_msg.content = response['content']
        await thinking_msg.update()
        
        # 如果有使用的文档，显示参考资料
        if response.get('used_documents'):
            await show_referenced_documents(response['used_documents'])
        
        # 每次AI回复后都显示固定的菜单
        logger.info("显示固定菜单...")
        await show_fixed_menu()
            
    except Exception as e:
        logger.error(f"处理消息时发生错误: {str(e)}")
        await cl.Message(content="抱歉，处理您的消息时发生错误，请稍后重试。").send()
        # 即使出错也要显示固定菜单
        await show_fixed_menu()

@cl.on_settings_update
async def setup_settings(settings):
    """设置更新处理"""
    logger.info(f"设置更新: {settings}")

# 注意：当前Chainlit版本不支持@cl.on_file_upload装饰器
# 文件上传功能通过用户界面提示引导用户进行
# 用户可以通过以下方式上传文档：
# 1. 在聊天界面直接粘贴文档内容
# 2. 使用"创建示例文档"功能
# 3. 通过文档上传界面输入文档内容

@cl.action_callback("login")
async def handle_login(action):
    """处理登录操作"""
    await show_login_form()

@cl.action_callback("register")
async def handle_register(action):
    """处理注册操作"""
    await show_register_form()

@cl.action_callback("logout")
async def handle_logout(action):
    """处理登出操作"""
    user_session = get_user_session()
    user_session['authenticated'] = False
    user_session['access_token'] = None
    user_session['user_info'] = None
    
    # 确保会话数据被保存
    cl.user_session.user_data = user_session
    
    await cl.Message(content="✅ 已成功登出").send()
    await show_login_interface()

@cl.action_callback("view_documents")
async def handle_view_documents(action):
    """查看文档列表"""
    await show_document_list()

@cl.action_callback("view_chat_history")
async def handle_view_chat_history(action):
    """查看聊天历史"""
    await show_chat_history()

@cl.action_callback("select_agent")
async def handle_select_agent(action):
    """选择Agent工作流"""
    await show_agent_selection()

@cl.action_callback("create_sample_doc")
async def handle_create_sample_doc(action):
    """创建示例文档"""
    user_session = get_user_session()
    if user_session and user_session.get('authenticated'):
        await create_sample_document(user_session)
        # 显示固定的菜单
        await show_fixed_menu()
    else:
        await cl.Message(content="请先登录。").send()

@cl.action_callback("refresh_documents")
async def handle_refresh_documents(action):
    """刷新文档列表"""
    await show_document_list()

@cl.action_callback("back_to_main")
async def handle_back_to_main(action):
    """返回主页"""
    user_session = get_user_session()
    if user_session and user_session.get('authenticated'):
        await show_main_interface(user_session['user_info'])
        # 显示固定的菜单
        await show_fixed_menu()
    else:
        await show_login_interface()

# 认证相关函数

async def check_authentication() -> Optional[Dict[str, Any]]:
    """检查用户认证状态"""
    user_session = get_user_session()
    
    if not user_session or not user_session.get('authenticated') or not user_session.get('access_token'):
        logger.info("用户未认证或令牌不存在")
        return None
    
    # 验证令牌有效性
    try:
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f"Bearer {user_session['access_token']}"}
            async with session.post(f"{API_BASE_URL}/auth/verify", headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    user_info = data.get('user')
                    if user_info:
                        logger.info(f"用户认证有效: {user_info.get('username', 'unknown')}")
                        return user_info
                    else:
                        logger.warn("API返回的用户信息为空")
                        return None
                else:
                    # 令牌无效，清除会话
                    logger.warn(f"令牌验证失败，状态码: {response.status}")
                    user_session['authenticated'] = False
                    user_session['access_token'] = None
                    user_session['user_info'] = None
                    cl.user_session.user_data = user_session
                    return None
    except Exception as e:
        logger.error(f"验证令牌失败: {str(e)}")
        # 网络错误时，如果本地有用户信息，暂时信任
        if user_session.get('user_info'):
            logger.info("网络错误，使用本地缓存的用户信息")
            return user_session['user_info']
        return None

async def show_login_interface():
    """显示登录界面"""
    actions = [
        cl.Action(name="login", value="login", label="🔐 登录"),
        cl.Action(name="register", value="register", label="📝 注册")
    ]
    
    await cl.Message(
        content="## 欢迎使用Chainlit RAG知识库系统\n\n请选择登录或注册以开始使用。",
        actions=actions
    ).send()

async def show_login_form():
    """显示登录表单"""
    try:
        # 使用正确的方式请求用户输入
        response = await cl.AskUserMessage(
            content="请输入您的登录信息，格式：邮箱,密码\n例如：user@example.com,password123",
            timeout=120
        ).send()
        
        if response:
            try:
                # 调试：打印响应对象的详细信息
                logger.info(f"AskUserMessage响应类型: {type(response)}")
                logger.info(f"AskUserMessage响应内容: {response}")
                
                # 安全地提取内容
                if hasattr(response, 'content'):
                    content = response.content
                elif isinstance(response, dict):
                    # 检查是否有 output 字段（用户输入的内容）
                    if 'output' in response:
                        content = response['output']
                    else:
                        content = response.get('content', str(response))
                else:
                    content = str(response)
                
                logger.info(f"提取的内容: {content}")
                
                # 验证内容格式
                if ',' not in content:
                    await cl.Message(content="❌ 输入格式错误，请按照 '邮箱,密码' 的格式输入。").send()
                    await show_login_interface()
                    return
                
                email, password = content.split(',', 1)
                email = email.strip()
                password = password.strip()
                
                if not email or not password:
                    await cl.Message(content="❌ 邮箱和密码不能为空。").send()
                    await show_login_interface()
                    return
                
                # 显示登录进度
                progress_msg = cl.Message(content="🔍 正在验证登录信息...")
                await progress_msg.send()
                
                # 调用登录API
                login_result = await authenticate_user(email, password)
                
                if login_result['success']:
                    user_session = get_user_session()
                    user_session['authenticated'] = True
                    user_session['access_token'] = login_result['access_token']
                    user_session['user_info'] = login_result['user_info']
                    
                    # 确保会话数据被保存
                    cl.user_session.user_data = user_session
                    
                    progress_msg.content = f"✅ 登录成功！欢迎回来，{login_result['user_info']['username']}！"
                    await progress_msg.update()
                    
                    # 记录登录成功
                    logger.info(f"用户 {login_result['user_info']['username']} 已登录并显示主界面")
                    await show_main_interface(login_result['user_info'])
                else:
                    progress_msg.content = f"❌ 登录失败：{login_result['error']}"
                    await progress_msg.update()
                    await show_login_interface()
                    
            except ValueError:
                await cl.Message(content="❌ 输入格式错误，请按照 '邮箱,密码' 的格式输入。").send()
                await show_login_interface()
            except Exception as e:
                logger.error(f"登录处理失败: {str(e)}")
                await cl.Message(content="❌ 登录处理失败，请稍后重试。").send()
                await show_login_interface()
        else:
            await cl.Message(content="❌ 登录已取消。").send()
            await show_login_interface()
            
    except Exception as e:
        logger.error(f"显示登录表单失败: {str(e)}")
        await cl.Message(content="❌ 登录表单显示失败，请刷新页面重试。").send()

async def show_register_form():
    """显示注册表单"""
    try:
        # 使用正确的方式请求用户输入
        response = await cl.AskUserMessage(
            content="请输入注册信息，格式：邮箱,用户名,密码,姓名（可选）\n例如：user@example.com,myusername,password123,张三",
            timeout=120
        ).send()
        
        if response:
            try:
                # 调试：打印响应对象的详细信息
                logger.info(f"注册AskUserMessage响应类型: {type(response)}")
                logger.info(f"注册AskUserMessage响应内容: {response}")
                
                # 安全地提取内容
                if hasattr(response, 'content'):
                    content = response.content
                elif isinstance(response, dict):
                    # 检查是否有 output 字段（用户输入的内容）
                    if 'output' in response:
                        content = response['output']
                    else:
                        content = response.get('content', str(response))
                else:
                    content = str(response)
                
                logger.info(f"注册提取的内容: {content}")
                
                parts = content.split(',')
                if len(parts) < 3:
                    await cl.Message(content="❌ 输入格式错误，至少需要邮箱、用户名和密码。").send()
                    await show_login_interface()
                    return
                
                email = parts[0].strip()
                username = parts[1].strip()
                password = parts[2].strip()
                full_name = parts[3].strip() if len(parts) > 3 else None
                
                if not email or not username or not password:
                    await cl.Message(content="❌ 邮箱、用户名和密码不能为空。").send()
                    await show_login_interface()
                    return
                
                # 显示注册进度
                progress_msg = cl.Message(content="📝 正在创建您的账户...")
                await progress_msg.send()
                
                # 调用注册API
                register_result = await register_user(email, username, password, full_name)
                
                if register_result['success']:
                    user_session = get_user_session()
                    user_session['authenticated'] = True
                    user_session['access_token'] = register_result['access_token']
                    user_session['user_info'] = register_result['user_info']
                    
                    progress_msg.content = f"✅ 注册成功！欢迎，{username}！"
                    await progress_msg.update()
                    await show_main_interface(register_result['user_info'])
                else:
                    progress_msg.content = f"❌ 注册失败：{register_result['error']}"
                    await progress_msg.update()
                    await show_login_interface()
                    
            except Exception as e:
                logger.error(f"注册处理失败: {str(e)}")
                await cl.Message(content="❌ 注册处理失败，请稍后重试。").send()
                await show_login_interface()
        else:
            await cl.Message(content="❌ 注册已取消。").send()
            await show_login_interface()
            
    except Exception as e:
        logger.error(f"显示注册表单失败: {str(e)}")
        await cl.Message(content="❌ 注册表单显示失败，请刷新页面重试。").send()

async def authenticate_user(email: str, password: str) -> Dict[str, Any]:
    """用户登录认证"""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {'email': email, 'password': password}
            async with session.post(f"{API_BASE_URL}/auth/login", json=payload) as response:
                data = await response.json()
                
                if response.status == 200:
                    return {
                        'success': True,
                        'access_token': data['access_token'],
                        'user_info': data['user']
                    }
                else:
                    return {
                        'success': False,
                        'error': data.get('error', '登录失败')
                    }
    except Exception as e:
        logger.error(f"认证API调用失败: {str(e)}")
        return {'success': False, 'error': '网络连接失败'}

async def register_user(email: str, username: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    """用户注册"""
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                'email': email,
                'username': username,
                'password': password,
                'full_name': full_name
            }
            async with session.post(f"{API_BASE_URL}/auth/register", json=payload) as response:
                data = await response.json()
                
                if response.status == 201:
                    return {
                        'success': True,
                        'access_token': data['access_token'],
                        'user_info': data['user']
                    }
                else:
                    return {
                        'success': False,
                        'error': data.get('error', '注册失败')
                    }
    except Exception as e:
        logger.error(f"注册API调用失败: {str(e)}")
        return {'success': False, 'error': '网络连接失败'}

# 主界面相关函数

async def show_main_interface(user_info: Dict[str, Any]):
    """显示主界面"""
    try:
        # 显示欢迎消息
        welcome_msg = f"""🎉 欢迎回来，{user_info.get('full_name', user_info.get('username', '用户'))}！

您现在可以：
- 📎 **上传文件**: 直接在聊天中拖拽或选择文件上传（支持 .txt, .md, .pdf, .docx, .doc, .csv, .json）
- 💬 **智能对话**: 基于上传的文档内容进行智能对话
- 📚 **查看文档**: 管理您的知识库文档
- 🤖 **选择AI助手**: 选择不同的AI助手

💡 **使用提示**: 
• 直接在聊天框中拖拽或选择文件上传
• 支持多种文件格式，系统会自动处理
• 上传后即可基于文档内容进行对话！
"""
        
        # 显示欢迎消息和菜单
        await cl.Message(content=welcome_msg).send()
        
        # 显示固定菜单
        await show_fixed_menu()
        
        # 保存用户会话信息
        session_id = getattr(cl.user_session, 'id', 'default_session')
        user_sessions[session_id] = {
            'user_info': user_info,
            'conversation_id': None
        }
        
        logger.info(f"用户 {user_info.get('username')} 已登录并显示主界面")
        
    except Exception as e:
        logger.error(f"显示主界面失败: {str(e)}")
        await cl.Message(content="显示主界面时发生错误，请刷新页面重试。").send()

async def process_user_message(message: str, user_session: Dict[str, Any]) -> Dict[str, Any]:
    """处理用户消息并获取AI回复"""
    try:
        logger.info(f"开始处理用户消息: {message[:50]}...")
        
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        payload = {
            'message': message,
            'conversation_id': user_session.get('conversation_id'),
            'agent_workflow': user_session.get('selected_agent', 'default_rag')
        }
        
        logger.info(f"发送请求到API: {API_BASE_URL}/chat")
        logger.info(f"请求载荷: {payload}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/chat", headers=headers, json=payload) as response:
                logger.info(f"API响应状态: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"API响应数据: {str(data)[:200]}...")
                    
                    # 保存对话ID
                    if 'conversation_id' in data:
                        user_session['conversation_id'] = data['conversation_id']
                    
                    return {
                        'content': data.get('content', '抱歉，我无法生成回答。'),
                        'used_documents': data.get('used_documents', []),
                        'reasoning_steps': data.get('reasoning_steps', [])
                    }
                else:
                    error_data = await response.json()
                    logger.error(f"API调用失败: {error_data}")
                    return {
                        'content': f"处理消息时发生错误：{error_data.get('error', '未知错误')}",
                        'used_documents': [],
                        'reasoning_steps': []
                    }
                    
    except Exception as e:
        logger.error(f"处理用户消息失败: {str(e)}")
        return {
            'content': "抱歉，我暂时无法处理您的消息，请稍后重试。",
            'used_documents': [],
            'reasoning_steps': []
        }

def get_main_actions():
    """获取主界面操作按钮（已废弃，使用show_fixed_menu替代）"""
    return [
        cl.Action(name="upload_document", value="upload", label="📄 上传文档"),
        cl.Action(name="view_documents", value="documents", label="📚 文档库"),
        cl.Action(name="view_chat_history", value="history", label="💬 聊天历史"),
        cl.Action(name="select_agent", value="agent", label="🤖 选择Agent"),
        cl.Action(name="logout", value="logout", label="🚪 登出")
    ]

async def show_referenced_documents(used_documents: List[Dict[str, Any]]):
    """显示参考文档"""
    if not used_documents:
        return
    
    content = "### 📚 参考资料\n\n"
    for i, doc in enumerate(used_documents, 1):
        content += f"{i}. **{doc.get('filename', '未知文档')}**\n"
        content += f"   - 相似度: {doc.get('similarity_score', 0):.2%}\n"
        if doc.get('chunk_content'):
            preview = doc['chunk_content'][:100] + "..." if len(doc['chunk_content']) > 100 else doc['chunk_content']
            content += f"   - 内容预览: {preview}\n"
        content += "\n"
    
    await cl.Message(content=content).send()

# 文档管理相关函数

async def show_document_upload_interface():
    """显示简化的文档上传页面"""
    try:
        user_session = get_user_session()
        if not user_session or not user_session.get('authenticated'):
            await cl.Message(content="请先登录。").send()
            return
        
        # 简化的上传界面
        content = """# 📄 文档上传

**当前版本支持以下上传方式：**

1. **📝 直接粘贴文档内容** - 在下方输入框中粘贴您的文档内容
2. **🧪 创建示例文档** - 快速创建一个测试文档
3. **📋 手动输入** - 逐段输入文档内容

**支持的内容类型：**
- 纯文本 (.txt)
- Markdown (.md) 
- 文档内容 (PDF、Word等需要先复制文本内容)

**💡 使用建议：**
- 对于PDF或Word文档，请先复制文本内容再粘贴
- 长文档可以分段上传
- 使用"创建示例文档"功能快速体验
"""
        
        # 添加操作按钮
        actions = [
            cl.Action(name="create_sample_doc", value="sample", label="🧪 创建示例文档"),
            cl.Action(name="back_to_main", value="main", label="🏠 返回主页"),
            cl.Action(name="view_documents", value="documents", label="📚 查看文档库")
        ]
        
        await cl.Message(content=content, actions=actions).send()
        
        # 显示固定的菜单
        await show_fixed_menu()
        
    except Exception as e:
        logger.error(f"显示文档上传界面失败: {str(e)}")
        await cl.Message(content="❌ 文档上传界面显示失败，请刷新页面重试。").send()

async def handle_text_document_upload(user_session: Dict[str, Any], content: str):
    """处理用户粘贴的文档内容"""
    try:
        progress_msg = cl.Message(content="📝 正在处理您的文档内容...")
        await progress_msg.send()
        
        # 生成文档名称
        import hashlib
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        
        # 尝试从内容中提取标题
        lines = content.split('\n')
        title = "用户文档"
        for line in lines[:5]:  # 检查前5行
            line = line.strip()
            if line and not line.startswith('#') and len(line) < 50:
                title = line[:30]
                break
        
        filename = f"{title}_{content_hash}.txt"
        
        # 上传文档内容
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field('file', content.encode('utf-8'), 
                              filename=filename, 
                              content_type='text/plain')
            form_data.add_field('metadata', json.dumps({
                'filename': filename,
                'file_size': len(content.encode('utf-8')),
                'content_type': 'text/plain'
            }))
            
            async with session.post(f"{API_BASE_URL}/documents/upload", 
                                  headers=headers, 
                                  data=form_data) as response:
                
                result = await response.json()
                
                if response.status == 201:
                    progress_msg.content = f"""
✅ 文档上传成功！

📋 **文档名称**: {filename}
📊 **文档大小**: {len(content)} 字符
📄 **文档状态**: 已处理完成

🎯 **测试建议**: 您现在可以问我关于这个文档的问题了！
💬 直接在下方输入您的问题开始体验吧！
                    """
                    await progress_msg.update()
                else:
                    progress_msg.content = f"❌ 文档上传失败: {result.get('error', '未知错误')}"
                    await progress_msg.update()
                    
    except Exception as e:
        logger.error(f"文档内容处理失败: {str(e)}")
        await cl.Message(content=f"❌ 文档内容处理失败: {str(e)}").send()

async def create_sample_document(user_session: Dict[str, Any]):
    """创建示例文档用于测试"""
    try:
        progress_msg = cl.Message(content="📝 正在创建示例文档...")
        await progress_msg.send()
        
        # 创建示例文档内容
        sample_content = """
# Chainlit RAG 知识库系统使用指南

## 系统简介
Chainlit RAG 知识库系统是一个基于检索增强生成(RAG)技术的智能问答系统。

## 主要功能

### 1. 文档管理
- 支持多种文档格式上传
- 自动文档向量化处理
- 文档内容智能分块

### 2. 智能问答
- 基于OpenAI GPT模型
- 检索相关文档内容
- 生成准确的答案

### 3. 用户管理
- 安全的用户认证系统
- 个人文档库管理
- 聊天历史记录

### 4. Agent工作流
- 可配置的AI助手
- 不同场景的专用助手
- 灵活的工作流定制

## 使用方法

1. **上传文档**: 将您的知识文档上传到系统
2. **提出问题**: 基于上传的文档内容提问
3. **获得答案**: 系统会检索相关内容并生成回答

## 技术特点

- **向量检索**: 使用FAISS进行高效的语义搜索
- **文档处理**: 支持PDF、Word、文本等格式
- **智能分析**: AI助手可以进行深度分析
- **安全可靠**: 完整的用户认证和数据保护

## 常见问题

Q: 支持哪些文档格式？
A: 支持PDF、TXT、MD、DOCX等常见格式。

Q: 文档大小限制是多少？
A: 单个文件最大支持50MB。

Q: 如何提高问答准确性？
A: 上传高质量、结构化的文档，并使用具体明确的问题。

---
*本文档由系统自动生成，用于演示RAG系统的文档处理和问答能力。*
        """
        
        # 上传示例文档
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field('file', sample_content.encode('utf-8'), 
                              filename='RAG系统使用指南.txt', 
                              content_type='text/plain')
            form_data.add_field('metadata', json.dumps({
                'filename': 'RAG系统使用指南.txt',
                'file_size': len(sample_content.encode('utf-8')),
                'content_type': 'text/plain'
            }))
            
            async with session.post(f"{API_BASE_URL}/documents/upload", 
                                  headers=headers, 
                                  data=form_data) as response:
                
                result = await response.json()
                
                if response.status == 201:
                    progress_msg.content = """
✅ 示例文档创建成功！

📋 **文档名称**: RAG系统使用指南.txt
📊 **文档状态**: 已上传并处理完成

🎯 **测试建议**: 您现在可以问我：
- "RAG系统有哪些功能？"
- "如何上传文档？"  
- "支持什么文档格式？"
- "系统的技术特点是什么？"

💬 直接在下方输入您的问题开始体验吧！
                    """
                    await progress_msg.update()
                    
                    # 显示固定的菜单
                    await show_fixed_menu()
                else:
                    progress_msg.content = f"❌ 示例文档创建失败: {result.get('error', '未知错误')}"
                    await progress_msg.update()
                    
    except Exception as e:
        logger.error(f"创建示例文档失败: {str(e)}")
        await cl.Message(content=f"❌ 创建示例文档失败: {str(e)}").send()

async def show_document_list():
    """显示文档管理页面"""
    user_session = get_user_session()
    
    try:
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/documents", headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    documents = data.get('documents', [])
                    
                    # 创建文档管理页面
                    content = """# 📚 文档管理中心

## 📋 功能说明

这是一个独立的文档管理页面，您可以在这里：
- 📄 **上传新文档**: 添加知识文档到您的个人知识库
- 📖 **查看文档**: 浏览所有已上传的文档
- 🔍 **文档详情**: 查看文档的详细信息
- 🗑️ **管理文档**: 删除不需要的文档

## 📊 文档统计

"""
                    
                    if documents:
                        content += f"- **总文档数**: {len(documents)} 个\n"
                        total_size = sum(doc.get('file_size', 0) for doc in documents)
                        content += f"- **总大小**: {format_file_size(total_size)}\n"
                        processed_count = sum(1 for doc in documents if doc.get('status') == 'processed')
                        content += f"- **已处理**: {processed_count} 个\n"
                        content += f"- **处理中**: {len(documents) - processed_count} 个\n\n"
                        
                        content += "## 📖 文档列表\n\n"
                        for i, doc in enumerate(documents, 1):
                            status_emoji = {
                                'processed': '✅',
                                'processing': '⏳',
                                'failed': '❌',
                                'uploading': '📤'
                            }.get(doc.get('status'), '❓')
                            
                            # 使用display_name或原文件名，避免显示乱码
                            display_name = doc.get('display_name') or doc.get('original_filename') or doc.get('filename', '未知文档')
                            content += f"### {i}. {status_emoji} {display_name}\n"
                            content += f"**文件信息**:\n"
                            content += f"- 📁 类型: {doc.get('file_type', '未知')}\n"
                            content += f"- 📏 大小: {format_file_size(doc.get('file_size', 0))}\n"
                            content += f"- 📅 上传时间: {format_datetime(doc.get('created_at'))}\n"
                            content += f"- 🔄 状态: {doc.get('status', '未知')}\n"
                            
                            if doc.get('chunk_count'):
                                content += f"- 📄 文档块: {doc['chunk_count']} 个\n"
                            if doc.get('vector_count'):
                                content += f"- 🧮 向量数: {doc['vector_count']} 个\n"
                            
                            content += "\n"
                    else:
                        content += """## 📝 暂无文档

您还没有上传任何文档。请点击"📄 上传文档"按钮开始添加您的知识库内容。

### 💡 支持的文件类型
- 📄 **文本文件** (.txt)
- 📊 **PDF文档** (.pdf)
- 📝 **Markdown** (.md)
- 📘 **Word文档** (.docx)

### 🚀 开始使用
1. 点击"📄 上传文档"按钮
2. 选择您要上传的文件
3. 等待文档处理完成
4. 开始与AI对话，它会基于您的文档内容回答

---
*上传文档后，AI将能够基于这些内容为您提供更准确的回答。*
"""
                    
                    # 添加操作按钮
                    actions = [
                        cl.Action(name="upload_document", value="upload", label="📄 上传新文档"),
                        cl.Action(name="refresh_documents", value="refresh", label="🔄 刷新列表"),
                        cl.Action(name="back_to_main", value="main", label="🏠 返回主页")
                    ]
                    
                    await cl.Message(content=content, actions=actions).send()
                    
                    # 显示固定的菜单
                    await show_fixed_menu()
                else:
                    await cl.Message(content="❌ 获取文档列表失败。").send()
                    
    except Exception as e:
        logger.error(f"获取文档列表失败: {str(e)}")
        await cl.Message(content="❌ 获取文档列表时发生错误。").send()

async def show_chat_history():
    """显示聊天历史"""
    user_session = get_user_session()
    
    try:
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/chat/history", headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    conversations = data.get('conversations', [])
                    
                    if not conversations:
                        await cl.Message(content="💬 您还没有聊天记录。").send()
                        # 显示固定的菜单
                        await show_fixed_menu()
                        return
                    
                    content = "### 💬 聊天历史\n\n"
                    for i, conv in enumerate(conversations, 1):
                        content += f"{i}. **{conv.get('title', '新对话')}**\n"
                        content += f"   - 消息数: {conv.get('message_count', 0)}\n"
                        content += f"   - 最后活动: {format_datetime(conv.get('last_message_at'))}\n"
                        content += f"   - Agent: {conv.get('agent_workflow', 'default_rag')}\n"
                        content += "\n"
                    
                    await cl.Message(content=content).send()
                    
                    # 显示固定的菜单
                    await show_fixed_menu()
                else:
                    await cl.Message(content="❌ 获取聊天历史失败。").send()
                    
    except Exception as e:
        logger.error(f"获取聊天历史失败: {str(e)}")
        await cl.Message(content="❌ 获取聊天历史时发生错误。").send()

async def show_agent_selection():
    """显示Agent选择界面"""
    # TODO: 从API获取可用的Agent列表
    agents = [
        {'id': 'default_rag', 'name': '默认RAG助手', 'description': '基础的检索增强生成助手'},
        {'id': 'analytical_agent', 'name': '分析型助手', 'description': '专门用于数据分析和深度解答'},
        {'id': 'conversational_agent', 'name': '对话型助手', 'description': '支持多轮对话的友好助手'}
    ]
    
    content = "### 🤖 选择AI助手\n\n"
    for agent in agents:
        content += f"**{agent['name']}**\n"
        content += f"- {agent['description']}\n\n"
    
    content += "请回复对应的数字选择助手（1-3）："
    
    await cl.Message(content=content).send()
    
    # 显示固定的菜单
    await show_fixed_menu()
    
    # TODO: 处理用户选择

# 工具函数

def get_user_session() -> Dict[str, Any]:
    """获取用户会话"""
    # 使用Chainlit的会话存储来持久化用户状态
    if not hasattr(cl.user_session, 'user_data'):
        cl.user_session.user_data = {
            'authenticated': False,
            'access_token': None,
            'user_info': None,
            'conversation_id': None,
            'selected_agent': 'default_rag'
        }
    return cl.user_session.user_data

def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def format_datetime(datetime_str: Optional[str]) -> str:
    """格式化日期时间"""
    if not datetime_str:
        return "未知"
    
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return datetime_str

async def handle_file_upload(user_session: Dict[str, Any], file_element):
    """处理文件上传"""
    try:
        logger.info(f"开始处理文件上传: {getattr(file_element, 'name', 'unknown')}")
        
        # 获取文件信息
        file_name = getattr(file_element, 'name', 'unknown')
        file_type = getattr(file_element, 'type', 'application/octet-stream')
        file_size = getattr(file_element, 'size', 0)
        
        logger.info(f"文件信息: 名称={file_name}, 类型={file_type}, 大小={file_size}")
        
        # 检查文件类型
        supported_types = [
            'text/plain', 'text/markdown', 'application/pdf', 
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/msword', 'text/csv', 'application/json'
        ]
        
        if file_type not in supported_types and not file_name.lower().endswith(('.txt', '.md', '.pdf', '.docx', '.doc', '.csv', '.json')):
            await cl.Message(content=f"❌ 不支持的文件类型: {file_type}\n\n支持的文件类型: .txt, .md, .pdf, .docx, .doc, .csv, .json").send()
            return
        
        # 尝试多种方式获取文件内容
        file_content = None
        
        # 方法1: 直接获取content
        if hasattr(file_element, 'content') and file_element.content is not None:
            file_content = file_element.content
            logger.info(f"通过content获取文件内容: {len(file_content)} bytes")
        
        # 方法2: 尝试获取bytes
        elif hasattr(file_element, 'bytes') and file_element.bytes is not None:
            file_content = file_element.bytes
            logger.info(f"通过bytes获取文件内容: {len(file_content)} bytes")
        
        # 方法3: 尝试获取data
        elif hasattr(file_element, 'data') and file_element.data is not None:
            file_content = file_element.data
            logger.info(f"通过data获取文件内容: {len(file_content)} bytes")
        
        # 方法4: 尝试调用read方法
        elif hasattr(file_element, 'read'):
            try:
                file_content = file_element.read()
                logger.info(f"通过read方法获取文件内容: {len(file_content)} bytes")
            except Exception as e:
                logger.error(f"read方法失败: {str(e)}")
        
        # 方法5: 尝试获取path并读取文件
        elif hasattr(file_element, 'path'):
            try:
                with open(file_element.path, 'rb') as f:
                    file_content = f.read()
                logger.info(f"通过path读取文件内容: {len(file_content)} bytes")
            except Exception as e:
                logger.error(f"path读取失败: {str(e)}")
        
        # 方法6: 尝试获取url并下载
        elif hasattr(file_element, 'url'):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(file_element.url) as response:
                        file_content = await response.read()
                logger.info(f"通过url下载文件内容: {len(file_content)} bytes")
            except Exception as e:
                logger.error(f"url下载失败: {str(e)}")
        
        # 如果所有方法都失败
        if file_content is None:
            logger.error(f"无法获取文件内容: {file_name}")
            # 尝试获取更多调试信息
            debug_info = f"""
文件对象属性:
- name: {getattr(file_element, 'name', 'N/A')}
- type: {getattr(file_element, 'type', 'N/A')}
- size: {getattr(file_element, 'size', 'N/A')}
- has content: {hasattr(file_element, 'content')}
- has bytes: {hasattr(file_element, 'bytes')}
- has data: {hasattr(file_element, 'data')}
- has read: {hasattr(file_element, 'read')}
- has path: {hasattr(file_element, 'path')}
- has url: {hasattr(file_element, 'url')}
"""
            logger.error(debug_info)
            await cl.Message(content=f"❌ 无法读取文件 {file_name} 的内容，请重试。\n\n💡 建议：\n1. 确保文件没有损坏\n2. 尝试复制文件内容到聊天框\n3. 使用较小的文件\n\n🔍 调试信息已记录到日志中").send()
            return
        
        # 如果是二进制内容，尝试解码为文本
        if isinstance(file_content, bytes):
            try:
                # 尝试UTF-8解码
                file_content = file_content.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    # 尝试GBK解码（中文文件）
                    file_content = file_content.decode('gbk')
                except UnicodeDecodeError:
                    # 如果都失败，使用latin-1（不会失败）
                    file_content = file_content.decode('latin-1')
        
        # 显示上传进度
        progress_msg = cl.Message(content=f"📤 正在上传文件: {file_name}\n\n📊 文件大小: {format_file_size(len(file_content.encode('utf-8')))}")
        await progress_msg.send()
        
        # 准备文件数据 - 使用FormData格式
        data = aiohttp.FormData()
        
        # 处理文件名编码问题
        try:
            # 尝试解码文件名（如果是URL编码的）
            import urllib.parse
            decoded_filename = urllib.parse.unquote(file_name)
            if decoded_filename != file_name:
                logger.info(f"文件名解码: {file_name} -> {decoded_filename}")
                file_name = decoded_filename
        except Exception as e:
            logger.warning(f"文件名解码失败: {e}")
        
        # 确保文件名是安全的
        import re
        safe_filename = re.sub(r'[^\w\-_\.]', '_', file_name)
        if safe_filename != file_name:
            logger.info(f"文件名安全化: {file_name} -> {safe_filename}")
            file_name = safe_filename
        
        # 添加文件内容
        if isinstance(file_content, str):
            # 如果是字符串，直接编码
            file_bytes = file_content.encode('utf-8')
        else:
            # 如果是字节，直接使用
            file_bytes = file_content
        
        data.add_field('file', 
                      file_bytes, 
                      filename=file_name,
                      content_type=file_type)
        
        # 添加元数据
        data.add_field('metadata', json.dumps({
            'filename': file_name,
            'file_size': len(file_bytes),
            'content_type': file_type,
            'upload_method': 'file_attachment'
        }))
        
        headers = {'Authorization': f"Bearer {user_session['access_token']}"}
        
        # 发送文件到后端API
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE_URL}/documents/upload",
                headers=headers,
                data=data
            ) as response:
                if response.status == 200 or response.status == 201:
                    response_data = await response.json()
                    logger.info(f"文件上传成功: {response_data}")
                    
                    # 更新进度消息
                    progress_msg.content = f"""✅ 文件上传成功！

📄 **文件名**: {file_name}
📊 **文件大小**: {format_file_size(len(file_content.encode('utf-8')))}
🆔 **文档ID**: {response_data.get('document_id', 'N/A')}
📈 **状态**: {response_data.get('status', '已处理')}

🎯 **现在您可以基于这个文档内容进行对话了！**
"""
                    await progress_msg.update()
                    
                    # 显示固定的菜单
                    await show_fixed_menu()
                else:
                    error_data = await response.text()
                    logger.error(f"文件上传失败: {response.status}, {error_data}")
                    
                    progress_msg.content = f"""❌ 文件上传失败

📄 **文件名**: {file_name}
📊 **文件大小**: {format_file_size(len(file_content))}
🚫 **错误**: {error_data}

💡 **建议**: 请检查文件格式是否正确，或尝试较小的文件。
"""
                    await progress_msg.update()
                    
    except Exception as e:
        logger.error(f"处理文件上传时发生错误: {str(e)}")
        await cl.Message(content=f"❌ 处理文件 {getattr(file_element, 'name', 'unknown')} 时发生错误: {str(e)}").send()

if __name__ == "__main__":
    logger.info("启动Chainlit RAG知识库系统")
    
    # 检查配置
    if not API_BASE_URL:
        logger.error("API_GATEWAY_URL未配置")
        exit(1)
    
    # 启动应用
    cl.run()