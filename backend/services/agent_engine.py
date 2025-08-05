"""
Agent工作流引擎
支持基于配置的可扩展Agent流程
"""
import yaml
import asyncio
from typing import Dict, Any, List, Optional, Union
from abc import ABC, abstractmethod
import logging

from backend.services.vector_service import VectorService
from backend.services.openai_service import OpenAIService
from backend.models.chat import ChatMessage, ChatRequest

logger = logging.getLogger(__name__)

class AgentStep(ABC):
    """Agent步骤基类"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行步骤"""
        pass

class PreprocessingStep(AgentStep):
    """预处理步骤"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("query", "")
        
        # 查询清理
        if self.config.get("max_length"):
            query = query[:self.config["max_length"]]
        
        # 语言检测
        if self.config.get("language_detection"):
            # 简单的语言检测逻辑
            context["detected_language"] = "zh" if any('\u4e00' <= char <= '\u9fff' for char in query) else "en"
        
        context["processed_query"] = query.strip()
        context["step_results"] = context.get("step_results", [])
        context["step_results"].append({
            "step": self.name,
            "type": "preprocessing",
            "output": {"processed_query": context["processed_query"]}
        })
        
        return context

class RetrievalStep(AgentStep):
    """检索步骤"""
    
    def __init__(self, name: str, config: Dict[str, Any], vector_service: VectorService):
        super().__init__(name, config)
        self.vector_service = vector_service
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("processed_query", context.get("query", ""))
        user_id = context.get("user_id")
        
        top_k = self.config.get("top_k", 5)
        similarity_threshold = self.config.get("similarity_threshold", 0.7)
        
        # 执行向量搜索
        search_results = await self.vector_service.search_documents(
            query=query,
            user_id=user_id,
            top_k=top_k,
            similarity_threshold=similarity_threshold
        )
        
        context["retrieved_documents"] = search_results
        context["step_results"].append({
            "step": self.name,
            "type": "retrieval",
            "output": {
                "document_count": len(search_results),
                "documents": [doc.dict() for doc in search_results]
            }
        })
        
        return context

class FilteringStep(AgentStep):
    """过滤步骤"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        documents = context.get("retrieved_documents", [])
        max_context_length = self.config.get("max_context_length", 2000)
        relevance_threshold = self.config.get("relevance_score_threshold", 0.6)
        
        # 过滤相关性低的文档
        filtered_docs = [
            doc for doc in documents 
            if doc.similarity_score >= relevance_threshold
        ]
        
        # 控制上下文长度
        total_length = 0
        final_docs = []
        for doc in filtered_docs:
            doc_length = len(doc.chunk_content)
            if total_length + doc_length <= max_context_length:
                final_docs.append(doc)
                total_length += doc_length
            else:
                break
        
        context["filtered_documents"] = final_docs
        context["context_text"] = "\n\n".join([doc.chunk_content for doc in final_docs])
        context["step_results"].append({
            "step": self.name,
            "type": "filtering",
            "output": {
                "filtered_count": len(final_docs),
                "total_context_length": total_length
            }
        })
        
        return context

class GenerationStep(AgentStep):
    """生成步骤"""
    
    def __init__(self, name: str, config: Dict[str, Any], openai_service: OpenAIService):
        super().__init__(name, config)
        self.openai_service = openai_service
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("processed_query", context.get("query", ""))
        context_text = context.get("context_text", "")
        
        model = self.config.get("model", "gpt-3.5-turbo")
        temperature = self.config.get("temperature", 0.7)
        max_tokens = self.config.get("max_tokens", 1000)
        system_prompt = self.config.get("system_prompt", "你是一个helpful助手。")
        
        # 构建消息
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        if context_text:
            user_content = f"上下文信息:\n{context_text}\n\n用户问题: {query}"
        else:
            user_content = query
            
        messages.append({"role": "user", "content": user_content})
        
        # 调用OpenAI API
        response = await self.openai_service.chat_completion(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        context["generated_response"] = response
        context["step_results"].append({
            "step": self.name,
            "type": "generation",
            "output": {
                "response": response,
                "model_used": model,
                "tokens_used": len(response.split())  # 简单的token计算
            }
        })
        
        return context

class AnalysisStep(AgentStep):
    """分析步骤"""
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        query = context.get("query", "")
        
        # 简单的意图检测
        intent = "question_answering"
        if any(word in query.lower() for word in ["分析", "比较", "评估"]):
            intent = "analysis"
        elif any(word in query.lower() for word in ["搜索", "查找", "找到"]):
            intent = "search"
        
        # 实体提取 (简化版)
        entities = []
        # 这里可以集成更复杂的NER模型
        
        context["detected_intent"] = intent
        context["extracted_entities"] = entities
        context["step_results"].append({
            "step": self.name,
            "type": "analysis",
            "output": {
                "intent": intent,
                "entities": entities
            }
        })
        
        return context

class AgentWorkflow:
    """Agent工作流"""
    
    def __init__(self, name: str, description: str, steps: List[AgentStep]):
        self.name = name
        self.description = description
        self.steps = steps
    
    async def execute(self, initial_context: Dict[str, Any]) -> Dict[str, Any]:
        """执行工作流"""
        context = initial_context.copy()
        context["workflow_name"] = self.name
        context["step_results"] = []
        
        try:
            for step in self.steps:
                logger.info(f"执行步骤: {step.name}")
                context = await step.execute(context)
            
            context["workflow_status"] = "completed"
            return context
            
        except Exception as e:
            logger.error(f"工作流执行失败: {str(e)}")
            context["workflow_status"] = "failed"
            context["error"] = str(e)
            return context

class AgentEngine:
    """Agent引擎主类"""
    
    def __init__(self, config_path: str, vector_service: VectorService, openai_service: OpenAIService):
        self.config_path = config_path
        self.vector_service = vector_service
        self.openai_service = openai_service
        self.workflows: Dict[str, AgentWorkflow] = {}
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.workflows = {}
            workflows_config = config.get("agent_workflows", {})
            
            for workflow_name, workflow_config in workflows_config.items():
                steps = []
                for step_config in workflow_config.get("steps", []):
                    step = self._create_step(step_config)
                    if step:
                        steps.append(step)
                
                workflow = AgentWorkflow(
                    name=workflow_config.get("name", workflow_name),
                    description=workflow_config.get("description", ""),
                    steps=steps
                )
                self.workflows[workflow_name] = workflow
            
            logger.info(f"已加载 {len(self.workflows)} 个工作流")
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            # 创建默认工作流
            self._create_default_workflow()
    
    def _create_step(self, step_config: Dict[str, Any]) -> Optional[AgentStep]:
        """创建步骤实例"""
        step_name = step_config.get("name")
        step_type = step_config.get("type")
        config = step_config.get("config", {})
        
        step_classes = {
            "preprocessing": PreprocessingStep,
            "analysis": AnalysisStep,
            "filtering": FilteringStep,
        }
        
        if step_type == "retrieval":
            return RetrievalStep(step_name, config, self.vector_service)
        elif step_type == "generation":
            return GenerationStep(step_name, config, self.openai_service)
        elif step_type in step_classes:
            return step_classes[step_type](step_name, config)
        else:
            logger.warning(f"未知的步骤类型: {step_type}")
            return None
    
    def _create_default_workflow(self):
        """创建默认工作流"""
        steps = [
            PreprocessingStep("preprocessing", {"max_length": 500}),
            RetrievalStep("retrieval", {"top_k": 5}, self.vector_service),
            FilteringStep("filtering", {"max_context_length": 2000}),
            GenerationStep("generation", {"model": "gpt-3.5-turbo"}, self.openai_service)
        ]
        
        self.workflows["default_rag"] = AgentWorkflow(
            name="默认RAG助手",
            description="基础的检索增强生成助手",
            steps=steps
        )
    
    async def process_chat(self, chat_request: ChatRequest, user_id: str) -> Dict[str, Any]:
        """处理聊天请求"""
        workflow_name = chat_request.agent_workflow
        workflow = self.workflows.get(workflow_name)
        
        if not workflow:
            logger.warning(f"未找到工作流: {workflow_name}, 使用默认工作流")
            workflow = self.workflows.get("default_rag")
            if not workflow:
                raise ValueError("没有可用的工作流")
        
        # 构建初始上下文
        initial_context = {
            "query": chat_request.message,
            "user_id": user_id,
            "conversation_id": chat_request.conversation_id,
            "context_documents": chat_request.context_documents or []
        }
        
        # 执行工作流
        result = await workflow.execute(initial_context)
        
        return {
            "response": result.get("generated_response", "抱歉，我无法生成回答。"),
            "workflow_name": workflow_name,
            "step_results": result.get("step_results", []),
            "used_documents": [doc.document_id for doc in result.get("filtered_documents", [])],
            "status": result.get("workflow_status", "unknown")
        }
    
    def get_available_workflows(self) -> Dict[str, Dict[str, str]]:
        """获取可用的工作流列表"""
        return {
            name: {
                "name": workflow.name,
                "description": workflow.description
            }
            for name, workflow in self.workflows.items()
        }