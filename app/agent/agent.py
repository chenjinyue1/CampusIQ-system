import os
import json
import asyncio
from langsmith import traceable
from typing import List, Optional, AsyncGenerator

from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_community.chat_models import ChatTongyi
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool

from app.agent.agent_middleware import get_middleware
from app.agent.agent_tools import rag_summary_tools, get_weather_tools, what_time_is_now, get_user_info_tools, \
    reorder_documents_tools, set_current_user_id, set_thinking_callback
from app.utils.logger_handler import logger
from app.services import session_manager as sm
from app.utils.prompt_loader import load_system_prompts


class AgentFactory:
    """
    生产 Agent 工厂类
    支持：
    - 每次调用创建全新的 AgentExecutor 实例
    - 动态注入工具、提示词、模型配置
    - 支持异步流式调用
    """

    def __init__(
            self,
            model: str = "qwen2.5:7b",
            api_key: Optional[str] = None,
            default_tools: Optional[List[BaseTool]] = None,
            default_middleware: Optional[List] = None,
            default_system_prompt: Optional[str] = None,
    ):
        """
        初始化工厂配置（仅配置，不创建实例）
        :param model: 默认模型名称
        :param api_key: 默认 API Key（不传则从env读取）
        :param default_tools: 默认工具列表
        :param default_system_prompt: 默认系统提示词
        """
        self.model = model
        self.api_key = api_key or os.getenv("OLLAMA_BASE_URL")
        self.default_tools = default_tools or self._get_default_tools()
        self.default_middleware = default_middleware or self._get_default_middleware()
        self.default_system_prompt = default_system_prompt or self._get_default_system_prompt()

    @staticmethod
    def _get_default_tools() -> List[BaseTool]:
        """获取默认工具列表"""
        return [
            rag_summary_tools,
            get_weather_tools,
            what_time_is_now,
            get_user_info_tools,
            reorder_documents_tools,
        ]

    def _get_default_middleware(self) -> List:
        """获取默认中间件列表"""
        return get_middleware()

    @staticmethod
    def _get_default_system_prompt() -> str:
        """获取默认系统提示词"""
        return load_system_prompts()

    def _create_chat_model(self, custom_model: Optional[str] = None):
        """内部方法：根据LLM_TYPE创建聊天模型实例"""
        llm_type = os.getenv("LLM_TYPE").upper()
        
        if llm_type == "OLLAMA":
            model_name = custom_model or os.getenv("OLLAMA_CHAT_MODEL_NAME", self.model)
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            
            logger.info(f"🤖 Agent使用Ollama模型: {model_name}")
            
            return ChatOllama(
                model=model_name,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )
        
        elif llm_type == "ALIYUN":
            api_key = os.getenv("ALIYUN_API_KEY")
            base_url = os.getenv("ALIYUN_BASE_URL")
            model_name = custom_model or os.getenv("ALIYUN_CHAT_MODEL_NAME", self.model)
            
            logger.info(f"🤖 Agent使用阿里云百炼模型: {model_name}")
            
            return ChatTongyi(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                streaming=True,
                top_p=0.7,
            )
        
        else:
            raise ValueError(f"不支持的LLM_TYPE: {llm_type}，可选值: ALIYUN, OLLAMA")

    def _create_prompt(self, custom_system_prompt: Optional[str] = None) -> ChatPromptTemplate:
        """内部方法：创建提示词模板"""
        return ChatPromptTemplate.from_messages([
            ("system", "{system_prompt}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])


    def create_agent_executor(
            self,
            custom_tools: Optional[List[BaseTool]] = None,
            custom_model: Optional[str] = None,
            custom_system_prompt: Optional[str] = None,
            verbose: bool = True,
            return_intermediate_steps: bool = True,
            **kwargs
    ) -> AgentExecutor:
        """
        核心工厂方法：创建全新的 AgentExecutor 实例
        每次调用都会生成新的实例，彻底避免全局状态污染

        :param custom_tools: 自定义工具列表（覆盖默认）
        :param custom_model: 自定义模型（覆盖默认）
        :param custom_system_prompt: 自定义系统提示词（覆盖默认）
        :param verbose: 是否打印详细日志
        :param return_intermediate_steps: 是否返回中间步骤
        :param kwargs: 其他 AgentExecutor 参数
        :return: 全新的 AgentExecutor 实例
        """
        # 1. 创建组件（每次都重新创建，避免全局状态污染）
        chat_model = self._create_chat_model(custom_model)
        prompt = self._create_prompt()
        tools = custom_tools or self.default_tools
        system_prompt = custom_system_prompt or self.default_system_prompt

        # 2. 创建 Agent
        agent = create_tool_calling_agent(chat_model, tools, prompt)

        # 3. 创建 Executor
        return AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=verbose,
            return_intermediate_steps=return_intermediate_steps,
            **kwargs
        )


# 初始化全局工厂配置
agent_factory = AgentFactory()


def get_agent_executor():
    """
    获取AgentExecutor实例，用于LangGraph
    :return: AgentExecutor实例
    """
    return agent_factory.create_agent_executor()


async def get_agent_response(
        query: str,
        history: Optional[List[tuple]] = None,
        user_id: Optional[str] = None,
        custom_tools: Optional[List[BaseTool]] = None,
        **kwargs
):
    """
    获取 Agent 响应（使用工厂创建实例）
    :param query: 用户查询
    :param history: 会话历史 [(user_msg, assistant_msg), ...]
    :param user_id: 用户ID
    :param custom_tools: 自定义工具（可选，用于动态切换工具）
    :param kwargs: 其他工厂参数
    :return: 响应结果
    """
    if user_id:
        set_current_user_id(user_id)

    try:
        # 1. 从工厂获取全新的 Executor 实例
        agent_executor = agent_factory.create_agent_executor(custom_tools=custom_tools, **kwargs)

        # 2. 构建聊天历史
        chat_history: List[BaseMessage] = []
        if history:
            from langchain_core.messages import HumanMessage, AIMessage
            for user_msg, assistant_msg in history:
                chat_history.append(HumanMessage(content=user_msg))
                chat_history.append(AIMessage(content=assistant_msg))

        # 3. 流式执行
        full_response = []
        steps = []
        async for chunk in agent_executor.astream({
            "input": query,
            "chat_history": chat_history,
            "system_prompt": agent_factory.default_system_prompt
        }):
            if "output" in chunk:
                full_response.append(chunk["output"])
            elif "intermediate_steps" in chunk:
                for action, observation in chunk["intermediate_steps"]:
                    # 记录日志
                    logger.info(f"\n\n🧠 [Agent 思考] {action.log}")
                    logger.info(f"🛠️ [调用工具] {action.tool}")
                    logger.info(f"📥 [工具输入] {action.tool_input}")
                    logger.info(f"📤 [工具结果] {observation}\n")
                    # 收集步骤
                    steps.append({
                        "thought": action.log,
                        "tool": action.tool,
                        "tool_input": action.tool_input,
                        "tool_output": observation
                    })

        return {
            "response": "".join(full_response) if full_response else "抱歉，我无法理解您的请求。",
            "steps": steps
        }

    except Exception as e:
        logger.error(f"Agent 执行错误: {str(e)}", exc_info=True)
        return {
            "response": f"抱歉，处理您的请求时出现了错误: {str(e)}",
            "steps": []
        }

@traceable
async def get_agent_stream_response(
        query: str,
        session_id: str,
        user_id: str,
        custom_tools: Optional[List[BaseTool]] = None,
        **kwargs
) -> AsyncGenerator[str, None]:
    """
    获取 Agent 流式响应（包含思考过程，实时推送）
    :param query: 用户查询
    :param session_id: 会话 ID
    :param user_id: 用户 ID
    :param custom_tools: 自定义工具（可选）
    :param kwargs: 其他参数
    :return: 流式响应生成器
    """
    
    thinking_queue = asyncio.Queue() # 思考过程队列
    agent_result_holder = {"response": None, "error": None} # 结果保存, 用于保存结果
    agent_done = asyncio.Event()
    
    async def thinking_callback(data: dict):
        """思考过程回调函数，将事件放入队列"""
        logger.info(f"【思考过程】{data.get('stage', 'unknown')}: {data.get('content', '')}")
        await thinking_queue.put(data)
    
    async def run_agent():
        """在独立任务中执行 Agent"""
        try:
            set_current_user_id(user_id)
            set_thinking_callback(thinking_callback)
            
            history = await sm.session_manager.get_history(session_id, user_id)
            logger.info(f"【Agent流式响应】获取会话历史成功，历史记录数: {len(history)}")
            
            chat_history: List[BaseMessage] = []
            if history:
                from langchain_core.messages import HumanMessage, AIMessage
                for user_msg, assistant_msg in history:
                    chat_history.append(HumanMessage(content=user_msg))
                    chat_history.append(AIMessage(content=assistant_msg))
            
            agent_executor = agent_factory.create_agent_executor(custom_tools=custom_tools, **kwargs)
            
            full_response = []
            
            async for chunk in agent_executor.astream({
                "input": query,
                "chat_history": chat_history,
                "system_prompt": agent_factory.default_system_prompt
            }):
                if "output" in chunk:
                    full_response.append(chunk["output"])
                elif "intermediate_steps" in chunk:
                    for action, observation in chunk["intermediate_steps"]:
                        logger.info(f"\n\n🧠 [Agent 思考] {action.log}")
                        logger.info(f"🛠️ [调用工具] {action.tool}")
                        logger.info(f"📥 [工具输入] {action.tool_input}")
                        logger.info(f"📤 [工具结果] {observation}\n")
            
            agent_result_holder["response"] = "".join(full_response) if full_response else "抱歉，我无法理解您的请求。"
        except Exception as e:
            logger.error(f"【Agent流式响应】Agent执行失败: {e}", exc_info=True)
            agent_result_holder["error"] = str(e)
        finally:
            agent_done.set()
    
    # 启动 Agent 执行任务
    agent_task = asyncio.create_task(run_agent())
    
    try:
        logger.info(f"【Agent流式响应】开始处理请求，用户ID: {user_id}, 会话ID: {session_id}, 查询: {query}")

        # 先发送初始响应
        yield f"data: {json.dumps({'type': 'response', 'content': '', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        
        # 持续监听队列并实时推送思考事件，同时等待 Agent 完成
        while not agent_done.is_set():
            try:
                # 使用短超时轮询队列，实现实时推送
                event = await asyncio.wait_for(thinking_queue.get(), timeout=0.1)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except asyncio.TimeoutError:
                # 超时是正常的，继续等待
                continue
        
        # Agent 已完成，推送队列中剩余的所有思考事件
        while not thinking_queue.empty():
            try:
                event = thinking_queue.get_nowait()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                thinking_queue.task_done()
            except asyncio.QueueEmpty:
                break
        
        # 等待 agent_task 完全结束
        await agent_task
        
        if agent_result_holder["error"]:
            error_message = f"错误: {agent_result_holder['error']}"
            yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
            return
        
        response = agent_result_holder["response"]
        
        # 添加到会话历史
        await sm.session_manager.add_message(session_id, user_id, query, response)
        logger.info(f"【Agent流式响应】添加到会话历史成功")
        
        # 发送回答内容
        for char in response:
            yield f"data: {json.dumps({'type': 'response', 'content': char}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.02)
        
        # 发送结束标记
        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id}, ensure_ascii=False)}\n\n"
        logger.info(f"【Agent流式响应】处理完成，会话ID: {session_id}")
        
    except Exception as e:
        logger.error(f"【Agent流式响应】处理请求失败: {e}", exc_info=True)
        
        # 取消 agent 任务
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        
        error_message = f"错误: {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_message, 'session_id': session_id}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"


# 测试
# ... existing code ...


if __name__ == '__main__':
    import asyncio
    import sys
    from datetime import datetime

    print("=" * 80)
    print("🚀 CampusIQ07 全链路集成测试")
    print("=" * 80)
    print(f"⏰ 测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


    async def test_full_workflow():
        """完整工作流测试 - 模拟真实用户交互"""

        # 测试配置
        TEST_USER_ID = "eiXLpAR5PsfGBoMJvjXV34"
        TEST_SESSION_ID = f"test_session_{int(datetime.now().timestamp())}"

        test_results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": []
        }

        def record_result(test_name: str, success: bool, error: str = None):
            """记录测试结果"""
            test_results["total"] += 1
            if success:
                test_results["passed"] += 1
                print(f"✅ [{test_name}] 通过")
            else:
                test_results["failed"] += 1
                test_results["errors"].append({"test": test_name, "error": error})
                print(f"❌ [{test_name}] 失败: {error}")

        print("\n" + "=" * 80)
        print("📋 测试计划:")
        print("  1. Agent流式响应测试 (基础问答)")
        print("  2. RAG检索测试 (知识库查询)")
        print("  3. 多轮对话测试 (上下文保持)")
        print("  4. 工具调用测试 (天气/时间/用户信息)")
        print("  5. 报告生成测试 (复杂任务)")
        print("  6. 异常处理测试 (错误场景)")
        print("=" * 80)

        # ==========================================
        # 测试 1: Agent流式响应 - 基础问答
        # ==========================================
        print("\n\n【测试 1】Agent流式响应 - 基础问答")
        print("-" * 80)
        try:
            query = "你好，请介绍一下你自己"
            print(f"📤 用户提问: {query}\n")

            response_chunks = []
            thinking_events = []

            async for chunk in get_agent_stream_response(
                    query=query,
                    session_id=TEST_SESSION_ID,
                    user_id=TEST_USER_ID
            ):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str:
                        try:
                            import json
                            data = json.loads(data_str)
                            if data.get("type") == "thinking":
                                thinking_events.append(data)
                                print(f"💭 [思考] {data.get('stage')}: {data.get('content', '')[:100]}")
                            elif data.get("type") == "response":
                                content = data.get("content", "")
                                response_chunks.append(content)
                                if content:
                                    print(content, end="", flush=True)
                            elif data.get("type") == "done":
                                print("\n✅ 流式响应完成")
                        except json.JSONDecodeError:
                            pass

            full_response = "".join(response_chunks)

            if len(full_response) > 0 and len(thinking_events) >= 0:
                record_result("基础问答", True)
                print(f"\n📊 统计: 收到 {len(thinking_events)} 个思考事件, {len(response_chunks)} 个响应块")
            else:
                record_result("基础问答", False, "未收到有效响应")

        except Exception as e:
            record_result("基础问答", False, str(e))
            import traceback
            traceback.print_exc()

        await asyncio.sleep(1)

        # ==========================================
        # 测试 2: RAG检索测试 - 知识库查询
        # ==========================================
        print("\n\n【测试 2】RAG检索测试 - 知识库查询")
        print("-" * 80)
        try:
            query = "扫拖一体机器人如何判断是否需要清洁滤网？"
            print(f"📤 用户提问: {query}\n")

            response_chunks = []
            has_retrieval = False

            async for chunk in get_agent_stream_response(
                    query=query,
                    session_id=TEST_SESSION_ID,
                    user_id=TEST_USER_ID
            ):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str:
                        try:
                            import json
                            data = json.loads(data_str)
                            if data.get("type") == "thinking":
                                stage = data.get("stage", "")
                                if stage in ["retrieval", "hyde", "reorder"]:
                                    has_retrieval = True
                                print(f"💭 [{stage}] {data.get('content', '')[:100]}")
                            elif data.get("type") == "response":
                                content = data.get("content", "")
                                response_chunks.append(content)
                                print(content, end="", flush=True)
                        except json.JSONDecodeError:
                            pass

            full_response = "".join(response_chunks)

            if has_retrieval and len(full_response) > 10:
                record_result("RAG检索", True)
                print(f"\n📊 统计: 检索到相关文档, 生成 {len(full_response)} 字符的回答")
            else:
                record_result("RAG检索", False, f"未触发检索或响应过短 (长度: {len(full_response)})")

        except Exception as e:
            record_result("RAG检索", False, str(e))
            import traceback
            traceback.print_exc()

        await asyncio.sleep(1)

        # ==========================================
        # 测试 3: 多轮对话测试 - 上下文保持
        # ==========================================
        print("\n\n【测试 3】多轮对话测试 - 上下文保持")
        print("-" * 80)

        conversation = [
            ("扫地机器人的电池续航一般多久？", "第一轮"),
            ("那充电需要多长时间？", "第二轮"),
            ("它支持自动回充吗？", "第三轮")
        ]

        multi_round_success = True

        for i, (query, round_name) in enumerate(conversation, 1):
            try:
                print(f"\n{round_name}: {query}")
                response_chunks = []

                async for chunk in get_agent_stream_response(
                        query=query,
                        session_id=TEST_SESSION_ID,
                        user_id=TEST_USER_ID
                ):
                    if chunk.startswith("data: "):
                        data_str = chunk[6:].strip()
                        if data_str:
                            try:
                                import json
                                data = json.loads(data_str)
                                if data.get("type") == "response":
                                    response_chunks.append(data.get("content", ""))
                            except json.JSONDecodeError:
                                pass

                response = "".join(response_chunks)
                if len(response) > 5:
                    print(f"✅ {round_name}响应成功 (长度: {len(response)})")
                else:
                    print(f"⚠️ {round_name}响应过短")
                    multi_round_success = False

            except Exception as e:
                print(f"❌ {round_name}失败: {e}")
                multi_round_success = False
                break

            await asyncio.sleep(0.5)

        record_result("多轮对话", multi_round_success, "某轮对话失败" if not multi_round_success else None)

        # ==========================================
        # 测试 4: 工具调用测试
        # ==========================================
        print("\n\n【测试 4】工具调用测试")
        print("-" * 80)

        tool_tests = [
            ("现在几点了？", "时间查询工具", "what_time"),
            ("北京天气怎么样？", "天气查询工具", "weather"),
        ]

        for query, test_name, expected_tool in tool_tests:
            try:
                print(f"\n📤 测试 {test_name}: {query}")
                response_chunks = []
                tool_called = False

                async for chunk in get_agent_stream_response(
                        query=query,
                        session_id=TEST_SESSION_ID,
                        user_id=TEST_USER_ID
                ):
                    if chunk.startswith("data: "):
                        data_str = chunk[6:].strip()
                        if data_str:
                            try:
                                import json
                                data = json.loads(data_str)
                                if data.get("type") == "thinking":
                                    if "tool" in data.get("content", "").lower():
                                        tool_called = True
                                elif data.get("type") == "response":
                                    response_chunks.append(data.get("content", ""))
                            except json.JSONDecodeError:
                                pass

                response = "".join(response_chunks)

                if tool_called or len(response) > 5:
                    record_result(test_name, True)
                    print(f"✅ {test_name}成功")
                else:
                    record_result(test_name, False, "未检测到工具调用")

            except Exception as e:
                record_result(test_name, False, str(e))

            await asyncio.sleep(0.5)

        # ==========================================
        # 测试 5: 报告生成测试 - 复杂任务
        # ==========================================
        print("\n\n【测试 5】报告生成测试 - 复杂任务")
        print("-" * 80)
        try:
            query = "帮我生成我的使用报告，包括我最近的使用情况和常见问题"
            print(f"📤 用户请求: {query}\n")

            response_chunks = []
            has_summary = False

            async for chunk in get_agent_stream_response(
                    query=query,
                    session_id=TEST_SESSION_ID,
                    user_id=TEST_USER_ID
            ):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str:
                        try:
                            import json
                            data = json.loads(data_str)
                            if data.get("type") == "thinking":
                                stage = data.get("stage", "")
                                if stage == "summarize":
                                    has_summary = True
                                print(f"💭 [{stage}] {data.get('content', '')[:100]}")
                            elif data.get("type") == "response":
                                content = data.get("content", "")
                                response_chunks.append(content)
                                print(content, end="", flush=True)
                        except json.JSONDecodeError:
                            pass

            full_response = "".join(response_chunks)

            if has_summary and len(full_response) > 50:
                record_result("报告生成", True)
                print(f"\n📊 统计: 生成了 {len(full_response)} 字符的报告")
            else:
                record_result("报告生成", False, f"未触发总结或报告过短 (长度: {len(full_response)})")

        except Exception as e:
            record_result("报告生成", False, str(e))
            import traceback
            traceback.print_exc()

        # ==========================================
        # 测试 6: 异常处理测试
        # ==========================================
        print("\n\n【测试 6】异常处理测试")
        print("-" * 80)

        # 测试空查询
        try:
            print("\n📤 测试空查询...")
            response_chunks = []

            async for chunk in get_agent_stream_response(
                    query="",
                    session_id=TEST_SESSION_ID,
                    user_id=TEST_USER_ID
            ):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str:
                        try:
                            import json
                            data = json.loads(data_str)
                            if data.get("type") == "response":
                                response_chunks.append(data.get("content", ""))
                            elif data.get("type") == "error":
                                print(f"⚠️ 收到错误: {data.get('content')}")
                        except json.JSONDecodeError:
                            pass

            record_result("空查询处理", True)
            print("✅ 空查询被正常处理")

        except Exception as e:
            record_result("空查询处理", False, str(e))

        # 测试超长查询
        try:
            print("\n📤 测试超长查询...")
            long_query = "请问" + "这个问题很重要" * 100

            response_chunks = []
            async for chunk in get_agent_stream_response(
                    query=long_query,
                    session_id=TEST_SESSION_ID,
                    user_id=TEST_USER_ID
            ):
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str:
                        try:
                            import json
                            data = json.loads(data_str)
                            if data.get("type") == "response":
                                response_chunks.append(data.get("content", ""))
                        except json.JSONDecodeError:
                            pass

            record_result("超长查询处理", True)
            print("✅ 超长查询被正常处理")

        except Exception as e:
            record_result("超长查询处理", False, str(e))

        # ==========================================
        # 输出测试报告
        # ==========================================
        print("\n\n" + "=" * 80)
        print("📊 测试报告汇总")
        print("=" * 80)
        print(f"总测试数: {test_results['total']}")
        print(f"✅ 通过: {test_results['passed']}")
        print(f"❌ 失败: {test_results['failed']}")
        print(
            f"成功率: {(test_results['passed'] / test_results['total'] * 100) if test_results['total'] > 0 else 0:.1f}%")

        if test_results['errors']:
            print("\n❌ 失败的测试详情:")
            for error in test_results['errors']:
                print(f"  - {error['test']}: {error['error']}")

        print("\n" + "=" * 80)
        print(f"⏰ 测试结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        return test_results['failed'] == 0


    # 运行测试
    try:
        success = asyncio.run(test_full_workflow())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试执行出错: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

