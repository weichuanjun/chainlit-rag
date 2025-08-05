"""
OpenAI API服务
"""
import openai
import asyncio
from typing import List, Dict, Any, Optional
import logging
from config import config

logger = logging.getLogger(__name__)

class OpenAIService:
    """OpenAI API服务类"""
    
    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.default_model = config.OPENAI_MODEL
        self.embedding_model = config.OPENAI_EMBEDDING_MODEL
    
    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> str:
        """
        聊天完成API调用
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            stream: 是否流式输出
            
        Returns:
            生成的回答文本
        """
        try:
            model = model or self.default_model
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=stream
            )
            
            if stream:
                # 处理流式响应
                content = ""
                async for chunk in response:
                    if chunk.choices[0].delta.content is not None:
                        content += chunk.choices[0].delta.content
                return content
            else:
                return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"OpenAI聊天完成API调用失败: {str(e)}")
            raise
    
    async def create_embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        创建文本嵌入向量
        
        Args:
            text: 输入文本
            model: 嵌入模型名称
            
        Returns:
            嵌入向量
        """
        try:
            model = model or self.embedding_model
            
            response = await self.client.embeddings.create(
                model=model,
                input=text
            )
            
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"OpenAI嵌入API调用失败: {str(e)}")
            raise
    
    async def create_embeddings_batch(
        self, 
        texts: List[str], 
        model: Optional[str] = None,
        batch_size: int = 100
    ) -> List[List[float]]:
        """
        批量创建文本嵌入向量
        
        Args:
            texts: 文本列表
            model: 嵌入模型名称
            batch_size: 批处理大小
            
        Returns:
            嵌入向量列表
        """
        try:
            model = model or self.embedding_model
            embeddings = []
            
            # 分批处理
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                
                response = await self.client.embeddings.create(
                    model=model,
                    input=batch_texts
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)
                
                # 避免API限流
                if i + batch_size < len(texts):
                    await asyncio.sleep(0.1)
            
            return embeddings
            
        except Exception as e:
            logger.error(f"OpenAI批量嵌入API调用失败: {str(e)}")
            raise
    
    async def moderate_content(self, text: str) -> Dict[str, Any]:
        """
        内容审核
        
        Args:
            text: 需要审核的文本
            
        Returns:
            审核结果
        """
        try:
            response = await self.client.moderations.create(input=text)
            
            result = response.results[0]
            return {
                "flagged": result.flagged,
                "categories": result.categories.dict(),
                "category_scores": result.category_scores.dict()
            }
            
        except Exception as e:
            logger.error(f"OpenAI内容审核API调用失败: {str(e)}")
            raise
    
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ):
        """
        流式聊天完成（生成器）
        
        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大token数
            
        Yields:
            每个chunk的内容
        """
        try:
            model = model or self.default_model
            
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            async for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
                    
        except Exception as e:
            logger.error(f"OpenAI流式聊天API调用失败: {str(e)}")
            raise
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """
        文本摘要
        
        Args:
            text: 原始文本
            max_length: 摘要最大长度
            
        Returns:
            摘要文本
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": f"请将以下文本总结为不超过{max_length}字的摘要。"
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
            
            summary = await self.chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=max_length
            )
            
            return summary
            
        except Exception as e:
            logger.error(f"文本摘要失败: {str(e)}")
            raise
    
    async def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """
        提取关键词
        
        Args:
            text: 输入文本
            max_keywords: 最大关键词数量
            
        Returns:
            关键词列表
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": f"从以下文本中提取最多{max_keywords}个关键词，用逗号分隔。"
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
            
            response = await self.chat_completion(
                messages=messages,
                temperature=0.1,
                max_tokens=100
            )
            
            # 解析关键词
            keywords = [kw.strip() for kw in response.split(",")]
            return keywords[:max_keywords]
            
        except Exception as e:
            logger.error(f"关键词提取失败: {str(e)}")
            return []